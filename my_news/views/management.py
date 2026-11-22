"""Configuración del feed: fuentes, palabras filtro e instrucciones para la IA."""
from datetime import timedelta

from django.contrib import messages
from django.db.models import Count, Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST, require_http_methods

from Bookshelf.http_utils import is_ajax, superuser_required

from ..forms import AIFilterInstructionForm, FeedSourceForm, FilterWordForm
from ..models import AIFilterInstruction, FeedSource, FilterWord


# Palabras filtro por tanda en la configuración. Con 150 reglas, pintarlas
# todas de golpe eran 354 KB de HTML; la búsqueda hace el resto.
WORD_FILTERS_PAGE_SIZE = 40


# Ventana del orden «Más filtradas»: la misma que vive una noticia antes de
# que `purge_old_news` la borre.
WORD_FILTERS_RECENT_DAYS = 15


def _management_redirect(section):
    return redirect(f"{reverse('my_news:feed_management')}#{section}")


@require_GET
@superuser_required
def feed_management(request):
    sources = list(FeedSource.objects.annotate(news_count=Count('news')).order_by('name'))
    ai_filters = list(AIFilterInstruction.objects.order_by('-created_at'))

    # Las palabras filtro llegan por tandas: la página trae la primera y el
    # resto se pide a `word_filter_rows`. Los totales salen de agregados, no
    # de recorrer la lista, que ya no está entera aquí.
    search = (request.GET.get('q') or '').strip()
    state = _word_filter_state(request.GET.get('estado'))
    order = _word_filter_order(request.GET.get('orden'))
    word_filters, matched_word_filters, _, has_more_word_filters = _word_filter_page(search, state, order, 0)
    word_filter_totals = FilterWord.objects.aggregate(
        total=Count('pk'),
        active=Count('pk', filter=Q(active=True)),
    )

    context = {
        'sources': sources,
        'word_filters': word_filters,
        'ai_filters': ai_filters,
        'word_filter_search': search,
        'word_filter_state': state,
        'word_filter_order': order,
        'word_filters_recent_days': WORD_FILTERS_RECENT_DAYS,
        'matched_word_filters': matched_word_filters,
        'has_more_word_filters': has_more_word_filters,
        'next_word_filter_offset': len(word_filters),
        'word_filters_page_size': WORD_FILTERS_PAGE_SIZE,
        'total_word_filters': word_filter_totals['total'],
        'active_sources': sum(source.active for source in sources),
        'active_word_filters': word_filter_totals['active'],
        'active_ai_filters': sum(ai_filter.active for ai_filter in ai_filters),
    }
    return render(request, 'feed_management.html', context)


def _render_management_form(request, form, *, title, eyebrow, back_section, submit_label):
    return render(request, 'feed_management_form.html', {
        'form': form,
        'form_title': title,
        'form_eyebrow': eyebrow,
        'back_section': back_section,
        'submit_label': submit_label,
    })


def _word_filter_base(search=None, state=None):
    """Palabras filtro que casan con la búsqueda y el estado, sin recuentos.

    La búsqueda va contra la base y no contra lo ya pintado: la lista se carga
    por tandas, así que filtrar en el navegador solo miraría el trozo cargado.
    """
    qs = FilterWord.objects.all()
    if search:
        qs = qs.filter(word__icontains=search)
    if state == 'active':
        qs = qs.filter(active=True)
    elif state == 'paused':
        qs = qs.filter(active=False)
    return qs


def _word_filter_state(value):
    return value if value in ('active', 'paused') else 'all'


def _word_filter_order(value):
    return value if value == 'filtradas' else 'alfabetico'


def _word_filter_page(search, state, order, offset):
    """Una tanda de palabras más el total que casa con la búsqueda.

    El recuento es de los últimos `WORD_FILTERS_RECENT_DAYS` días, también
    cuando se ordena alfabéticamente, para que la cifra de la tarjeta sea la
    misma con los dos órdenes.
    """
    # El total se cuenta sobre el queryset SIN anotar: con el `annotate` el
    # COUNT se envuelve en una subconsulta agrupada que no hace falta para
    # contar filas.
    matched = _word_filter_base(search, state).count()
    since = timezone.now() - timedelta(days=WORD_FILTERS_RECENT_DAYS)
    rows_qs = (
        _word_filter_base(search, state)
        .annotate(news_count=Count(
            'filtered_news',
            filter=Q(filtered_news__created_at__gte=since),
        ))
    )
    # El desempate por palabra y pk hace falta para paginar: con el mismo
    # recuento en varias filas, sin un orden total una tanda podría repetir o
    # saltarse palabras de la anterior.
    if order == 'filtradas':
        rows_qs = rows_qs.order_by('-news_count', 'word', 'pk')
    else:
        rows_qs = rows_qs.order_by('word', 'pk')
    # Devuelve el desplazamiento ya acotado: quien lo llama lo necesita para
    # decir por dónde sigue, y con uno negativo la cuenta saldría mal.
    offset = max(0, offset)
    rows = list(rows_qs[offset:offset + WORD_FILTERS_PAGE_SIZE])
    return rows, matched, offset, offset + len(rows) < matched


@require_GET
@superuser_required
def word_filter_rows(request):
    """Tanda de palabras filtro en JSON, para buscar sin recargar la página."""
    search = (request.GET.get('q') or '').strip()
    state = _word_filter_state(request.GET.get('estado'))
    order = _word_filter_order(request.GET.get('orden'))
    try:
        offset = int(request.GET.get('offset') or 0)
    except (TypeError, ValueError):
        offset = 0

    rows, matched, offset, has_more = _word_filter_page(search, state, order, offset)
    html = ''.join(
        render_to_string('feed_management_word_card.html', {'filter': word_filter}, request=request)
        for word_filter in rows
    )
    return JsonResponse({
        'status': 'success',
        'html': html,
        'matched': matched,
        'returned': len(rows),
        'next_offset': offset + len(rows),
        'has_more': has_more,
    })


@require_http_methods(['GET', 'POST'])
@superuser_required
def source_create(request):
    form = FeedSourceForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        source = form.save()
        messages.success(request, f"Fuente «{source.name}» creada.")
        return _management_redirect('sources')
    return _render_management_form(
        request, form, title='Nueva fuente RSS', eyebrow='Fuentes',
        back_section='sources', submit_label='Crear fuente',
    )


@require_http_methods(['GET', 'POST'])
@superuser_required
def source_edit(request, pk):
    source = get_object_or_404(FeedSource, pk=pk)
    form = FeedSourceForm(request.POST or None, instance=source)
    if request.method == 'POST' and form.is_valid():
        source = form.save()
        messages.success(request, f"Fuente «{source.name}» actualizada.")
        return _management_redirect('sources')
    return _render_management_form(
        request, form, title=f'Editar {source.name}', eyebrow='Fuentes',
        back_section='sources', submit_label='Guardar cambios',
    )


@require_http_methods(['GET', 'POST'])
@superuser_required
def word_filter_create(request):
    form = FilterWordForm(request.POST or None)
    if request.method == 'POST' and is_ajax(request):
        # El modal del feed: crea sin salir de la página que se está leyendo.
        if not form.is_valid():
            errors = [error for field_errors in form.errors.values() for error in field_errors]
            return JsonResponse({'status': 'error', 'message': ' '.join(errors)}, status=400)
        word_filter = form.save()
        return JsonResponse({'status': 'success', 'message': f"Filtro «{word_filter.word}» creado."})
    if request.method == 'POST' and form.is_valid():
        word_filter = form.save()
        messages.success(request, f"Filtro «{word_filter.word}» creado.")
        return _management_redirect('word-filters')
    return _render_management_form(
        request, form, title='Nuevo filtro por palabra', eyebrow='Filtros por palabra',
        back_section='word-filters', submit_label='Crear filtro',
    )


@require_http_methods(['GET', 'POST'])
@superuser_required
def word_filter_edit(request, pk):
    word_filter = get_object_or_404(FilterWord, pk=pk)
    form = FilterWordForm(request.POST or None, instance=word_filter)
    if request.method == 'POST' and form.is_valid():
        word_filter = form.save()
        messages.success(request, f"Filtro «{word_filter.word}» actualizado.")
        return _management_redirect('word-filters')
    return _render_management_form(
        request, form, title=f'Editar {word_filter.word}', eyebrow='Filtros por palabra',
        back_section='word-filters', submit_label='Guardar cambios',
    )


@require_http_methods(['GET', 'POST'])
@superuser_required
def ai_filter_create(request):
    form = AIFilterInstructionForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, 'Instrucción para la IA creada.')
        return _management_redirect('ai-filters')
    return _render_management_form(
        request, form, title='Nueva instrucción para la IA', eyebrow='Filtros con IA',
        back_section='ai-filters', submit_label='Crear instrucción',
    )


@require_http_methods(['GET', 'POST'])
@superuser_required
def ai_filter_edit(request, pk):
    ai_filter = get_object_or_404(AIFilterInstruction, pk=pk)
    form = AIFilterInstructionForm(request.POST or None, instance=ai_filter)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, 'Instrucción para la IA actualizada.')
        return _management_redirect('ai-filters')
    return _render_management_form(
        request, form, title='Editar instrucción para la IA', eyebrow='Filtros con IA',
        back_section='ai-filters', submit_label='Guardar cambios',
    )


def _toggle_management_object(request, obj, section, label):
    obj.active = not obj.active
    obj.save(update_fields=['active'])
    state = 'activado' if obj.active else 'desactivado'
    if is_ajax(request):
        # Sin recargar: la configuración pierde la búsqueda escrita y la
        # posición de la lista si se responde con el redirect de siempre.
        return JsonResponse({'status': 'success', 'active': obj.active, 'message': f'{label} {state}.'})
    messages.success(request, f'{label} {state}.')
    return _management_redirect(section)


@require_POST
@superuser_required
def source_toggle(request, pk):
    source = get_object_or_404(FeedSource, pk=pk)
    return _toggle_management_object(request, source, 'sources', f'«{source.name}»')


@require_POST
@superuser_required
def word_filter_toggle(request, pk):
    word_filter = get_object_or_404(FilterWord, pk=pk)
    return _toggle_management_object(request, word_filter, 'word-filters', f'«{word_filter.word}»')


@require_POST
@superuser_required
def ai_filter_toggle(request, pk):
    ai_filter = get_object_or_404(AIFilterInstruction, pk=pk)
    return _toggle_management_object(request, ai_filter, 'ai-filters', 'La instrucción')


def _confirm_management_delete(
    request, obj, *, object_name, object_detail, impact_count, impact_label, section
):
    if request.method == 'POST':
        if request.POST.get('confirmation') != 'delete':
            return render(request, 'feed_management_confirm_delete.html', {
                'object_name': object_name,
                'object_detail': object_detail,
                'impact_count': impact_count,
                'impact_label': impact_label,
                'back_section': section,
                'confirmation_error': True,
            }, status=400)
        obj.delete()
        messages.success(request, 'El elemento se eliminó correctamente.')
        return _management_redirect(section)
    return render(request, 'feed_management_confirm_delete.html', {
        'object_name': object_name,
        'object_detail': object_detail,
        'impact_count': impact_count,
        'impact_label': impact_label,
        'back_section': section,
    })


@require_http_methods(['GET', 'POST'])
@superuser_required
def source_delete(request, pk):
    source = get_object_or_404(FeedSource, pk=pk)
    return _confirm_management_delete(
        request, source, object_name='Fuente', object_detail=source.name,
        impact_count=source.news_set.count(), impact_label='noticias asociadas',
        section='sources',
    )


@require_http_methods(['GET', 'POST'])
@superuser_required
def word_filter_delete(request, pk):
    word_filter = get_object_or_404(FilterWord, pk=pk)
    return _confirm_management_delete(
        request, word_filter, object_name='Filtro', object_detail=word_filter.word,
        impact_count=word_filter.filtered_news.count(),
        impact_label='noticias conservarán su estado filtrado, pero perderán esta referencia',
        section='word-filters',
    )


@require_http_methods(['GET', 'POST'])
@superuser_required
def ai_filter_delete(request, pk):
    ai_filter = get_object_or_404(AIFilterInstruction, pk=pk)
    return _confirm_management_delete(
        request, ai_filter, object_name='Instrucción', object_detail=ai_filter.instruction,
        impact_count=0, impact_label='', section='ai-filters',
    )

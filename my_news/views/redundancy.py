"""Página de revisión de lo que se quedó fuera del feed en un día:
palabras filtro, filtro de la IA y duplicados.
"""
import logging
from datetime import datetime

from django.db.models import Count, Q
from django.http import JsonResponse
from django.shortcuts import render
from django.template.loader import render_to_string
from django.urls import reverse
from django.views.decorators.http import require_GET

from Bookshelf.http_utils import superuser_required

from ..models import News
from .common import _day_bounds_local

logger = logging.getLogger(__name__)


# Filas por tanda en la página de redundancia. Cada una lleva el texto
# completo de la noticia (dos, en los pares redundantes), así que pintar el
# día entero eran 365 KB de HTML.
REDUNDANCY_PAGE_SIZE = 25


REDUNDANCY_TABS = ('keyword', 'ai', 'redundant')


def _redundancy_day_bounds(value):
    """Día local de la página de redundancia, tolerando una fecha inválida."""
    try:
        selected_date = datetime.strptime(value, '%Y-%m-%d').date() if value else None
    except (TypeError, ValueError):
        selected_date = None
    return _day_bounds_local(selected_date)


def _redundancy_tab_queryset(tab, start_dt, end_dt):
    """Las tres listas del día, cada una excluyendo las categorías anteriores.

    El orden importa: una noticia redundante que además casó con una palabra
    filtro se cuenta una sola vez, en la categoría de más peso.
    """
    day_qs = News.objects.filter(created_at__gte=start_dt, created_at__lt=end_dt)
    if tab == 'keyword':
        return day_qs.filter(
            filtered_by__isnull=False, is_redundant=False, is_ai_filtered=False
        ).select_related('source', 'filtered_by').order_by('-created_at', '-id')
    if tab == 'ai':
        return day_qs.filter(
            is_ai_filtered=True, is_redundant=False
        ).select_related('source').order_by('-created_at', '-id')
    # Un duplicado cuyo original ya se purgó no tiene `similar_to`, pero conserva
    # su titular en `similar_ref`: sigue siendo un par que se puede revisar.
    return day_qs.filter(
        Q(similar_to__isnull=False) | ~Q(similar_ref=''),
        is_redundant=True,
    ).select_related('similar_to', 'source', 'similar_to__source').order_by('-created_at', '-id')


@require_GET
@superuser_required
def redundancy_rows(request):
    """Tanda de filas de una pestaña, para no pintar el día entero de golpe."""
    tab = request.GET.get('tab')
    if tab not in REDUNDANCY_TABS:
        return JsonResponse({'status': 'error', 'message': 'Pestaña desconocida.'}, status=400)

    _, start_dt, end_dt = _redundancy_day_bounds(request.GET.get('date'))
    try:
        offset = max(0, int(request.GET.get('offset') or 0))
    except (TypeError, ValueError):
        offset = 0

    qs = _redundancy_tab_queryset(tab, start_dt, end_dt)
    matched = qs.count()
    rows = list(qs[offset:offset + REDUNDANCY_PAGE_SIZE])
    html = render_to_string(
        'redundancy_test_rows.html', {'tab': tab, 'rows': rows}, request=request
    )
    return JsonResponse({
        'status': 'success',
        'html': html,
        'matched': matched,
        'returned': len(rows),
        'next_offset': offset + len(rows),
        'has_more': offset + len(rows) < matched,
    })


@require_GET
@superuser_required
def test_redundancy(request):
    """Vista para probar la detección de redundancia en noticias"""
    try:
        # Los mismos límites que usa `redundancy_rows`: si cada uno calculara
        # su día por su cuenta, los contadores de las pestañas podrían no
        # cuadrar con las filas que se cargan dentro.
        selected_date, day_start, day_end = _redundancy_day_bounds(request.GET.get('date'))

        news_today_qs = News.objects.filter(
            created_at__gte=day_start,
            created_at__lt=day_end,
        )
        total_today = news_today_qs.count()

        # Las filas de las tres pestañas las pide `redundancy_rows` al abrirlas.

        # Calcular estadísticas para la barra (lógica revisada para exclusividad)
        if total_today > 0:
            # 1. Redundantes (máxima prioridad)
            redundant_today_count = news_today_qs.filter(is_redundant=True).count()

            # 2. Filtradas IA (pero NO redundantes)
            filtered_ai_today_count = news_today_qs.filter(
                is_ai_filtered=True,
                is_redundant=False
            ).count()

            # 3. Filtradas Keyword (pero NO redundantes NI IA)
            filtered_keyword_today_count = news_today_qs.filter(
                filtered_by__isnull=False,
                is_redundant=False,
                is_ai_filtered=False
            ).count()

            # 4. Visibles (las restantes: no redundantes, no IA, no keyword)
            # Simplificado: Total - Redundantes - Filtradas IA - Filtradas Keyword
            visible_today_count = total_today - redundant_today_count - filtered_ai_today_count - filtered_keyword_today_count
            # Asegurar que no sea negativo por algún caso extraño
            visible_today_count = max(0, visible_today_count)

            # Verificación (opcional, pero útil para depurar)
            calculated_total = visible_today_count + filtered_keyword_today_count + filtered_ai_today_count + redundant_today_count
            if calculated_total != total_today:
                 # Si esto sigue ocurriendo, hay un estado de noticia no contemplado
                 logger.warning(f"[LOGICA EXCLUSIVA] Suma ({calculated_total}) no coincide con total ({total_today}).")
                 # Como fallback, ajustamos visibles para cuadrar, aunque indica un problema subyacente
                 visible_today_count = total_today - filtered_keyword_today_count - filtered_ai_today_count - redundant_today_count
                 visible_today_count = max(0, visible_today_count)

            # Calcular porcentajes
            visible_perc = (visible_today_count / total_today) * 100 if total_today > 0 else 0
            keyword_perc = (filtered_keyword_today_count / total_today) * 100 if total_today > 0 else 0
            ai_perc = (filtered_ai_today_count / total_today) * 100 if total_today > 0 else 0
            redundant_perc = (redundant_today_count / total_today) * 100 if total_today > 0 else 0
        else:
            visible_today_count = 0
            filtered_keyword_today_count = 0
            filtered_ai_today_count = 0
            redundant_today_count = 0
            visible_perc = 0
            keyword_perc = 0
            ai_perc = 0
            redundant_perc = 0

        # Total general de redundantes histórico
        total_redundant_all_time = News.objects.filter(is_redundant=True).count()

        # Calcular estadísticas de redundancia por fuente (una sola query agregada)
        source_rows = (
            news_today_qs.filter(source__active=True)
            .values('source__name')
            .annotate(
                total_today=Count('id'),
                redundant_today=Count('id', filter=Q(is_redundant=True)),
            )
        )
        source_stats = [
            {
                'name': row['source__name'],
                'total_today': row['total_today'],
                'redundant_today': row['redundant_today'],
                'redundancy_percentage': (row['redundant_today'] / row['total_today']) * 100,
                'non_redundant_today': row['total_today'] - row['redundant_today'],
            }
            for row in source_rows
        ]

        # Ordenar por porcentaje de redundancia descendente
        source_stats.sort(key=lambda x: x['redundancy_percentage'], reverse=True)

        # Preparar el contexto
        context = {
            'rows_url': reverse('my_news:redundancy_rows'),
            'rows_page_size': REDUNDANCY_PAGE_SIZE,
            'total_redundant': total_redundant_all_time,
            'current_date': selected_date,
            'total_today': total_today,
            'visible_today_count': visible_today_count, # Contiene el recuento recalculado
            'filtered_keyword_today_count': filtered_keyword_today_count, # Contiene el recuento exclusivo
            'filtered_ai_today_count': filtered_ai_today_count,       # Contiene el recuento exclusivo
            'redundant_today_count': redundant_today_count,          # Contiene el recuento total redundante
            'visible_perc': visible_perc,
            'keyword_perc': keyword_perc,
            'ai_perc': ai_perc,
            'redundant_perc': redundant_perc,
            'source_stats': source_stats,  # Nuevas estadísticas por fuente
        }

        return render(request, 'redundancy_test.html', context)
    except Exception as e:
        logger.exception("Error en test_redundancy")
        # Podrías devolver una página de error o un JsonResponse
        # Para mantener la consistencia con la plantilla, podrías renderizarla con un mensaje de error
        return render(request, 'redundancy_test.html', {'error_message': f'Ocurrió un error: {str(e)}'})

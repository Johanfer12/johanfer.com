"""El feed: listado público y privado, paginación por cursor, sondeo de
noticias nuevas, borrar, deshacer y guardar.
"""
import hashlib
from datetime import timedelta
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from django.contrib.auth.views import LoginView
from django.core.cache import cache
from django.db.models import Max, Q
from django.http import HttpResponse, JsonResponse
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.utils.decorators import method_decorator
from django.views.decorators.http import require_GET, require_POST
from django.views.generic import ListView

from Bookshelf.http_utils import superuser_required

from ..ingestion_status import feed_alert
from ..models import News
from .common import (
    _json_server_error,
    PAGE_SIZE,
    PAGE_CACHE_TTL,
    _get_cache_version,
    _bump_cache_version,
    _safe_page,
    _day_bounds_local,
    _public_news_queryset,
    _apply_feed_filters,
    _get_total_news_and_pages,
    _serialize_news_card,
)


NEWS_NOTIFICATION_SETTLE_DELAY = timedelta(seconds=60)


def _latest_public_day_bounds():
    latest_created = _public_news_queryset().aggregate(latest=Max('created_at'))['latest']
    if latest_created is None:
        return None, None, None

    latest_local_date = timezone.localtime(latest_created).date()
    return _day_bounds_local(latest_local_date)


def _parse_cursor(cursor):
    """Cursor «fecha ISO|id» → (datetime con zona, id), o (None, None) si no vale."""
    if not cursor:
        return None, None
    try:
        ts_str, id_str = cursor.split('|', 1)
        dt = parse_datetime(ts_str)
        if dt is None:
            return None, None
        if timezone.is_naive(dt):
            dt = timezone.make_aware(dt, timezone.get_current_timezone())
        return dt, int(id_str)
    except Exception:
        return None, None


def _keyset_after(field, value, pk, *, ascending):
    """Filas que van después de (value, pk) en el orden (field, id).

    El id desempata las filas con la misma fecha, así que una página nunca
    repite ni se salta una noticia aunque compartan sello de tiempo.
    """
    op = 'gt' if ascending else 'lt'
    return Q(**{f'{field}__{op}': value}) | (Q(**{field: value}) & Q(**{f'id__{op}': pk}))


def _news_notification_cutoff():
    return timezone.now() - NEWS_NOTIFICATION_SETTLE_DELAY


def _build_page_response(request, *, order, page, cursor, search_query, saved_only=False):
    base_qs = _apply_feed_filters(
        News.visible.select_related('source'),
        saved_only=saved_only,
        search_query=search_query,
        order=order,
    )

    # El ancla es la última noticia de la página anterior: la da el cursor o,
    # sin él, se busca por posición. Un cursor que no se entiende se ignora
    # y sale la primera página.
    anchor_date = anchor_id = None
    if cursor:
        anchor_date, anchor_id = _parse_cursor(cursor)
    elif page and page > 1:
        anchor_idx = (page - 1) * PAGE_SIZE - 1
        # Solo se necesita la clave (fecha, id) del ancla: evitar
        # materializar todas las filas previas como objetos completos.
        anchor_row = list(base_qs.values_list('published_date', 'id')[anchor_idx:anchor_idx + 1])
        if anchor_row:
            anchor_date, anchor_id = anchor_row[0]
    if anchor_date is not None and anchor_id is not None:
        base_qs = base_qs.filter(
            _keyset_after('published_date', anchor_date, anchor_id, ascending=order == 'asc')
        )

    items = list(base_qs[:PAGE_SIZE + 1])
    has_more = len(items) > PAGE_SIZE
    items = items[:PAGE_SIZE]
    cards = [_serialize_news_card(article, request) for article in items]

    next_cursor = None
    if has_more:
        last = items[-1]
        next_cursor = f"{last.published_date.isoformat()}|{last.id}"

    total_news, total_pages = _get_total_news_and_pages(search_query, saved_only=saved_only)
    return {
        'status': 'success',
        'cards': cards,
        'next_cursor': next_cursor,
        'total_news': total_news,
        'total_pages': total_pages,
        'order': order
    }


@require_POST
@superuser_required
def delete_news(request, pk):
    try:
        current_page = _safe_page(request.POST.get('current_page', 1))
        order = request.POST.get('order', 'desc')
        saved_only = request.POST.get('saved_only', 'false').lower() == 'true'
        search_query = (request.POST.get('q') or '').strip() or None
        news = News.objects.get(pk=pk)
        news.is_deleted = True
        news.deleted_at = timezone.now()
        news.save(update_fields=['is_deleted', 'deleted_at'])
        _bump_cache_version()
        
        # Obtener la noticia que ahora ocupa el borde inferior de la pagina.
        # La UI ya tiene el resto de tarjetas visibles; la unica "nueva" que debe
        # llegar tras un borrado es el ultimo item de la pagina recalculada.
        next_news = None
        total_news, total_pages = _get_total_news_and_pages(search_query=search_query, saved_only=saved_only)

        base_qs = _apply_feed_filters(
            News.visible, saved_only=saved_only, search_query=search_query, order=order
        )
        # Solo hace falta el último ítem de la página recalculada; si existe,
        # la página sigue llena y ese es el reemplazo que espera la UI.
        page_end_idx = current_page * PAGE_SIZE - 1
        page_end = list(base_qs.select_related('source')[page_end_idx:page_end_idx + 1])
        if page_end:
            next_news = page_end[0]
        
        response_data = {
            'status': 'success',
            'total_news': total_news,
            'total_pages': total_pages
        }
        
        # Si hay una noticia para reemplazar, incluirla en la respuesta
        if next_news:
            response_data['card'] = _serialize_news_card(next_news, request)
        
        return JsonResponse(response_data)
    except News.DoesNotExist:
        return JsonResponse({'status': 'error', 'message': 'Noticia no encontrada'})
    except Exception:
        return _json_server_error(request)


class NewsListView(ListView):
    model = News
    saved_only = False

    def is_private_view(self):
        user = self.request.user
        return bool(user.is_authenticated and user.is_superuser)

    def get_paginate_by(self, queryset):
        return PAGE_SIZE

    def get_template_names(self):
        return ['news_list.html'] if self.is_private_view() else ['news_public.html']

    def get_queryset(self):
        if not self.is_private_view():
            local_date, start_dt, end_dt = _latest_public_day_bounds()
            self.public_news_date = local_date
            if start_dt is None:
                return News.objects.none()
            return _public_news_queryset().filter(
                created_at__gte=start_dt,
                created_at__lt=end_dt,
            ).order_by('-published_date', '-id')

        # Usar el manager optimizado + búsqueda y orden dinámico
        return _apply_feed_filters(
            News.visible.select_related('source'),
            saved_only=self.saved_only,
            search_query=self.request.GET.get('q'),
            order=self.request.GET.get('order', 'desc'),
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        if not self.is_private_view():
            local_date = getattr(self, 'public_news_date', None)
            if context.get('is_paginated'):
                total_news = context['paginator'].count
            else:
                total_news = context['object_list'].count() if hasattr(context['object_list'], 'count') else len(context['object_list'])
            context.update({
                'total_news': total_news,
                'public_news_mode': True,
                'public_news_date': local_date.strftime('%d/%m/%Y') if local_date else None,
                'public_storage_key': f"public-news-hidden:{local_date.isoformat()}" if local_date else "public-news-hidden:empty",
                'public_page_data': {
                    'current_page': context['page_obj'].number,
                    'total_pages': context['paginator'].num_pages,
                    'page_size': PAGE_SIZE,
                },
            })
            return context
        
        # Reutilizar el count de paginación que ya calcula Django
        # En lugar de hacer self.get_queryset().count() duplicado
        total_news = context['paginator'].count
        context['total_news'] = total_news

        # Obtener página actual
        page = self.request.GET.get('page', 1)
        try:
            current_page = int(page)
        except (ValueError, TypeError):
            current_page = 1

        current_queryset = self.get_queryset()
        context['current_page'] = current_page
        context['order'] = self.request.GET.get('order', 'desc')
        latest_created = current_queryset.order_by('-created_at', '-id').values_list('created_at', 'id').first()
        context['initial_news_cursor'] = f"{latest_created[0].isoformat()}|{latest_created[1]}" if latest_created else None
        context['news_view_mode'] = {'saved_only': self.saved_only}
        # Aviso de que la ingesta está parada o pausada. Solo en la vista
        # privada: es información de mantenimiento, no del feed.
        context['ingestion_alert'] = feed_alert()

        return context


@method_decorator(superuser_required, name='dispatch')
class SavedNewsListView(NewsListView):
    template_name = 'news_list.html'
    saved_only = True


@require_GET
@superuser_required
def check_new_news(request):
    try:
        cursor = request.GET.get('cursor')
        last_checked = request.GET.get('last_checked')
        saved_only = request.GET.get('saved_only', 'false').lower() == 'true'
        notification_cutoff = _news_notification_cutoff()
        current_time = notification_cutoff.isoformat()
        news_qs = _apply_feed_filters(News.visible.select_related('source'), saved_only=saved_only)
        news_qs = news_qs.filter(created_at__lte=notification_cutoff)
        created_dt, created_id = _parse_cursor(cursor)

        if created_dt and created_id is not None:
            news_qs = news_qs.filter(
                _keyset_after('created_at', created_dt, created_id, ascending=True)
            )
        elif last_checked:
            dt = parse_datetime(last_checked)
            if dt is not None:
                if timezone.is_naive(dt):
                    dt = timezone.make_aware(dt, timezone.get_current_timezone())
                news_qs = news_qs.filter(created_at__gte=dt)
            else:
                news_qs = news_qs.none()
        else:
            news_qs = news_qs.none()

        new_news = list(news_qs.order_by('created_at', 'id')[:200])
        news_cards = [_serialize_news_card(article, request) for article in new_news]
        latest_cursor = None
        if new_news:
            last_item = new_news[-1]
            latest_cursor = f"{last_item.created_at.isoformat()}|{last_item.id}"
        elif cursor:
            latest_cursor = cursor

        total_news, total_pages = _get_total_news_and_pages(saved_only=saved_only)
        
        return JsonResponse({
            'status': 'success',
            'current_time': current_time,
            'news_cards': news_cards,
            'cursor': latest_cursor,
            'total_news': total_news,
            'total_pages': total_pages
        })
    except Exception:
        return _json_server_error(request)


@require_GET
@superuser_required
def image_proxy(request):
    image_url = request.GET.get('url', '').strip()
    if not image_url:
        return JsonResponse({'status': 'error', 'message': 'Falta url'}, status=400)

    parsed = urlparse(image_url)
    if parsed.scheme not in ('http', 'https'):
        return JsonResponse({'status': 'error', 'message': 'URL no valida'}, status=400)

    try:
        req = Request(image_url, headers={
            'User-Agent': 'Mozilla/5.0 (compatible; johanfer-news-bot/1.0)'
        })
        with urlopen(req, timeout=6) as resp:
            content_type = resp.headers.get('Content-Type', '').split(';')[0].strip().lower()
            if not content_type.startswith('image/'):
                return JsonResponse({'status': 'error', 'message': 'El recurso no es imagen'}, status=415)

            data = resp.read(5 * 1024 * 1024 + 1)  # max 5MB
            if len(data) > 5 * 1024 * 1024:
                return JsonResponse({'status': 'error', 'message': 'Imagen demasiado grande'}, status=413)

            response = HttpResponse(data, content_type=content_type)
            response['Cache-Control'] = 'public, max-age=3600'
            return response
    except Exception:
        return JsonResponse({'status': 'error', 'message': 'No se pudo obtener la imagen'}, status=502)


@require_GET
@superuser_required
def get_page(request):
    try:
        order = request.GET.get('order', 'desc')
        search_query = request.GET.get('q')
        saved_only = request.GET.get('saved_only', 'false').lower() == 'true'
        page = _safe_page(request.GET.get('page', 1))
        cursor = request.GET.get('cursor')

        version = _get_cache_version()
        # is_staff entra en la clave porque desde que la tarjeta se renderiza
        # en el servidor el boton de eliminar viaja dentro del HTML cacheado.
        key_raw = f"{version}|{order}|{search_query or ''}|{page}|{cursor or ''}|{int(saved_only)}|{int(request.user.is_staff)}"
        cache_key = f"news:page:{hashlib.md5(key_raw.encode('utf-8')).hexdigest()}"
        cached = cache.get(cache_key)
        if cached:
            return JsonResponse(cached)

        payload = _build_page_response(
            request,
            order=order,
            page=page,
            cursor=cursor,
            search_query=search_query,
            saved_only=saved_only,
        )
        cache.set(cache_key, payload, PAGE_CACHE_TTL)
        return JsonResponse(payload)
    except Exception:
        return _json_server_error(request)


@require_POST
@superuser_required
def undo_delete(request, pk):
    try:
        saved_only = request.POST.get('saved_only', 'false').lower() == 'true'
        search_query = (request.POST.get('q') or '').strip() or None
        news = News.objects.get(pk=pk)
        if news.is_deleted:
            news.is_deleted = False
            news.deleted_at = None
            # Restauramos cualquier marca de filtrado manual
            news.is_filtered = False
            news.is_ai_filtered = False
            news.is_redundant = False
            news.save()
            _bump_cache_version()

        total_news, total_pages = _get_total_news_and_pages(search_query, saved_only=saved_only)

        return JsonResponse({
            'status': 'success',
            'card': _serialize_news_card(news, request),
            'total_news': total_news,
            'total_pages': total_pages
        })
    except News.DoesNotExist:
        return JsonResponse({'status': 'error', 'message': 'Noticia no encontrada'})
    except Exception:
        return _json_server_error(request)


@require_GET
@superuser_required
def latest_deleted_news(request):
    try:
        saved_only = request.GET.get('saved_only', 'false').lower() == 'true'
        search_query = (request.GET.get('q') or '').strip() or None

        deleted_qs = _apply_feed_filters(
            News.objects.select_related('source').filter(
                is_deleted=True,
                is_filtered=False,
                is_ai_filtered=False,
                is_redundant=False,
            ),
            saved_only=saved_only,
            search_query=search_query,
        )

        latest = deleted_qs.order_by('-deleted_at', '-id').first()
        if not latest:
            return JsonResponse({'status': 'empty'})

        return JsonResponse({
            'status': 'success',
            'news_id': latest.id,
            'card': _serialize_news_card(latest, request),
        })
    except Exception:
        return _json_server_error(request)


@require_POST
@superuser_required
def toggle_save_news(request, pk):
    try:
        saved_only = request.POST.get('saved_only', 'false').lower() == 'true'
        news = News.objects.get(pk=pk)
        news.is_saved = not news.is_saved
        news.save(update_fields=['is_saved'])
        _bump_cache_version()

        total_news, total_pages = _get_total_news_and_pages(saved_only=saved_only)
        return JsonResponse({
            'status': 'success',
            'news_id': news.id,
            'is_saved': bool(news.is_saved),
            'total_news': total_news,
            'total_pages': total_pages,
        })
    except News.DoesNotExist:
        return JsonResponse({'status': 'error', 'message': 'Noticia no encontrada'})
    except Exception:
        return _json_server_error(request)


# Vista de Login Personalizada
class NewsLoginView(LoginView):
    template_name = 'news_login.html' # Apuntar al archivo creado por el usuario
    redirect_authenticated_user = True # Redirigir si ya está autenticado
    next_page = '/noticias/' # Sin esto Django redirige a /accounts/profile/ (404)

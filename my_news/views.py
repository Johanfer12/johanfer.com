from django.shortcuts import render
from django.views.generic import ListView
from .models import News
from django.http import JsonResponse
from django.http import HttpResponse
from django.views.decorators.http import require_POST, require_GET
from .services import FeedService, EmbeddingService
from django.contrib.auth.decorators import user_passes_test
from django.contrib.auth.views import LoginView
from django.utils.decorators import method_decorator
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.templatetags.static import static
from django.core.cache import cache
from django.conf import settings
from datetime import datetime, time as datetime_time, timedelta
from Bookshelf.html_sanitizer import sanitize_html
import pytz
from django.db.models import Q, Count, Max
from .tasks import purge_old_news, retry_summarize_pending
import subprocess
import platform
import hashlib
import time
import logging
from urllib.parse import urlparse
from urllib.request import Request, urlopen

# Create your views here.
logger = logging.getLogger(__name__)

PAGE_SIZE = 25
# TTL corto: el caché es LocMem (independiente por worker de gunicorn y por
# proceso), así que la invalidación por versión no cruza procesos. Con 5s la
# ventana de datos desactualizados queda acotada a algo imperceptible.
COUNT_CACHE_TTL = 5
PAGE_CACHE_TTL = 5
CACHE_VERSION_KEY = 'news_feed_cache_version'
NEWS_NOTIFICATION_SETTLE_DELAY = timedelta(seconds=60)


def _get_cache_version():
    value = cache.get(CACHE_VERSION_KEY)
    if value is None:
        cache.set(CACHE_VERSION_KEY, 1, None)
        return 1
    return int(value)


def _bump_cache_version():
    try:
        cache.incr(CACHE_VERSION_KEY)
    except ValueError:
        cache.set(CACHE_VERSION_KEY, _get_cache_version() + 1, None)


def _safe_page(value):
    try:
        page = int(value)
        return page if page > 0 else 1
    except (TypeError, ValueError):
        return 1


def _counts_cache_key(search_query, saved_only=False):
    version = _get_cache_version()
    query_hash = hashlib.md5((search_query or '').strip().lower().encode('utf-8')).hexdigest()
    saved_flag = '1' if saved_only else '0'
    return f"news:count:v{version}:q:{query_hash}:saved:{saved_flag}"


def _day_bounds_local(target_date=None):
    local_date = target_date or timezone.localdate()
    current_tz = timezone.get_current_timezone()
    start_dt = timezone.make_aware(datetime.combine(local_date, datetime_time.min), current_tz)
    end_dt = start_dt + timedelta(days=1)
    return local_date, start_dt, end_dt


def _public_news_filter():
    """Noticias aptas para visitantes, sin aplicar borrados personales."""
    return News.visible.editorial_filter()


def _public_news_queryset():
    return News.objects.select_related('source').filter(_public_news_filter())


def _latest_public_day_bounds():
    latest_created = _public_news_queryset().aggregate(latest=Max('created_at'))['latest']
    if latest_created is None:
        return None, None, None

    latest_local_date = timezone.localtime(latest_created).date()
    return _day_bounds_local(latest_local_date)


def _apply_feed_filters(qs, *, saved_only=False, search_query=None, order=None):
    """Filtros comunes del feed: guardadas, búsqueda y orden keyset."""
    qs = qs.filter(is_saved=saved_only)
    if search_query:
        qs = qs.filter(Q(title__icontains=search_query) | Q(description__icontains=search_query))
    if order == 'asc':
        qs = qs.order_by('published_date', 'id')
    elif order is not None:
        qs = qs.order_by('-published_date', '-id')
    return qs


def _get_total_news_and_pages(search_query=None, saved_only=False):
    key = _counts_cache_key(search_query, saved_only=saved_only)
    cached = cache.get(key)
    if cached:
        return cached

    count_qs = _apply_feed_filters(News.visible, saved_only=saved_only, search_query=search_query)
    total_news = count_qs.count()
    total_pages = (total_news + (PAGE_SIZE - 1)) // PAGE_SIZE
    result = (total_news, total_pages)
    cache.set(key, result, COUNT_CACHE_TTL)
    return result


def _serialize_news_card(article):
    published_local = timezone.localtime(article.published_date) if article.published_date else None
    return {
        'id': article.id,
        'title': article.title or '',
        'description_html': sanitize_html(article.description),
        'link': article.link or '',
        'image_url': article.image_url or static('Img/News_Default.png'),
        'short_answer': article.short_answer or '',
        'source_name': article.source.name if article.source_id and article.source else '',
        'published_at': article.published_date.isoformat() if article.published_date else None,
        'published_label': published_local.strftime('%d/%m/%Y %H:%M') if published_local else '',
        'created_at': article.created_at.isoformat() if article.created_at else None,
        'created_cursor': f"{article.created_at.isoformat()}|{article.id}" if article.created_at else None,
        'similarity_score': article.similarity_score,
        'similarity_label': f"{article.similarity_score:.2f}" if article.similarity_score is not None else '',
        'is_saved': bool(article.is_saved),
    }


def _parse_created_cursor(cursor):
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


def _news_notification_cutoff():
    return timezone.now() - NEWS_NOTIFICATION_SETTLE_DELAY


def _build_page_response(*, order, page, cursor, search_query, saved_only=False):
    base_qs = _apply_feed_filters(
        News.visible.select_related('source'),
        saved_only=saved_only,
        search_query=search_query,
        order=order,
    )

    if cursor:
        try:
            ts_str, id_str = cursor.split('|')
            anchor_dt = parse_datetime(ts_str)
            anchor_id = int(id_str)
            if order == 'asc':
                key_q = Q(published_date__gt=anchor_dt) | (Q(published_date=anchor_dt) & Q(id__gt=anchor_id))
            else:
                key_q = Q(published_date__lt=anchor_dt) | (Q(published_date=anchor_dt) & Q(id__lt=anchor_id))
            base_qs = base_qs.filter(key_q)
        except Exception:
            pass
    elif page and page > 1:
        anchor_idx = (page - 1) * PAGE_SIZE - 1
        if anchor_idx >= 0:
            # Solo se necesita la clave (fecha, id) del ancla: evitar
            # materializar todas las filas previas como objetos completos.
            anchor_row = list(base_qs.values_list('published_date', 'id')[anchor_idx:anchor_idx + 1])
            if anchor_row:
                anchor_date, anchor_id = anchor_row[0]
                if order == 'asc':
                    key_q = Q(published_date__gt=anchor_date) | (Q(published_date=anchor_date) & Q(id__gt=anchor_id))
                else:
                    key_q = Q(published_date__lt=anchor_date) | (Q(published_date=anchor_date) & Q(id__lt=anchor_id))
                base_qs = base_qs.filter(key_q)

    items = list(base_qs[:PAGE_SIZE + 1])
    has_more = len(items) > PAGE_SIZE
    items = items[:PAGE_SIZE]
    cards = [_serialize_news_card(article) for article in items]

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
@user_passes_test(lambda u: u.is_superuser, login_url='/noticias/login/')
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
            response_data['card'] = _serialize_news_card(next_news)
        
        return JsonResponse(response_data)
    except News.DoesNotExist:
        return JsonResponse({'status': 'error', 'message': 'Noticia no encontrada'})
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)})

def superuser_required(view_func):
    decorated_view = user_passes_test(lambda u: u.is_superuser, login_url='/noticias/login/')(view_func)
    return decorated_view

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
        context['news_user_flags'] = {
            'is_staff': bool(self.request.user.is_staff),
            'default_image_url': static('Img/News_Default.png'),
        }
        context['news_view_mode'] = {'saved_only': self.saved_only}

        return context


@method_decorator(superuser_required, name='dispatch')
class SavedNewsListView(NewsListView):
    template_name = 'news_list.html'
    saved_only = True

@require_GET
@user_passes_test(lambda u: u.is_superuser, login_url='/noticias/login/')
def update_feed(request):
    try:
        # Reintentar completar resúmenes pendientes antes de buscar nuevas
        try:
            retry_summarize_pending(limit=5, days=15)
        except Exception:
            pass
        new_articles = FeedService.fetch_and_save_news(max_ai_items=20)
        _bump_cache_version()
        total_news, total_pages = _get_total_news_and_pages()
        
        return JsonResponse({
            'status': 'success',
            'message': f'Feed actualizado. {new_articles} nuevos artículos obtenidos.',
            'total_news': total_news,
            'total_pages': total_pages
        })
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)})

@require_GET
@user_passes_test(lambda u: u.is_superuser, login_url='/noticias/login/')
def check_new_news(request):
    try:
        cursor = request.GET.get('cursor')
        last_checked = request.GET.get('last_checked')
        saved_only = request.GET.get('saved_only', 'false').lower() == 'true'
        notification_cutoff = _news_notification_cutoff()
        current_time = notification_cutoff.isoformat()
        news_qs = _apply_feed_filters(News.visible.select_related('source'), saved_only=saved_only)
        news_qs = news_qs.filter(created_at__lte=notification_cutoff)
        created_dt, created_id = _parse_created_cursor(cursor)

        if created_dt and created_id is not None:
            news_qs = news_qs.filter(
                Q(created_at__gt=created_dt) |
                (Q(created_at=created_dt) & Q(id__gt=created_id))
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
        news_cards = [_serialize_news_card(article) for article in new_news]
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
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)})

@require_GET
@user_passes_test(lambda u: u.is_superuser, login_url='/noticias/login/')
def get_news_count(request):
    try:
        saved_only = request.GET.get('saved_only', 'false').lower() == 'true'
        total_news, total_pages = _get_total_news_and_pages(saved_only=saved_only)
        
        return JsonResponse({
            'status': 'success',
            'total_news': total_news,
            'total_pages': total_pages
        })
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)})

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


@require_POST
@user_passes_test(lambda u: u.is_superuser, login_url='/noticias/login/')
def cleanup_old_news(request):
    try:
        days = int(request.POST.get('days', 15))
        removed = purge_old_news(days)
        _bump_cache_version()
        total_news, total_pages = _get_total_news_and_pages()
        return JsonResponse({'status': 'success', 'removed': removed, 'total_news': total_news, 'total_pages': total_pages})
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)})


@require_POST
@user_passes_test(lambda u: u.is_superuser, login_url='/noticias/login/')
def retry_summaries(request):
    try:
        limit = int(request.POST.get('limit', 50))
        days = int(request.POST.get('days', 2))
        processed = retry_summarize_pending(limit=limit, days=days)
        return JsonResponse({'status': 'success', 'processed': processed})
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)})


@require_GET
@user_passes_test(lambda u: u.is_superuser, login_url='/noticias/login/')
def get_page(request):
    try:
        order = request.GET.get('order', 'desc')
        search_query = request.GET.get('q')
        saved_only = request.GET.get('saved_only', 'false').lower() == 'true'
        page = _safe_page(request.GET.get('page', 1))
        cursor = request.GET.get('cursor')

        version = _get_cache_version()
        key_raw = f"{version}|{order}|{search_query or ''}|{page}|{cursor or ''}|{int(saved_only)}"
        cache_key = f"news:page:{hashlib.md5(key_raw.encode('utf-8')).hexdigest()}"
        cached = cache.get(cache_key)
        if cached:
            return JsonResponse(cached)

        payload = _build_page_response(
            order=order,
            page=page,
            cursor=cursor,
            search_query=search_query,
            saved_only=saved_only,
        )
        cache.set(cache_key, payload, PAGE_CACHE_TTL)
        return JsonResponse(payload)
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)})


@require_POST
@user_passes_test(lambda u: u.is_superuser, login_url='/noticias/login/')
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
            'card': _serialize_news_card(news),
            'total_news': total_news,
            'total_pages': total_pages
        })
    except News.DoesNotExist:
        return JsonResponse({'status': 'error', 'message': 'Noticia no encontrada'})
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)})


@require_GET
@user_passes_test(lambda u: u.is_superuser, login_url='/noticias/login/')
def latest_deleted_news(request):
    try:
        saved_only = request.GET.get('saved_only', 'false').lower() == 'true'
        search_query = (request.GET.get('q') or '').strip() or None

        deleted_qs = News.objects.select_related('source').filter(
            is_deleted=True,
            is_saved=saved_only,
            is_filtered=False,
            is_ai_filtered=False,
            is_redundant=False,
        )
        if search_query:
            deleted_qs = deleted_qs.filter(
                Q(title__icontains=search_query) | Q(description__icontains=search_query)
            )

        latest = deleted_qs.order_by('-deleted_at', '-id').first()
        if not latest:
            return JsonResponse({'status': 'empty'})

        return JsonResponse({
            'status': 'success',
            'news_id': latest.id,
            'card': _serialize_news_card(latest),
        })
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)})


@require_POST
@user_passes_test(lambda u: u.is_superuser, login_url='/noticias/login/')
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
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)})



@require_GET
@superuser_required
def test_redundancy(request):
    """Vista para probar la detección de redundancia en noticias"""
    try:
        # Obtener fecha seleccionada o fecha de hoy
        bogota_tz = pytz.timezone('America/Bogota')
        selected_date_str = request.GET.get('date')

        if selected_date_str:
            try:
                selected_date = timezone.datetime.strptime(selected_date_str, '%Y-%m-%d').date()
            except ValueError:
                selected_date = timezone.now().astimezone(bogota_tz).date()
        else:
            selected_date = timezone.now().astimezone(bogota_tz).date()

        # Convertir a UTC para consultas
        today_start_utc = bogota_tz.localize(timezone.datetime.combine(selected_date, timezone.datetime.min.time())).astimezone(pytz.utc)
        today_end_utc = bogota_tz.localize(timezone.datetime.combine(selected_date, timezone.datetime.max.time())).astimezone(pytz.utc)

        # Queryset base para noticias creadas hoy
        news_today_qs = News.objects.filter(
            created_at__gte=today_start_utc,
            created_at__lte=today_end_utc
        )
        total_today = news_today_qs.count()

        # Obtener noticias redundantes del día (para mostrar la lista)
        redundant_news_today_list = News.objects.filter(
            is_redundant=True,
            similar_to__isnull=False,
            created_at__gte=today_start_utc,
            created_at__lte=today_end_utc
        ).select_related('similar_to', 'source', 'similar_to__source').order_by('-created_at')

        # Obtener listas de noticias para cada pestaña
        # 1. Noticias filtradas por keywords (pero no redundantes ni IA)
        keyword_filtered_news = news_today_qs.filter(
            filtered_by__isnull=False,
            is_redundant=False,
            is_ai_filtered=False
        ).select_related('source', 'filtered_by').order_by('-created_at')

        # 2. Noticias filtradas por IA (pero no redundantes)
        ai_filtered_news = news_today_qs.filter(
            is_ai_filtered=True,
            is_redundant=False
        ).select_related('source').order_by('-created_at')

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
            'redundant_news': redundant_news_today_list, # Lista para mostrar abajo
            'keyword_filtered_news': keyword_filtered_news,  # Nueva variable para la pestaña de keywords
            'ai_filtered_news': ai_filtered_news,  # Nueva variable para la pestaña de IA
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

@require_GET
@superuser_required
def generate_embeddings(request):
    """Indexa noticias visibles recientes en Qdrant sin guardar vectores en SQLite."""
    try:
        gemini_client = FeedService.initialize_gemini()
        vector_index = FeedService.initialize_vector_index()
        if vector_index is None:
            return JsonResponse({'status': 'error', 'message': 'Qdrant no disponible'})

        news_to_index = News.visible.order_by('-published_date')[:50]

        processed_count = 0
        for news in news_to_index:
            content = f"{news.title} {news.description}"
            embedding = EmbeddingService.generate_embedding(content, gemini_client)
            if not embedding:
                continue

            vector_index.ensure_collection(len(embedding))
            payload = {
                'news_id': news.id,
                'source_id': news.source_id,
                'published_ts': int(news.published_date.timestamp()) if news.published_date else int(time.time()),
                'is_filtered': False,
                'is_redundant': False,
                'model_version': getattr(settings, 'GEMINI_EMBEDDING_MODEL', 'gemini-embedding-001'),
            }
            vector_index.upsert(news.guid, embedding, payload)
            processed_count += 1
        
        return JsonResponse({
            'status': 'success',
            'processed_count': processed_count,
            'remaining': None
        })
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)})

@require_GET
@superuser_required
def check_all_redundancy(request):
    """Verifica redundancia en noticias visibles usando Qdrant."""
    try:
        gemini_client = FeedService.initialize_gemini()
        vector_index = FeedService.initialize_vector_index()

        news_to_check = News.visible.select_related('source').order_by('-published_date')[:100]
        
        redundant_count = 0
        for news in news_to_check:
            is_redundant, similar_news, similarity_score = EmbeddingService.check_redundancy(
                news, gemini_client, vector_index=vector_index
            )
            
            if is_redundant and similar_news:
                news.is_redundant = True
                news.is_filtered = True  # Usamos is_filtered en lugar de is_deleted
                news.similar_to = similar_news
                news.similarity_score = similarity_score
                news.save()
                redundant_count += 1
        if redundant_count:
            _bump_cache_version()
        
        return JsonResponse({
            'status': 'success',
            'redundant_count': redundant_count,
            'total_checked': len(news_to_check)
        })
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)})


@require_GET
@user_passes_test(lambda u: u.is_superuser, login_url='/noticias/login/')
def system_stats(request):
    """Vista para mostrar estadísticas del sistema Raspberry Pi"""
    stats = {}
    is_raspberry_pi = False
    error_message = None

    try:
        # Detectar si estamos en Raspberry Pi
        system_info = platform.uname()
        is_raspberry_pi = 'arm' in system_info.machine.lower() or 'aarch64' in system_info.machine.lower()

        if is_raspberry_pi:
            # Temperatura
            try:
                result = subprocess.run(['/usr/bin/vcgencmd', 'measure_temp'],
                                      capture_output=True, text=True, timeout=5)
                if result.returncode == 0:
                    temp_str = result.stdout.strip().replace("temp=", "").replace("'C", "")
                    stats['temperature'] = f"{temp_str}°C"
            except Exception as e:
                stats['temperature'] = f"Error: {str(e)}"

            # Voltaje del núcleo
            try:
                result = subprocess.run(['/usr/bin/vcgencmd', 'measure_volts', 'core'],
                                      capture_output=True, text=True, timeout=5)
                if result.returncode == 0:
                    stats['voltage'] = result.stdout.strip().replace("volt=", "")
            except Exception as e:
                stats['voltage'] = f"Error: {str(e)}"

            # Frecuencia del CPU
            try:
                result = subprocess.run(['/usr/bin/vcgencmd', 'measure_clock', 'arm'],
                                      capture_output=True, text=True, timeout=5)
                if result.returncode == 0:
                    freq_hz = int(result.stdout.strip().split('=')[1])
                    freq_mhz = freq_hz / 1000000
                    stats['cpu_frequency'] = f"{freq_mhz:.0f} MHz"
            except Exception as e:
                stats['cpu_frequency'] = f"Error: {str(e)}"

            # Memoria
            try:
                result = subprocess.run(['/usr/bin/vcgencmd', 'get_mem', 'arm'],
                                      capture_output=True, text=True, timeout=5)
                if result.returncode == 0:
                    stats['memory_arm'] = result.stdout.strip().replace("arm=", "")

                result = subprocess.run(['/usr/bin/vcgencmd', 'get_mem', 'gpu'],
                                      capture_output=True, text=True, timeout=5)
                if result.returncode == 0:
                    stats['memory_gpu'] = result.stdout.strip().replace("gpu=", "")
            except Exception as e:
                stats['memory_arm'] = f"Error: {str(e)}"

            # Throttling (si el Pi está limitando rendimiento por temperatura/voltaje)
            try:
                result = subprocess.run(['/usr/bin/vcgencmd', 'get_throttled'],
                                      capture_output=True, text=True, timeout=5)
                if result.returncode == 0:
                    throttled_hex = result.stdout.strip().split('=')[1]
                    throttled_val = int(throttled_hex, 16)
                    if throttled_val == 0:
                        stats['throttled'] = "No hay limitaciones"
                    else:
                        issues = []
                        if throttled_val & 0x1: issues.append("Under-voltage detectado")
                        if throttled_val & 0x2: issues.append("Límite de frecuencia ARM")
                        if throttled_val & 0x4: issues.append("Actualmente limitado")
                        if throttled_val & 0x8: issues.append("Soft temperature limit activo")
                        if throttled_val & 0x10000: issues.append("Under-voltage ha ocurrido")
                        if throttled_val & 0x20000: issues.append("Límite de frecuencia ARM ha ocurrido")
                        if throttled_val & 0x40000: issues.append("Throttling ha ocurrido")
                        if throttled_val & 0x80000: issues.append("Soft temperature limit ha ocurrido")
                        stats['throttled'] = ", ".join(issues)
            except Exception as e:
                stats['throttled'] = f"Error: {str(e)}"
        else:
            error_message = "Este sistema no es un Raspberry Pi. Las estadísticas de vcgencmd no están disponibles."

        # Información del sistema (disponible en cualquier plataforma)
        stats['system'] = f"{system_info.system} {system_info.release}"
        stats['machine'] = system_info.machine
        stats['hostname'] = system_info.node

        # Uptime (intentar obtener en Linux)
        try:
            with open('/proc/uptime', 'r') as f:
                uptime_seconds = float(f.readline().split()[0])
            total_minutes, _ = divmod(int(uptime_seconds), 60)
            total_hours, minutes = divmod(total_minutes, 60)
            total_days, hours = divmod(total_hours, 24)
            months, rest_days = divmod(total_days, 30)
            weeks, days = divmod(rest_days, 7)
            parts = []
            if months:
                parts.append(f"{months} mes" if months == 1 else f"{months} meses")
            if weeks:
                parts.append(f"{weeks} semana" if weeks == 1 else f"{weeks} semanas")
            if days:
                parts.append(f"{days} día" if days == 1 else f"{days} días")
            if hours:
                parts.append(f"{hours}h")
            parts.append(f"{minutes}m")
            stats['uptime'] = ' '.join(parts)
        except Exception:
            stats['uptime'] = "N/A"

        # Carga del sistema
        try:
            with open('/proc/loadavg', 'r') as f:
                load_avg = f.readline().split()[:3]
                stats['load_average'] = f"{load_avg[0]} {load_avg[1]} {load_avg[2]}"
        except Exception:
            stats['load_average'] = "N/A"

    except Exception as e:
        error_message = f"Error al obtener estadísticas: {str(e)}"

    context = {
        'stats': stats,
        'is_raspberry_pi': is_raspberry_pi,
        'error_message': error_message,
    }

    return render(request, 'system_stats.html', context)


# Vista de Login Personalizada
class NewsLoginView(LoginView):
    template_name = 'news_login.html' # Apuntar al archivo creado por el usuario
    redirect_authenticated_user = True # Redirigir si ya está autenticado
    next_page = '/noticias/' # Sin esto Django redirige a /accounts/profile/ (404)


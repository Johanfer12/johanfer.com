from django.shortcuts import render
from django.views.generic import ListView
from .models import News, FeedSource
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
import pytz
from django.db.models import Q, Count
from .tasks import purge_old_news, retry_summarize_pending
import subprocess
import platform
import hashlib
from urllib.parse import urlparse
from urllib.request import Request, urlopen

# Create your views here.
PAGE_SIZE = 25
COUNT_CACHE_TTL = 20
PAGE_CACHE_TTL = 20
CACHE_VERSION_KEY = 'news_feed_cache_version'


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


def _get_total_news_and_pages(search_query=None, saved_only=False):
    key = _counts_cache_key(search_query, saved_only=saved_only)
    cached = cache.get(key)
    if cached:
        return cached

    count_qs = News.visible
    if saved_only:
        count_qs = count_qs.filter(is_saved=True)
    else:
        count_qs = count_qs.filter(is_saved=False)
    if search_query:
        count_qs = count_qs.filter(Q(title__icontains=search_query) | Q(description__icontains=search_query))
    total_news = count_qs.count()
    total_pages = (total_news + (PAGE_SIZE - 1)) // PAGE_SIZE
    result = (total_news, total_pages)
    cache.set(key, result, COUNT_CACHE_TTL)
    return result


def _serialize_news_card(article):
    published_local = timezone.localtime(article.published_date) if article.published_date else None
    created_local = timezone.localtime(article.created_at) if article.created_at else None
    return {
        'id': article.id,
        'title': article.title or '',
        'description_html': article.description or '',
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


def _build_page_response(*, order, page, cursor, search_query, backup_only=False, saved_only=False):
    base_qs = News.visible.select_related('source')
    if saved_only:
        base_qs = base_qs.filter(is_saved=True)
    else:
        base_qs = base_qs.filter(is_saved=False)
    if search_query:
        base_qs = base_qs.filter(
            Q(title__icontains=search_query) | Q(description__icontains=search_query)
        )

    if order == 'asc':
        base_qs = base_qs.order_by('published_date', 'id')
    else:
        base_qs = base_qs.order_by('-published_date', '-id')

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
            prev_slice = list(base_qs[:anchor_idx + 1])
            if prev_slice:
                anchor = prev_slice[-1]
                if order == 'asc':
                    key_q = Q(published_date__gt=anchor.published_date) | (Q(published_date=anchor.published_date) & Q(id__gt=anchor.id))
                else:
                    key_q = Q(published_date__lt=anchor.published_date) | (Q(published_date=anchor.published_date) & Q(id__lt=anchor.id))
                base_qs = base_qs.filter(key_q)

    window_qs = base_qs

    if backup_only:
        backup_items = list(window_qs[:PAGE_SIZE])
        backup_cards = [_serialize_news_card(article) for article in backup_items]
        backup_next_cursor = None
        if backup_items:
            last_backup = backup_items[-1]
            backup_next_cursor = f"{last_backup.published_date.isoformat()}|{last_backup.id}"
        total_news, total_pages = _get_total_news_and_pages(search_query, saved_only=saved_only)
        return {
            'status': 'success',
            'backup_cards': backup_cards,
            'backup_next_cursor': backup_next_cursor,
            'total_news': total_news,
            'total_pages': total_pages,
            'order': order
        }

    items = list(window_qs[:PAGE_SIZE + 1])
    has_more = len(items) > PAGE_SIZE
    items = items[:PAGE_SIZE]
    cards = [_serialize_news_card(article) for article in items]

    next_cursor = None
    if has_more:
        last = items[-1]
        next_cursor = f"{last.published_date.isoformat()}|{last.id}"

    backup_size = PAGE_SIZE if page == 1 else 5
    backup_items = list(window_qs[PAGE_SIZE:PAGE_SIZE + backup_size])
    backup_cards = [_serialize_news_card(article) for article in backup_items]

    backup_next_cursor = None
    if backup_items:
        last_backup = backup_items[-1]
        backup_next_cursor = f"{last_backup.published_date.isoformat()}|{last_backup.id}"

    total_news, total_pages = _get_total_news_and_pages(search_query, saved_only=saved_only)
    return {
        'status': 'success',
        'cards': cards,
        'next_cursor': next_cursor,
        'backup_cards': backup_cards,
        'backup_next_cursor': backup_next_cursor,
        'total_news': total_news,
        'total_pages': total_pages,
        'order': order
    }

@require_POST
def delete_news(request, pk):
    try:
        current_page = _safe_page(request.POST.get('current_page', 1))
        order = request.POST.get('order', 'desc')
        saved_only = request.POST.get('saved_only', 'false').lower() == 'true'
        news = News.objects.get(pk=pk)
        news.is_deleted = True
        news.save(update_fields=['is_deleted'])
        _bump_cache_version()
        
        # Obtener la siguiente noticia para reemplazar la eliminada
        next_news = None
        total_news, total_pages = _get_total_news_and_pages(saved_only=saved_only)
        
        # Buscar noticia de reemplazo por keyset para mantener orden estable (siempre, también en descendente página 1)
        base_qs = News.visible
        if saved_only:
            base_qs = base_qs.filter(is_saved=True)
        else:
            base_qs = base_qs.filter(is_saved=False)
        base_qs = base_qs.order_by('published_date', 'id') if order == 'asc' else base_qs.order_by('-published_date', '-id')
        page_start = (current_page - 1) * PAGE_SIZE
        page_qs = list(base_qs[page_start:page_start + PAGE_SIZE])
        if page_qs:
            anchor = page_qs[-1]
            if order == 'asc':
                keyset_q = (
                    Q(published_date__gt=anchor.published_date) |
                    (Q(published_date=anchor.published_date) & Q(id__gt=anchor.id))
                )
                ordering = ('published_date', 'id')
            else:
                keyset_q = (
                    Q(published_date__lt=anchor.published_date) |
                    (Q(published_date=anchor.published_date) & Q(id__lt=anchor.id))
                )
                ordering = '-published_date', '-id'
            next_qs = News.visible
            if saved_only:
                next_qs = next_qs.filter(is_saved=True)
            else:
                next_qs = next_qs.filter(is_saved=False)
            next_news = next_qs.filter(keyset_q).order_by(*ordering).first()
        
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

@method_decorator(superuser_required, name='dispatch')
class NewsListView(ListView):
    model = News
    template_name = 'news_list.html'
    paginate_by = 25

    def get_queryset(self):
        # Usar el manager optimizado + búsqueda y orden dinámico
        order = self.request.GET.get('order', 'desc')
        search_query = self.request.GET.get('q')

        queryset = News.visible.select_related('source').filter(is_saved=False)
        if search_query:
            queryset = queryset.filter(
                Q(title__icontains=search_query) | Q(description__icontains=search_query)
            )

        if order == 'asc':
            queryset = queryset.order_by('published_date', 'id')
        else:
            queryset = queryset.order_by('-published_date', '-id')

        return queryset
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
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
            
        # Obtener noticias de respaldo (5 adicionales) por keyset (cursor) a partir del último ítem de la página
        order = self.request.GET.get('order', 'desc')
        ordering = 'published_date' if order == 'asc' else '-published_date'
        current_queryset = self.get_queryset()
        page_qs = list(current_queryset[(current_page - 1) * PAGE_SIZE: (current_page - 1) * PAGE_SIZE + PAGE_SIZE])
        last_item = page_qs[-1] if page_qs else None  # último en la página independientemente del orden
        backup_news = []
        if last_item:
            if order == 'asc':
                backup_q = (
                    Q(published_date__gt=last_item.published_date) |
                    (Q(published_date=last_item.published_date) & Q(id__gt=last_item.id))
                )
            else:
                backup_q = (
                    Q(published_date__lt=last_item.published_date) |
                    (Q(published_date=last_item.published_date) & Q(id__lt=last_item.id))
                )
            backup_news = current_queryset.filter(backup_q).order_by(ordering)[:5]
        
        # Noticias de respaldo serializadas para JavaScript
        backup_cards = [_serialize_news_card(article) for article in backup_news]
        
        context['backup_cards'] = backup_cards
        context['current_page'] = current_page
        context['order'] = order
        latest_created = current_queryset.order_by('-created_at', '-id').values_list('created_at', 'id').first()
        context['initial_news_cursor'] = f"{latest_created[0].isoformat()}|{latest_created[1]}" if latest_created else None
        context['news_user_flags'] = {
            'is_staff': bool(self.request.user.is_staff),
            'default_image_url': static('Img/News_Default.png'),
        }
        context['news_view_mode'] = {'saved_only': False}
        
        return context


@method_decorator(superuser_required, name='dispatch')
class SavedNewsListView(NewsListView):
    template_name = 'news_list.html'

    def get_queryset(self):
        order = self.request.GET.get('order', 'desc')
        search_query = self.request.GET.get('q')

        queryset = News.visible.select_related('source').filter(is_saved=True)
        if search_query:
            queryset = queryset.filter(
                Q(title__icontains=search_query) | Q(description__icontains=search_query)
            )

        if order == 'asc':
            queryset = queryset.order_by('published_date', 'id')
        else:
            queryset = queryset.order_by('-published_date', '-id')

        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['news_view_mode'] = {'saved_only': True}
        return context

@require_GET
def update_feed(request):
    try:
        # Reintentar completar resúmenes pendientes antes de buscar nuevas
        try:
            retry_summarize_pending(limit=50, days=15)
        except Exception as _:
            pass
        new_articles = FeedService.fetch_and_save_news()
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
def check_new_news(request):
    try:
        cursor = request.GET.get('cursor')
        last_checked = request.GET.get('last_checked')
        current_time = timezone.now().isoformat()
        news_qs = News.visible.select_related('source')
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

        total_news, total_pages = _get_total_news_and_pages()
        
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
def get_page(request):
    try:
        order = request.GET.get('order', 'desc')
        search_query = request.GET.get('q')
        backup_only = request.GET.get('backup_only', 'false').lower() == 'true'
        saved_only = request.GET.get('saved_only', 'false').lower() == 'true'
        page = _safe_page(request.GET.get('page', 1))
        cursor = request.GET.get('cursor')

        version = _get_cache_version()
        key_raw = f"{version}|{order}|{search_query or ''}|{page}|{cursor or ''}|{int(backup_only)}|{int(saved_only)}"
        cache_key = f"news:page:{hashlib.md5(key_raw.encode('utf-8')).hexdigest()}"
        cached = cache.get(cache_key)
        if cached:
            return JsonResponse(cached)

        payload = _build_page_response(
            order=order,
            page=page,
            cursor=cursor,
            search_query=search_query,
            backup_only=backup_only,
            saved_only=saved_only,
        )
        cache.set(cache_key, payload, PAGE_CACHE_TTL)
        return JsonResponse(payload)
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)})


@require_POST
def undo_delete(request, pk):
    try:
        saved_only = request.POST.get('saved_only', 'false').lower() == 'true'
        news = News.objects.get(pk=pk)
        if news.is_deleted:
            news.is_deleted = False
            # Restauramos cualquier marca de filtrado manual
            news.is_filtered = False
            news.is_ai_filtered = False
            news.is_redundant = False
            news.save()
            _bump_cache_version()

        total_news, total_pages = _get_total_news_and_pages(saved_only=saved_only)

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


@require_POST
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
                 print(f"Advertencia [LOGICA EXCLUSIVA]: Suma ({calculated_total}) no coincide con total ({total_today}).")
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

        # Calcular estadísticas de redundancia por fuente
        source_stats = []
        sources = FeedSource.objects.filter(active=True)

        for source in sources:
            # Total de noticias de esta fuente hoy
            source_total_today = news_today_qs.filter(source=source).count()

            if source_total_today > 0:
                # Noticias redundantes de esta fuente hoy
                source_redundant_today = news_today_qs.filter(
                    source=source,
                    is_redundant=True
                ).count()

                # Calcular porcentaje de redundancia
                redundancy_percentage = (source_redundant_today / source_total_today) * 100

                source_stats.append({
                    'name': source.name,
                    'total_today': source_total_today,
                    'redundant_today': source_redundant_today,
                    'redundancy_percentage': redundancy_percentage,
                    'non_redundant_today': source_total_today - source_redundant_today
                })

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
        # Considera loguear el error aquí para depuración
        print(f"Error en test_redundancy: {str(e)}") # Log simple
        # Podrías devolver una página de error o un JsonResponse
        # Para mantener la consistencia con la plantilla, podrías renderizarla con un mensaje de error
        return render(request, 'redundancy_test.html', {'error_message': f'Ocurrió un error: {str(e)}'})

@require_GET
def generate_embeddings(request):
    """Vista para generar embeddings para noticias existentes"""
    try:
        # Inicializar modelo
        embedding_model_name = EmbeddingService.initialize_embedding_model()
        
        # Obtener noticias sin embedding usando el manager visible
        news_without_embedding = News.visible.filter(
            embedding__isnull=True
        ).order_by('-published_date')[:50]  # Limitar a 50 para evitar sobrecarga
        
        processed_count = 0
        for news in news_without_embedding:
            # Combinar título y descripción para el embedding
            content = f"{news.title} {news.description}"
            embedding = EmbeddingService.generate_embedding(content, embedding_model_name)
            
            if embedding:
                news.embedding = embedding
                news.save(update_fields=['embedding'])
                processed_count += 1
        
        return JsonResponse({
            'status': 'success',
            'processed_count': processed_count,
            'remaining': News.visible.filter(embedding__isnull=True).count()
        })
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)})

@require_GET
def check_all_redundancy(request):
    """Vista para verificar redundancia en todas las noticias con embeddings"""
    try:
        # Inicializar modelo
        embedding_model_name = EmbeddingService.initialize_embedding_model()
        
        # Obtener noticias no marcadas como redundantes usando el manager visible
        news_to_check = News.visible.filter(
            embedding__isnull=False
        ).order_by('-published_date')[:100]  # Limitar a 100 para evitar sobrecarga
        
        redundant_count = 0
        for news in news_to_check:
            is_redundant, similar_news, similarity_score = EmbeddingService.check_redundancy(
                news, embedding_model_name
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
                uptime_hours = int(uptime_seconds // 3600)
                uptime_minutes = int((uptime_seconds % 3600) // 60)
                stats['uptime'] = f"{uptime_hours}h {uptime_minutes}m"
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


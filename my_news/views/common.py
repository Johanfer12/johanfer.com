"""Piezas que comparten las vistas del feed: caché de recuentos, filtros y
tarjetas serializadas.
"""
import hashlib
import logging
from datetime import datetime, time as datetime_time, timedelta

from django.core.cache import cache
from django.db.models import Q
from django.http import JsonResponse
from django.template.loader import render_to_string
from django.utils import timezone

from ..models import News

logger = logging.getLogger(__name__)


def _json_server_error(request):
    """Respuesta de un endpoint JSON que ha fallado.

    Se registra la traza, que antes se perdía, y al navegador va un 500 con un
    mensaje genérico en vez del texto de la excepción.
    """
    logger.exception('Fallo en %s %s', request.method, request.path)
    return JsonResponse({'status': 'error', 'message': 'Error interno del servidor.'}, status=500)


PAGE_SIZE = 25


# TTL corto: el caché es LocMem (independiente por worker de gunicorn y por
# proceso), así que la invalidación por versión no cruza procesos. Con 5s la
# ventana de datos desactualizados queda acotada a algo imperceptible.
COUNT_CACHE_TTL = 5


PAGE_CACHE_TTL = 5


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


def _apply_feed_filters(qs, *, saved_only=False, search_query=None, order=None):
    """Filtros comunes del feed: guardadas, búsqueda y orden keyset."""
    qs = qs.filter(is_saved=saved_only)
    if search_query:
        qs = qs.filter(
            Q(title__icontains=search_query)
            | Q(title_es__icontains=search_query)
            | Q(description__icontains=search_query)
        )
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


def _collapse_html_whitespace(html):
    """Quita la sangría que los ``{% if %}`` de la plantilla dejan por medio.

    Cada línea se queda sin espacios a los lados y las vacías se caen. HTML
    colapsa cualquier racha de espacios en uno solo, y entre dos líneas sigue
    quedando el salto, así que lo que se ve no cambia. Es seguro porque el
    marcado de la tarjeta no tiene ``pre`` ni ``textarea`` (ver ALLOWED_TAGS
    del sanitizador), que son los únicos sitios donde el espacio contaría.

    Sin esto la tarjeta ocupa un 18% más: la plantilla está indentada para
    leerse, no para viajar.
    """
    return "\n".join(
        stripped for line in html.splitlines() if (stripped := line.strip())
    )


def _card_render_flags(request):
    """Los mismos indicadores con los que news_list.html incluye news_grid.html.

    Tienen que coincidir: una tarjeta que llega por JSON acaba al lado de las
    que pintó la plantilla, y cualquier diferencia se vería como dos estilos
    de tarjeta en la misma rejilla.
    """
    return {
        'card_id_prefix': 'news',
        'show_save_button': True,
        'show_delete_button': bool(request.user.is_staff),
        'show_similarity_score': True,
    }


def _serialize_news_card(article, request):
    """Tarjeta lista para insertar en la rejilla, más lo que el JS necesita.

    El HTML lo pinta ``news_card.html``, la misma plantilla que usa la carga
    inicial de la página. Antes había una segunda copia del marcado dentro de
    ``news_script.js`` y las dos habían empezado a divergir.

    No se pasa ``request`` a ``render_to_string`` a propósito: la plantilla no
    lo usa, y hacerlo ejecutaría los context processors una vez por tarjeta.
    """
    html = render_to_string(
        'news_card.html',
        {'article': article, **_card_render_flags(request)},
    )
    return {
        'id': article.id,
        # Sellos de tiempo que el JS lee del dataset para ordenar, deduplicar
        # y decidir si una noticia nueva entra en la página visible.
        'published_at': article.published_date.isoformat() if article.published_date else None,
        'created_at': article.created_at.isoformat() if article.created_at else None,
        'html': _collapse_html_whitespace(html),
    }

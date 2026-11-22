"""Comentarios de una noticia, extraídos bajo demanda del sitio de origen."""
import logging
import time

from django.core.cache import cache
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.http import require_GET

from ..comment_extractors import (
    CommentExtractionError,
    extract_comments,
    supports_comment_extraction,
)
from ..models import News
from .common import _public_news_filter

logger = logging.getLogger(__name__)


# Los comentarios se consultan bajo demanda a sitios externos. Diez minutos
# reducen consultas repetidas sin dejar el modal desactualizado durante horas.
COMMENTS_CACHE_TTL = 600


@require_GET
def news_comments(request, pk):
    queryset = News.objects.select_related('source')
    if not (request.user.is_authenticated and request.user.is_superuser):
        queryset = queryset.filter(_public_news_filter())

    article = get_object_or_404(queryset, pk=pk)
    if not supports_comment_extraction(article.link):
        return JsonResponse(
            {'status': 'unsupported', 'message': 'Esta fuente no tiene extractor de comentarios.'},
            status=404,
        )

    cache_key = f"news:comments:{article.id}"
    cached = cache.get(cache_key)
    if cached is not None:
        response = JsonResponse(cached)
        response['X-Comments-Cache'] = 'HIT'
        return response

    started_at = time.monotonic()
    try:
        result = extract_comments(
            article.link,
            guid=article.guid,
            title=article.title,
        )
    except CommentExtractionError as exc:
        logger.warning("No se pudieron extraer comentarios de la noticia %s: %s", article.id, exc)
        return JsonResponse(
            {'status': 'error', 'message': str(exc)},
            status=502,
        )
    except Exception:
        logger.exception("Error inesperado extrayendo comentarios de la noticia %s", article.id)
        return JsonResponse(
            {'status': 'error', 'message': 'No se pudieron cargar los comentarios.'},
            status=502,
        )

    payload = {
        'status': 'success',
        'title': article.display_title,
        'article_url': article.link,
        **result,
    }
    cache.set(cache_key, payload, COMMENTS_CACHE_TTL)
    response = JsonResponse(payload)
    response['X-Comments-Cache'] = 'MISS'
    response['Server-Timing'] = f"comments;dur={(time.monotonic() - started_at) * 1000:.1f}"
    return response

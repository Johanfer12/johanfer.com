"""El botón de actualizar: lanza la pasada de ingesta en un proceso aparte y
responde a las preguntas del navegador sobre cómo va.
"""
import logging
import subprocess
import sys

from django.conf import settings
from django.http import JsonResponse
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.views.decorators.http import require_GET, require_POST

from Bookshelf.http_utils import superuser_required

from ..ingestion_status import current_status
from ..locks import news_update_running
from .common import _bump_cache_version, _get_total_news_and_pages

logger = logging.getLogger(__name__)


# La pasada que lanza el botón de actualizar. Antes corría dentro de la
# petición, y una pasada tarda de uno a cinco minutos (264 s medidos con Gemini
# dando 503 y Groq esperando su cuota por minuto): nginx corta a los 60 s con un
# 504 y el botón daba error aunque la pasada terminara bien por detrás. Además
# no tomaba el cerrojo del cron, así que podía solaparse con él, y cargaba en el
# proceso web los clientes de IA que se importan tarde precisamente para que
# gunicorn no los pague.
#
# Ahora es un proceso aparte (``manage.py update_news``) y el navegador pregunta
# por ``update_feed_status`` hasta que ``IngestionStatus`` cambia. Se guarda la
# referencia para recoger el proceso al terminar y que no quede un zombi, y su
# hora de arranque para no achacar a un clic nuevo el fallo de uno anterior.
_manual_update_process = None


_manual_update_started = None


def _manual_update_alive():
    """Recoge el proceso lanzado desde el feed; devuelve si sigue vivo."""
    proc = _manual_update_process
    return proc is not None and proc.poll() is None


def _launch_manual_update(started_at):
    global _manual_update_process, _manual_update_started
    _manual_update_started = started_at
    log = open(settings.CRON_LOG_PATH, 'ab')
    try:
        _manual_update_process = subprocess.Popen(
            [sys.executable, str(settings.BASE_DIR / 'manage.py'), 'update_news'],
            cwd=str(settings.BASE_DIR),
            stdin=subprocess.DEVNULL,
            stdout=log,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
    finally:
        # El hijo ya tiene su copia del descriptor.
        log.close()


@require_POST
@superuser_required
def update_feed(request):
    started_at = timezone.now()
    if _manual_update_alive() or news_update_running():
        # Ya hay una pasada en marcha (del cron o de otro clic): no se lanza
        # otra, se espera a que esa deje su estado.
        return JsonResponse({'status': 'running', 'since': started_at.isoformat()})
    try:
        _launch_manual_update(started_at)
    except Exception:
        logger.exception("No se pudo lanzar la actualización manual de noticias")
        return JsonResponse({'status': 'error', 'message': 'No se pudo lanzar la actualización.'}, status=500)
    return JsonResponse({'status': 'started', 'since': started_at.isoformat()})


@require_GET
@superuser_required
def update_feed_status(request):
    since = parse_datetime(request.GET.get('since') or '')
    if since is None:
        return JsonResponse({'status': 'error', 'message': 'Falta el parámetro since.'}, status=400)

    status = current_status()
    if status is not None and status.updated_at >= since:
        # La pasada corrió en otro proceso: su caché LocMem no es el de aquí.
        _bump_cache_version()
        total_news, total_pages = _get_total_news_and_pages()
        return JsonResponse({
            'status': 'done',
            'state': status.state,
            'reason': status.reason,
            'new_count': status.new_count,
            'total_news': total_news,
            'total_pages': total_pages,
        })

    proc = _manual_update_process
    own_launch = _manual_update_started is not None and _manual_update_started >= since
    if own_launch and not _manual_update_alive() and proc.returncode:
        # Murió antes de poder anotar nada (p. ej. al importar).
        return JsonResponse({
            'status': 'done',
            'state': 'error',
            'reason': f'La actualización terminó con código {proc.returncode}; ver el log del cron.',
        })
    return JsonResponse({'status': 'running'})

"""Estado de la última pasada de ingesta, escrito por el cron y leído por el feed.

Antes, si la ingesta se paraba (cuota de la IA agotada, proveedor caído), lo
único que se veía era un feed que dejaba de crecer. Averiguar el motivo exigía
entrar por SSH a leer el log del cron. Aquí se deja anotado el resultado de cada
pasada para poder verlo desde la propia página.

Va en la base de datos y no en caché a propósito: el caché por defecto es
LocMem, privado de cada proceso, y el cron es un proceso distinto del de
gunicorn. Lo que escribiera el cron no lo vería nunca la web.
"""

import logging
from datetime import timedelta

from django.utils import timezone

from .models import IngestionStatus

logger = logging.getLogger(__name__)

# Franja en la que el cron de noticias debería estar corriendo (ver CRONJOBS en
# settings: cada 30 minutos de 08 a 21, más una última pasada a las 22).
CRON_ACTIVE_HOURS = (8, 22)

# El cron corre cada 30 minutos. Con margen para una pasada lenta, pasada esta
# holgura sin noticias frescas hay que sospechar que no está corriendo.
SILENCE_THRESHOLD = timedelta(minutes=75)


def _record(state, reason='', detail='', new_count=0, retry_at=None):
    """Guarda el resultado de la pasada; nunca interrumpe la ingesta si falla."""
    try:
        IngestionStatus.objects.update_or_create(
            pk=IngestionStatus.SINGLETON_PK,
            defaults={
                'state': state,
                'reason': reason[:200],
                'detail': (detail or '')[:2000],
                'new_count': new_count,
                'retry_at': retry_at,
            },
        )
    except Exception:
        # Anotar el estado es diagnóstico: que no tumbe la pasada que sí funciona.
        logger.exception("No se pudo registrar el estado de la ingesta")


def report_ok(new_count=0):
    _record(IngestionStatus.STATE_OK, new_count=new_count)


def report_paused(reason, detail='', new_count=0, retry_at=None):
    _record(
        IngestionStatus.STATE_PAUSED,
        reason=reason,
        detail=detail,
        new_count=new_count,
        retry_at=retry_at,
    )


def report_error(reason, detail=''):
    _record(IngestionStatus.STATE_ERROR, reason=reason, detail=detail)


def current_status():
    """Devuelve la fila de estado, o ``None`` si aún no se ha escrito ninguna."""
    try:
        return IngestionStatus.objects.filter(pk=IngestionStatus.SINGLETON_PK).first()
    except Exception:
        logger.exception("No se pudo leer el estado de la ingesta")
        return None


def _in_cron_hours(moment):
    start, end = CRON_ACTIVE_HOURS
    return start <= timezone.localtime(moment).hour <= end


def feed_alert():
    """Aviso a mostrar en el feed privado, o ``None`` si todo va bien.

    Cubre dos averías distintas: que la pasada falle (lo dice el estado) y que
    el cron directamente no esté corriendo (lo delata el silencio). La segunda
    no dejaría ninguna huella en la base, así que sin este chequeo un cron
    parado se vería igual que un día tranquilo de noticias.
    """
    status = current_status()
    now = timezone.now()

    if status is None:
        # Sin ninguna pasada registrada no se puede afirmar que algo va mal:
        # es lo que se ve justo después de desplegar esto por primera vez.
        return None

    stale_for = now - status.updated_at
    if stale_for > SILENCE_THRESHOLD and _in_cron_hours(now):
        return {
            'level': 'error',
            'title': 'La actualización de noticias no se está ejecutando',
            'message': (
                f"La última pasada fue {_humanize_delta(stale_for)} y debería "
                "correr cada 30 minutos. Puede que el cron esté parado."
            ),
            'since': status.updated_at,
        }

    if status.state == IngestionStatus.STATE_PAUSED:
        message = status.reason or 'La ingesta se pausó y reintentará más tarde.'
        if status.retry_at and status.retry_at > now:
            message += f" Reintenta {_humanize_until(status.retry_at - now)}."
        return {
            'level': 'warning',
            'title': 'Ingesta de noticias pausada',
            'message': message,
            'detail': status.detail,
            'since': status.updated_at,
        }

    if status.state == IngestionStatus.STATE_ERROR:
        return {
            'level': 'error',
            'title': 'Error en la actualización de noticias',
            'message': status.reason or 'La última pasada terminó con error.',
            'detail': status.detail,
            'since': status.updated_at,
        }

    return None


def _humanize_delta(delta):
    minutes = int(delta.total_seconds() // 60)
    if minutes < 90:
        return f"hace {minutes} minutos"
    hours = minutes // 60
    if hours < 36:
        return f"hace {hours} horas"
    return f"hace {hours // 24} días"


def _humanize_until(delta):
    minutes = int(delta.total_seconds() // 60) + 1
    if minutes < 60:
        return f"en {minutes} minutos"
    hours = minutes // 60
    return f"en {hours} horas" if hours > 1 else "en una hora"

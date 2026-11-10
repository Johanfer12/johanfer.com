from .utils import refresh_books_data
import logging

from django.core.management import call_command


logger = logging.getLogger(__name__)

def update_books_cron():
    """Devuelve si la pasada terminó bien, para que el comando lo traduzca a su código de salida."""
    try:
        refresh_books_data()
        logger.info("Libros actualizados correctamente")
        return True
    except Exception:
        logger.exception("Error actualizando libros")
        return False


def clear_expired_sessions():
    """Borra las sesiones caducadas. Django no lo hace solo.

    El registro de visitas guarda el `visitor_id` en la sesión, así que cada
    visitante sin cookie —cada robot, en la práctica— deja una fila en
    `django_session`. Sin esta limpieza la tabla solo crece: en noviembre de
    2026 tenía 14.257 filas y 12.672 ya estaban caducadas.

    Un fallo aquí no tumba la pasada: es mantenimiento, no la tarea.
    """
    try:
        call_command('clearsessions')
    except Exception:
        logger.exception("Error borrando las sesiones caducadas")

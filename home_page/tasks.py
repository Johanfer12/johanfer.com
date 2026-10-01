from .utils import refresh_books_data
import logging


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

from .utils import refresh_books_data
import logging


logger = logging.getLogger(__name__)

def update_books_cron():
    try:
        refresh_books_data()
        logger.info("Libros actualizados correctamente")
    except Exception:
        logger.exception("Error actualizando libros")

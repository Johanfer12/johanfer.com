from .utils import refresh_watching_data
import logging


logger = logging.getLogger(__name__)


def update_watching_cron():
    try:
        refresh_watching_data()
        logger.info("Historial de Trakt actualizado correctamente")
    except Exception:
        logger.exception("Error actualizando historial de Trakt")

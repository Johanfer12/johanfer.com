from .utils import refresh_watching_data
import logging


logger = logging.getLogger(__name__)


def update_watching_cron():
    try:
        # Crawl completo (sin corte anticipado) para capturar también las entradas
        # con fechas antiguas / importaciones masivas de Trakt, no solo lo reciente.
        created = refresh_watching_data(max_pages=100, stop_when_page_has_no_new=False)
        logger.info("Historial de Trakt actualizado correctamente (%s eventos nuevos)", created)
    except Exception:
        logger.exception("Error actualizando historial de Trakt")

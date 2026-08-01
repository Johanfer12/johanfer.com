from .utils import refresh_watching_from_simkl
import logging


logger = logging.getLogger(__name__)


def update_watching_cron():
    try:
        # Pull completo (full=True): ignora el gate de /sync/activities y pide toda la
        # biblioteca. Es la única forma de detectar lo borrado del otro lado y de captar
        # entradas con fechas viejas, igual que hacía el crawl completo con Trakt.
        # Con una corrida diaria el coste es despreciable.
        created = refresh_watching_from_simkl(full=True)
        logger.info("Historial de Simkl actualizado correctamente (%s eventos nuevos)", created)
    except Exception:
        logger.exception("Error actualizando historial de Simkl")

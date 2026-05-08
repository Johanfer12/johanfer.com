from .utils import refresh_spotify_data
import logging


logger = logging.getLogger(__name__)

def update_spotify_cron():
    try:
        if refresh_spotify_data():
            logger.info("Spotify actualizado correctamente")
        else:
            logger.warning("Spotify no se actualizó; se conserva la información guardada")
    except Exception:
        logger.exception("Error actualizando Spotify")

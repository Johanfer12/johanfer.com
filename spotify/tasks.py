from .utils import refresh_spotify_data
import logging


logger = logging.getLogger(__name__)

def update_spotify_cron():
    try:
        refresh_spotify_data()
        logger.info("Spotify actualizado correctamente")
    except Exception:
        logger.exception("Error actualizando Spotify")

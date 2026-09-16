import logging
import time

import requests

from .utils import refresh_watching_from_simkl


logger = logging.getLogger(__name__)

# Esperas entre reintentos de la pasada, en segundos. Solo se usan cuando falla la
# CONEXIÓN, nunca cuando falla Simkl: el 15/09/2026 la Pi se quedó sin resolución DNS
# justo en ese minuto (el cron de Cloudflare murió igual a la misma hora) y, como esto
# corre una sola vez al día, el historial se quedó 24 h sin actualizar. El backoff de
# `simkl._get` cubre unos segundos, que para un corte de red doméstica es poco.
#
# Repetir la pasada no le añade carga a Simkl: sus peticiones nunca llegaron a salir.
# Y cada intento vuelve a empezar por /sync/activities, la llamada más barata de la
# API, así que si la red sigue caída muere ahí sin llegar a pedir /sync/all-items.
NETWORK_RETRY_DELAYS = (120, 600)  # 2 y 10 minutos


def update_watching_cron():
    attempts = len(NETWORK_RETRY_DELAYS) + 1
    for attempt in range(attempts):
        try:
            # Pull completo (full=True): ignora el gate de /sync/activities y pide toda
            # la biblioteca. Es la única forma de detectar lo borrado del otro lado y de
            # captar entradas con fechas viejas, igual que hacía el crawl completo con
            # Trakt. Con una corrida diaria el coste es despreciable.
            created = refresh_watching_from_simkl(full=True)
        except (requests.ConnectionError, requests.Timeout) as exc:
            if attempt == attempts - 1:
                logger.error(
                    "Sin conexión para sincronizar Simkl tras %s intentos; queda para mañana: %s",
                    attempts, exc,
                )
                return
            delay = NETWORK_RETRY_DELAYS[attempt]
            logger.warning(
                "Sin conexión para sincronizar Simkl (%s); se reintenta en %s min.",
                exc, delay // 60,
            )
            time.sleep(delay)
            continue
        except Exception:
            # Un error de Simkl, de TMDB o del propio código no se arregla repitiendo:
            # fallaría igual y solo gastaría cuota.
            logger.exception("Error actualizando historial de Simkl")
            return
        logger.info("Historial de Simkl actualizado correctamente (%s eventos nuevos)", created)
        return

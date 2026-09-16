"""Cliente de la API de Simkl (https://api.simkl.org/).

Aislado a propósito: si Simkl cambia, solo se toca este archivo. La API es gratis y
el token del flujo PIN dura ~5 años sin refresh, así que se guarda en el .env y no
hay nada que rotar.

Reglas de la API que importan aquí:
- `client_id`, `app-name` y `app-version` van como query params en TODAS las llamadas.
- Los endpoints de usuario piden `Authorization: Bearer <token>`.
- Límite: 10 GET/s. Y nunca pedir /sync/all-items en un timer sin consultar antes
  /sync/activities (la propia documentación advierte que puede costar la suspensión).
"""

import json
import logging
import random
import time

import requests
from django.conf import settings

logger = logging.getLogger(__name__)

API_BASE = 'https://api.simkl.com'
APP_NAME = 'johanfer-com'
APP_VERSION = '1.0'
USER_AGENT = f'{APP_NAME}/{APP_VERSION}'
PIN_VERIFICATION_URL = 'https://simkl.com/pin'

# Reintentos de los GET, con el patrón que documenta Simkl en
# https://api.simkl.org/conventions/errors: espera exponencial con jitter para los
# transitorios y nada de insistir en los deterministas (400, 401, 403, 404, 409, 412),
# que fallarían igual y solo gastarían cuota hasta provocar un 429. El 412 además
# puede ser un bloqueo ya activo: repetirlo lo alargaría.
#
# El reintento vive AQUÍ y no en la tarea a propósito: así solo se repite la llamada
# que falló. Reintentar la pasada entera volvería a pedir /sync/all-items, que es
# justo la llamada que la documentación advierte no repetir en un timer.
#
# Los POST se quedan fuera: un exceso de escrituras no devuelve 429, dispara un
# bloqueo temporal del client_id que los reintentos alargan.
RETRY_STATUSES = frozenset({429, 500, 502, 503})
RETRY_ATTEMPTS = 5  # 1 + 4 reintentos, esperando 1, 2, 4 y 8 s
RETRY_BASE_DELAY = 1.0
MAX_RETRY_DELAY = 60.0


def _retry_after_seconds(response):
    """Segundos que pide la respuesta, si los pide. El 503 puede traer `Retry-After`."""
    raw = (response.headers.get('Retry-After') or '').strip()
    if raw.isdigit():
        return min(float(raw), MAX_RETRY_DELAY)
    return None


def _retry_delay(retry_number, retry_after=None):
    """1, 2, 4, 8... más un jitter de 0-1 s para no sincronizar con otros clientes."""
    if retry_after is not None:
        return retry_after
    backoff = RETRY_BASE_DELAY * (2 ** retry_number)
    return min(backoff, MAX_RETRY_DELAY) + random.random()


def _client_id():
    client_id = getattr(settings, 'SIMKL_CLIENT_ID', None)
    if not client_id:
        raise ValueError(
            "SIMKL_CLIENT_ID no configurado. Creá la app en "
            "https://simkl.com/settings/developer/ y agregá el Client ID al .env."
        )
    return client_id


def _access_token():
    token = getattr(settings, 'SIMKL_ACCESS_TOKEN', None)
    if not token:
        raise ValueError(
            "SIMKL_ACCESS_TOKEN no configurado. Obtenelo con "
            "`python manage.py simkl_auth` y agregalo al .env."
        )
    return token


def _get(path, authenticated=True, **params):
    query = {
        'client_id': _client_id(),
        'app-name': APP_NAME,
        'app-version': APP_VERSION,
    }
    query.update({key: value for key, value in params.items() if value is not None})
    headers = {'User-Agent': USER_AGENT, 'Accept': 'application/json'}
    if authenticated:
        headers['Authorization'] = f'Bearer {_access_token()}'

    last_error = None
    retry_after = None
    for attempt in range(RETRY_ATTEMPTS):
        if attempt:
            delay = _retry_delay(attempt - 1, retry_after)
            logger.warning(
                "Fallo transitorio de Simkl en %s (%s); reintento %s de %s en %.1f s.",
                path, last_error, attempt, RETRY_ATTEMPTS - 1, delay,
            )
            time.sleep(delay)
        retry_after = None
        try:
            response = requests.get(f"{API_BASE}{path}", params=query, headers=headers, timeout=90)
        except (requests.ConnectionError, requests.Timeout) as exc:
            # La petición ni siquiera llegó a salir (DNS caído, WiFi reconectando).
            # No le ha costado nada a Simkl, así que repetirla no le añade carga.
            last_error = exc
            continue
        if response.status_code in RETRY_STATUSES:
            last_error = f'HTTP {response.status_code}'
            retry_after = _retry_after_seconds(response)
            continue
        break
    else:
        # Agotados los intentos: si el último fue de red no hay respuesta que mirar.
        if isinstance(last_error, Exception):
            raise last_error
    response.raise_for_status()
    if not response.content:
        raise ValueError(f'Respuesta vacía de Simkl en {path}')
    try:
        return response.json()
    except json.JSONDecodeError:
        logger.warning("Respuesta no-JSON de Simkl en %s", path)
        raise ValueError(f'Respuesta no JSON de Simkl en {path}') from None


# --- Flujo PIN (setup manual, una sola vez) ------------------------------------

def request_pin():
    """Paso 1: devuelve {user_code, verification_uri, expires_in, interval}."""
    return _get('/oauth/pin', authenticated=False)


def check_pin(user_code):
    """Paso 3: {'result': 'OK', 'access_token': …} cuando el usuario ya autorizó.

    Mientras espera devuelve {'result': 'KO', 'message': 'Authorization pending'}.
    Si la respuesta trae `device_code`, el código murió y hay que pedir otro.
    """
    return _get(f'/oauth/pin/{user_code}', authenticated=False)


# --- Lectura del historial -----------------------------------------------------

def fetch_activities():
    """Timestamps de última modificación. Es la llamada más barata: gatea el resto."""
    return _get('/sync/activities') or {}


def fetch_all_items(date_from=None):
    """Biblioteca completa con episodios y su fecha de visto.

    `extended=full` es prerrequisito de `episode_watched_at`, y sin
    `include_all_episodes` no vienen los episodios de lo completed/dropped.
    """
    result = _get(
        '/sync/all-items/all/all',
        extended='full_anime_seasons',
        episode_watched_at='yes',
        include_all_episodes='yes',
        date_from=date_from,
    )
    if (not isinstance(result, dict) or set(result) - {'shows', 'anime', 'movies'}
            or any(not isinstance(v, list) for v in result.values())):
        raise ValueError('Biblioteca Simkl inválida; no se reconcilia el historial')
    return result


def add_anime_history(simkl_id, number, watched_at):
    """Escritura por ID exacto del cour y episodio nativo, sin temporada ni rewatch."""
    response = requests.post(
        f'{API_BASE}/sync/history',
        params={'client_id': _client_id(), 'app-name': APP_NAME, 'app-version': APP_VERSION},
        headers={'Authorization': f'Bearer {_access_token()}', 'User-Agent': USER_AGENT},
        json={'shows': [{'ids': {'simkl': simkl_id}, 'episodes': [
            {'number': number, 'watched_at': watched_at.isoformat()},
        ]}]}, timeout=90,
    )
    response.raise_for_status()
    result = response.json()
    if not isinstance(result, dict) or any((result.get('not_found') or {}).values()):
        raise ValueError('Simkl no reconoció la marca; no se declara recuperada')
    return result


def fetch_episodes(simkl_id, is_anime=False):
    """Episodios de una obra: número, título, sinopsis y fecha de emisión.

    Simkl da el título del episodio, que /sync/all-items no incluye: evita una
    llamada extra a TMDB por temporada.
    """
    kind = 'anime' if is_anime else 'tv'
    return _get(f'/{kind}/episodes/{simkl_id}', authenticated=False) or []


def fetch_detail(simkl_id, is_anime=False):
    """Ficha completa de una obra.

    `/sync/all-items` devuelve los ids abreviados y a veces sin `tmdb`; la ficha sí lo
    trae (junto con tvdb, mal, anilist…). Sirve para rescatar obras que si no se
    descartarían, típicamente las secuelas de anime.
    """
    kind = 'anime' if is_anime else 'tv'
    return _get(f'/{kind}/{simkl_id}', authenticated=False, extended='full') or {}


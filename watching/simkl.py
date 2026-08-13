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

import requests
from django.conf import settings

logger = logging.getLogger(__name__)

API_BASE = 'https://api.simkl.com'
APP_NAME = 'johanfer-com'
APP_VERSION = '1.0'
USER_AGENT = f'{APP_NAME}/{APP_VERSION}'
PIN_VERIFICATION_URL = 'https://simkl.com/pin'


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

    response = requests.get(f"{API_BASE}{path}", params=query, headers=headers, timeout=90)
    response.raise_for_status()
    if not response.content:
        return None
    try:
        return response.json()
    except json.JSONDecodeError:
        logger.warning("Respuesta no-JSON de Simkl en %s", path)
        return None


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
    return _get(
        '/sync/all-items/all/all',
        extended='full',
        episode_watched_at='yes',
        include_all_episodes='yes',
        language='es',
        date_from=date_from,
    ) or {}


def fetch_episodes(simkl_id, is_anime=False):
    """Episodios de una obra: número, título, sinopsis y fecha de emisión.

    Simkl da el título del episodio, que /sync/all-items no incluye: evita una
    llamada extra a TMDB por temporada.
    """
    kind = 'anime' if is_anime else 'tv'
    return _get(f'/{kind}/episodes/{simkl_id}', authenticated=False) or []


def _post(path, payload):
    query = {
        'client_id': _client_id(),
        'app-name': APP_NAME,
        'app-version': APP_VERSION,
    }
    headers = {
        'User-Agent': USER_AGENT,
        'Content-Type': 'application/json',
        'Authorization': f'Bearer {_access_token()}',
    }
    response = requests.post(
        f"{API_BASE}{path}", params=query, headers=headers, json=payload, timeout=120,
    )
    response.raise_for_status()
    try:
        return response.json() if response.content else None
    except json.JSONDecodeError:
        return None


def add_to_history(payload):
    """Marca como visto. El payload acepta `movies` y `shows` (anime incluido).

    La forma manda: una serie sin `seasons`/`episodes` marca la serie COMPLETA, así que
    siempre hay que bajar al episodio. Cada episodio puede llevar su propio `watched_at`.
    """
    return _post('/sync/history', payload)


def fetch_detail(simkl_id, is_anime=False):
    """Ficha completa de una obra.

    `/sync/all-items` devuelve los ids abreviados y a veces sin `tmdb`; la ficha sí lo
    trae (junto con tvdb, mal, anilist…). Sirve para rescatar obras que si no se
    descartarían, típicamente las secuelas de anime.
    """
    kind = 'anime' if is_anime else 'tv'
    return _get(f'/{kind}/{simkl_id}', authenticated=False, extended='full') or {}


def fetch_user_settings():
    """Datos de la cuenta dueña del token. Útil para verificar la conexión."""
    return _get('/users/settings') or {}

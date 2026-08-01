import logging
import os
from datetime import datetime, timezone

import requests
from django.conf import settings

from home_page.utils import convert_to_webp

from . import simkl
from .models import SimklSyncState, WatchedItem

logger = logging.getLogger(__name__)

TMDB_API_BASE = 'https://api.themoviedb.org/3'
TMDB_IMAGE_BASE = 'https://image.tmdb.org/t/p/w342'

# Cada entrada: clave en la respuesta de Simkl, tipo de medio del modelo, si es anime.
SIMKL_GROUPS = (
    ('shows', 'episode', False),
    ('anime', 'episode', True),
    ('movies', 'movie', False),
)

# Simkl parte el anime por temporada: las secuelas son entradas separadas y suelen venir
# sin `ids.tmdb`, así que el sync las descartaría. Acá se mapean a mano a la obra que ya
# existe en la BD (donde Trakt las agrupaba en una sola serie con temporadas).
# clave: id de Simkl -> {tmdb_id, season}
SIMKL_WORK_ALIASES = {
    1670325: {'tmdb_id': 69346, 'season': 2},  # Youjo Senki II = Saga of Tanya the Evil T2
    2671730: {'tmdb_id': 1669841},             # Bleach: Kashin Tan; en la BD es película
}


# --- TMDB ----------------------------------------------------------------------

def fetch_tmdb_media_details(tmdb_type, tmdb_id):
    """Metadatos de TMDB: textos en español pero carátula en inglés. tmdb_type: 'movie' | 'tv'."""
    api_key = getattr(settings, 'TMDB_API_KEY', None)
    if not api_key or not tmdb_id:
        return {}
    try:
        response = requests.get(
            f"{TMDB_API_BASE}/{tmdb_type}/{tmdb_id}",
            params={
                'api_key': api_key,
                'language': 'es-ES',
                # Trae también el listado de imágenes en inglés (y sin idioma) para
                # elegir la carátula original en vez de la localizada al español.
                'append_to_response': 'images',
                'include_image_language': 'en,null',
            },
            timeout=15,
        )
        response.raise_for_status()
        payload = response.json() or {}
        poster_path = _pick_english_poster(payload)
        return {
            'overview': (payload.get('overview') or '').strip(),
            'public_rating': _normalize_tmdb_rating(payload.get('vote_average')),
            'available_episodes': payload.get('number_of_episodes'),
            'poster_url': f"{TMDB_IMAGE_BASE}{poster_path}" if poster_path else None,
        }
    except Exception:
        logger.exception("Error consultando metadatos en TMDB (%s %s)", tmdb_type, tmdb_id)
        return {}


def fetch_tmdb_id_by_imdb(imdb_id):
    """Resuelve un id de IMDB a TMDB. Devuelve (tmdb_id, tmdb_type) o (None, None).

    Solo se usa cuando Simkl no trae `ids.tmdb`, que es raro.
    """
    api_key = getattr(settings, 'TMDB_API_KEY', None)
    if not api_key or not imdb_id:
        return None, None
    try:
        response = requests.get(
            f"{TMDB_API_BASE}/find/{imdb_id}",
            params={'api_key': api_key, 'external_source': 'imdb_id'},
            timeout=15,
        )
        response.raise_for_status()
        payload = response.json() or {}
    except Exception:
        logger.exception("Error resolviendo %s en TMDB", imdb_id)
        return None, None

    for key, tmdb_type in (('tv_results', 'tv'), ('movie_results', 'movie')):
        results = payload.get(key) or []
        if results and results[0].get('id'):
            return results[0]['id'], tmdb_type
    return None, None


def _pick_english_poster(payload):
    """Elige la carátula en inglés; si no hay, la neutral, y por último la localizada."""
    posters = (payload.get('images') or {}).get('posters') or []
    # TMDB devuelve los pósters ordenados por votos; 'en' primero, luego sin idioma.
    for wanted in ('en', None):
        for poster in posters:
            if poster.get('iso_639_1') == wanted and poster.get('file_path'):
                return poster['file_path']
    return payload.get('poster_path')


def _normalize_tmdb_rating(value):
    if value is None:
        return None
    try:
        return round(float(value), 1)
    except (TypeError, ValueError):
        return None


def _get_tmdb_metadata(cache, tmdb_type, tmdb_id):
    if not tmdb_id:
        return {}
    key = (tmdb_type, tmdb_id)
    if key not in cache:
        cache[key] = fetch_tmdb_media_details(tmdb_type, tmdb_id)
    return cache[key]


# --- Pósters -------------------------------------------------------------------

def download_poster(poster_url, file_name, force=False):
    folder = os.path.join(settings.MEDIA_ROOT, 'Posters')
    os.makedirs(folder, exist_ok=True)
    file_path = os.path.join(folder, file_name)
    if os.path.exists(file_path) and not force:
        return
    temp_path = os.path.join(folder, f"temp_{file_name}.jpg")
    try:
        response = requests.get(poster_url, timeout=30)
        response.raise_for_status()
        with open(temp_path, 'wb') as f:
            f.write(response.content)
        convert_to_webp(temp_path, file_path)
    except Exception:
        logger.exception("Error descargando póster %s", file_name)
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)


def refresh_posters(force=False):
    """Re-descarga la carátula de cada obra distinta. Con force=True sobrescribe
    las existentes (útil tras cambiar el idioma de las carátulas)."""
    tmdb_cache = {}
    seen = set()
    updated = 0
    for item in WatchedItem.objects.exclude(tmdb_id__isnull=True).only('media_type', 'tmdb_id'):
        key = (item.media_type, item.tmdb_id)
        if key in seen:
            continue
        seen.add(key)
        tmdb_type = 'tv' if item.media_type == 'episode' else 'movie'
        poster_url = _get_tmdb_metadata(tmdb_cache, tmdb_type, item.tmdb_id).get('poster_url')
        if poster_url:
            download_poster(poster_url, item.poster_name, force=force)
            updated += 1
    logger.info("Carátulas re-descargadas: %s", updated)
    return updated


# --- Sincronización con Simkl --------------------------------------------------

def _parse_stamp(value):
    """'2026-08-01T20:08:30Z' -> datetime con tzinfo UTC. None si no se puede."""
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
    except ValueError:
        logger.warning("Fecha ilegible de Simkl: %r", value)
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _episode_titles(cache, simkl_id, is_anime):
    """{(temporada, episodio): título} desde Simkl, que sí trae los títulos.

    En series normales cada episodio declara `season` y `episode`. En anime la
    numeración es absoluta y `/sync/all-items` los reporta como temporada 1, así que
    se indexa igual.
    """
    if not simkl_id:
        return {}
    if simkl_id in cache:
        return cache[simkl_id]

    titles = {}
    try:
        for episode in simkl.fetch_episodes(simkl_id, is_anime=is_anime):
            number = episode.get('episode')
            if not number:
                continue
            season = 1 if is_anime else (episode.get('season') or 1)
            title = (episode.get('title') or '').strip()
            if title:
                titles[(season, number)] = title
    except requests.RequestException:
        logger.warning("No se pudieron traer los títulos de episodio de simkl %s", simkl_id)

    cache[simkl_id] = titles
    return titles


def _detail_url(media_type, ids, is_anime=False):
    """Ficha en Simkl. El anime vive bajo /anime/, no bajo /tv/."""
    slug = ids.get('slug') or ''
    simkl_id = ids.get('simkl')
    if not simkl_id:
        return ''
    if media_type == 'movie':
        kind = 'movies'
    else:
        kind = 'anime' if is_anime else 'tv'
    return f"https://simkl.com/{kind}/{simkl_id}/{slug}/" if slug else f"https://simkl.com/{kind}/{simkl_id}/"


def _work_rows(item, media_type, is_anime, forced_season=None):
    """Expande un ítem de Simkl a los eventos que le corresponden en el modelo.

    Devuelve [(season, episode, watched_at)]; para películas, [(None, None, fecha)].
    `forced_season` reubica los episodios de una secuela de anime en la temporada que
    le corresponde dentro de la obra agrupada (ver SIMKL_WORK_ALIASES).
    """
    if media_type == 'movie':
        watched_at = _parse_stamp(item.get('last_watched_at'))
        return [(None, None, watched_at)] if watched_at else []

    rows = []
    for season in item.get('seasons') or []:
        season_number = forced_season or season.get('number')
        for episode in season.get('episodes') or []:
            watched_at = _parse_stamp(episode.get('watched_at'))
            if season_number is not None and episode.get('number') and watched_at:
                rows.append((season_number, episode['number'], watched_at))
    return rows


def refresh_watching_from_simkl(full=False):
    """Sincroniza el historial desde Simkl.

    Gatea con /sync/activities: si Simkl no reporta cambios, no descarga nada (la
    documentación advierte que pedir /sync/all-items en un timer puede costar la
    suspensión de la app). Con `full=True` ignora el gate y pide todo, que es la
    única forma de saber qué se borró del otro lado.

    Nunca toca la fecha de los registros heredados de Trakt: para lo ya visto, las
    fechas de Trakt son las reales y las de Simkl pueden venir de una importación.
    """
    state = SimklSyncState.load()
    activities = simkl.fetch_activities()
    stamp = activities.get('all')

    if not full and stamp and stamp == state.last_activity_at:
        logger.info("Simkl sin cambios desde %s: no se descarga nada.", stamp)
        return 0

    date_from = None if full else (state.last_activity_at or None)
    payload = simkl.fetch_all_items(date_from=date_from)

    existing = {
        item.dedup_key: item
        for item in WatchedItem.objects.only(
            'id', 'dedup_key', 'watched_at', 'source', 'user_rating', 'episode_title'
        )
    }
    # Simkl cataloga las películas de anime como series de un episodio, así que al
    # leerlas volverían como T01E01 y duplicarían la película que ya existe. Manda lo
    # que ya está en la BD: si esa obra es una película, no se crean episodios de ella.
    movie_tmdb_ids = set(
        WatchedItem.objects.filter(media_type='movie').values_list('tmdb_id', flat=True)
    )
    # Título ya establecido para cada obra. Simkl nombra distinto que Trakt (sobre todo
    # el anime: "Youjo Senki II" por "Saga of Tanya the Evil"), y como la tarjeta toma el
    # título del evento más reciente, un episodio nuevo le cambiaría el nombre a la serie.
    # Lo mismo con el año de estreno, que alimenta el gráfico de décadas.
    known_works = {
        tmdb_id: (title, year)
        for tmdb_id, title, year in WatchedItem.objects.exclude(tmdb_id__isnull=True)
        .order_by('watched_at')
        .values_list('tmdb_id', 'title', 'year')
    }
    tmdb_cache = {}
    title_cache = {}
    created = 0
    updated = 0
    skipped = 0
    seen_keys = set()
    touched_works = {}  # (media_type, tmdb_id) -> datos de la obra en Simkl

    for group_key, media_type, is_anime in SIMKL_GROUPS:
        for item in payload.get(group_key) or []:
            media = item.get('show') or item.get('movie') or {}
            ids = media.get('ids') or {}
            tmdb_type = 'movie' if media_type == 'movie' else 'tv'

            alias = SIMKL_WORK_ALIASES.get(ids.get('simkl')) or {}
            forced_season = alias.get('season')

            tmdb_id = alias.get('tmdb_id') or ids.get('tmdb')
            try:
                tmdb_id = int(tmdb_id) if tmdb_id else None
            except (TypeError, ValueError):  # en anime llega como string
                tmdb_id = None
            if not tmdb_id:
                tmdb_id, _ = fetch_tmdb_id_by_imdb(ids.get('imdb'))
            if tmdb_id and media_type == 'episode' and tmdb_id in movie_tmdb_ids:
                # Es una película que Simkl cataloga como serie de un episodio. Si se
                # dejara pasar, se duplicaría la obra y además se pediría a TMDB el id
                # de película por la ruta /tv/, que devuelve otra obra distinta.
                continue
            if not tmdb_id:
                logger.warning(
                    "Sin id de TMDB para %r (simkl=%s, imdb=%s): se omite.",
                    media.get('title'), ids.get('simkl'), ids.get('imdb'),
                )
                skipped += 1
                continue

            rows = _work_rows(item, media_type, is_anime, forced_season)
            if not rows:
                continue

            metadata = _get_tmdb_metadata(tmdb_cache, tmdb_type, tmdb_id)
            titles = _episode_titles(title_cache, ids.get('simkl'), is_anime) if media_type == 'episode' else {}
            # Se acumula: varias entradas de Simkl pueden mapear a una sola obra nuestra
            # (el anime viene partido por temporada). Si se sobrescribiera, los
            # contadores de una secuela pasarían por los de la serie entera.
            work = touched_works.setdefault((media_type, tmdb_id), {
                'user_rating': None, 'watched_episodes_count': 0, 'available_episodes': 0,
            })
            work['user_rating'] = work['user_rating'] or item.get('user_rating')
            work['watched_episodes_count'] += item.get('watched_episodes_count') or 0
            work['available_episodes'] += _available_episodes(item, metadata) or 0

            known_title, known_year = known_works.get(tmdb_id, (None, None))

            for season, episode, watched_at in rows:
                dedup_key = WatchedItem.build_dedup_key(media_type, tmdb_id, season, episode)
                seen_keys.add(dedup_key)
                known = existing.get(dedup_key)

                if known is not None:
                    # Solo se corrige la fecha de lo que vino de Simkl: los registros
                    # de Trakt conservan la suya, que es la real.
                    if known.source == 'simkl' and known.watched_at != watched_at:
                        known.watched_at = watched_at
                        known.save(update_fields=['watched_at'])
                        updated += 1
                    continue

                watched = WatchedItem.objects.create(
                    dedup_key=dedup_key,
                    source='simkl',
                    media_type=media_type,
                    title=known_title or (media.get('title') or '').strip() or 'Sin título',
                    episode_title=titles.get((season, episode), ''),
                    season=season,
                    episode=episode,
                    year=known_year or media.get('year'),
                    overview=metadata.get('overview', ''),
                    public_rating=metadata.get('public_rating'),
                    watched_at=watched_at,
                    tmdb_id=tmdb_id,
                    imdb_id=ids.get('imdb') or '',
                    simkl_id=ids.get('simkl'),
                    detail_url=_detail_url(media_type, ids, is_anime),
                )
                existing[dedup_key] = watched
                created += 1

                poster_path = os.path.join(settings.MEDIA_ROOT, 'Posters', watched.poster_name)
                if not os.path.exists(poster_path) and metadata.get('poster_url'):
                    download_poster(metadata['poster_url'], watched.poster_name)

    _update_work_aggregates(touched_works)
    deleted = _reconcile(seen_keys) if full else 0

    in_progress = fetch_in_progress()
    state.in_progress_ids = ','.join(str(tmdb_id) for tmdb_id in sorted(in_progress))
    if stamp:
        state.last_activity_at = stamp
    state.save(update_fields=['last_activity_at', 'in_progress_ids', 'last_synced_at'])

    logger.info(
        "Simkl sincronizado: %s nuevos, %s con fecha corregida, %s eliminados, %s omitidos",
        created, updated, deleted, skipped,
    )
    return created


def _available_episodes(item, metadata):
    """Episodios que tiene la obra, **incluidos los que aún no se emiten**.

    Alimenta el listón "Viendo": la vista considera terminada una serie cuando ya viste
    tantos episodios como tiene. Si se descontaran los no emitidos, una serie en curso
    de la que estás al día (Silo: 25 vistos de 25 emitidos, con 5 por salir) se daría
    por terminada y perdería el listón.
    """
    return item.get('total_episodes_count') or metadata.get('available_episodes')


def _update_work_aggregates(touched_works):
    """Actualiza nota, episodios vistos y disponibles en todas las filas de cada obra.

    Los episodios vistos se cuentan en local y no se toman de Simkl a secas: Simkl
    arrancó vacío, así que su `watched_episodes_count` de una serie vieja solo
    refleja lo nuevo.
    """
    for (media_type, tmdb_id), data in touched_works.items():
        rows = WatchedItem.objects.filter(media_type=media_type, tmdb_id=tmdb_id)
        updates = {}

        if media_type == 'episode':
            local_count = rows.count()
            updates['total_episodes'] = max(local_count, data['watched_episodes_count'])
            if data['available_episodes']:
                updates['available_episodes'] = data['available_episodes']
        if data['user_rating']:
            updates['user_rating'] = data['user_rating']

        if updates:
            rows.exclude(**updates).update(**updates)


def _reconcile(seen_keys):
    """Borra lo que ya no está en Simkl, solo entre las filas cuya fuente es Simkl.

    Los registros heredados de Trakt no están en Simkl por definición: borrarlos
    arrasaría el historial. Y si "sobrara" una fracción grande de los de Simkl es
    señal de un pull anómalo, así que tampoco se borra en masa.
    """
    simkl_rows = dict(
        WatchedItem.objects.filter(source='simkl').values_list('dedup_key', 'id')
    )
    stale = [row_id for key, row_id in simkl_rows.items() if key not in seen_keys]
    if not stale:
        return 0
    if len(stale) > max(5, len(simkl_rows) // 5):
        logger.warning(
            "Reconciliación abortada: %s de %s filas de Simkl marcadas como sobrantes.",
            len(stale), len(simkl_rows),
        )
        return 0
    deleted, _ = WatchedItem.objects.filter(id__in=stale).delete()
    return deleted


def fetch_in_progress():
    """Lo que está a medias en Simkl, para el listón 'Viendo'.

    Devuelve {tmdb_id: {'season', 'episode', 'progress'}}. Es dato real, no la
    heurística de "actividad en los últimos N días".
    """
    in_progress = {}
    try:
        entries = simkl.fetch_playback()
    except requests.RequestException:
        logger.warning("No se pudo consultar /sync/playback; el listón Viendo cae a la heurística.")
        return in_progress

    for entry in entries or []:
        media = entry.get('show') or entry.get('anime') or entry.get('movie') or {}
        ids = media.get('ids') or {}
        try:
            tmdb_id = int(ids.get('tmdb')) if ids.get('tmdb') else None
        except (TypeError, ValueError):
            tmdb_id = None
        if not tmdb_id:
            continue
        episode = entry.get('episode') or {}
        in_progress[tmdb_id] = {
            'season': episode.get('season'),
            'episode': episode.get('number'),
            'progress': entry.get('progress'),
        }
    return in_progress

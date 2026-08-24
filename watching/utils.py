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

# Ids que Simkl declara mal y que ningún rescate automático resuelve. Se usan SOLO
# para pedir metadatos a TMDB: la identidad de la obra (`dedup_key`, `poster_name`)
# sigue colgando del id original, así que no hay filas que migrar ni carátulas que
# renombrar. El archivo se llama igual que antes, solo cambia su contenido.
#
# ('tv', 329809): Simkl da ese id para "Bleach: Sennen Kessen Hen", pero en TMDB no
# es una serie —/tv/329809 responde 404— sino la película francesa "Courted" (2015).
# TMDB no tiene entrada propia para Thousand-Year Blood War: la modela como la
# temporada 2 de tv/30984 (Bleach). Se comprobó que no hay salida automática: ni
# find por imdb (tt14986406) ni find por tvdb (458864) devuelven nada, y buscar por
# título tampoco pasa de tv/30984. De ahí que la corrección vaya a mano.
TMDB_METADATA_OVERRIDES = {
    ('tv', 329809): 30984,
}

# Entradas de Simkl que son la continuación de una obra que ya tenemos, y que por su
# id de TMDB abrirían una tarjeta aparte. Clave: id de Simkl -> id de TMDB de la obra.
# Esto SÍ cambia la identidad (`dedup_key`, `poster_name`), al revés que
# TMDB_METADATA_OVERRIDES.
#
# 2671730 ("Bleach: Sennen Kessen Hen - Kashin Tan"): Simkl parte el anime por cour y
# este declara tmdb 30984, que es Bleach entero, mientras que los 13 episodios que ya
# tenemos cuelgan de 329809. Sin esto saldría una segunda tarjeta "Bleach" en cuanto se
# viera un episodio. La numeración encaja sola porque ambos cours comparten temporada en
# TVDB: los que hay son S17E01-13 y los nuevos son S17E41-48.
#
# 2743422 ("Re:Zero kara Hajimeru Isekai Seikatsu", cour de 2026): declara tmdb 328061,
# que en TMDB no es una serie sino la película "Ariana" (2003) —/tv/328061 responde 404—,
# así que la obra salía en una tarjeta aparte, con el título japonés y sin carátula ni
# sinopsis. La serie ya está aquí desde Trakt bajo tmdb 65942. La salida automática
# tampoco existe: su imdb (tt36501927) resuelve en TMDB a un *episodio*, no a una serie,
# así que `find` deja `tv_results` vacío.
SIMKL_WORK_OVERRIDES = {
    2671730: 329809,
    2743422: 65942,
}

# Cada entrada: clave en la respuesta de Simkl, tipo de medio del modelo, si es anime.
SIMKL_GROUPS = (
    ('shows', 'episode', False),
    ('anime', 'episode', True),
    ('movies', 'movie', False),
)



# --- TMDB ----------------------------------------------------------------------

def fetch_tmdb_media_details(tmdb_type, tmdb_id):
    """Metadatos de TMDB: textos en español pero carátula en inglés. tmdb_type: 'movie' | 'tv'.

    Devuelve None —y no {}— cuando TMDB no conoce el id, para que el llamador pueda
    distinguir "nos dieron un id inválido", que no se arregla solo, de "la consulta
    falló esta vez", que se arregla en la pasada siguiente.
    """
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
        if response.status_code == 404:
            return None
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


def fetch_tmdb_id_by_imdb(imdb_id, expected_type=None):
    """Resuelve un id de IMDB a TMDB. Devuelve (tmdb_id, tmdb_type) o (None, None).

    Solo se usa cuando Simkl no trae `ids.tmdb`, que es raro. Con `expected_type` se
    exige que la coincidencia esté en el espacio que toca: los dos espacios de ids son
    independientes, así que un id de película colocado en una serie da un 404 en /tv/ y
    deja la obra sin carátula ni sinopsis.
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
        if expected_type and tmdb_type != expected_type:
            continue
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


def _get_tmdb_metadata(cache, tmdb_type, tmdb_id, title=''):
    """Metadatos de la obra, pidiéndolos por el id corregido si hay override.

    Si TMDB no conoce el id se avisa por WARNING nombrando la obra. Antes esto se
    degradaba en silencio: la obra se quedaba sin carátula ni sinopsis y lo único que
    lo delataba era una traza de 404 en el log del cron, que ni existía hasta hace poco.
    """
    if not tmdb_id:
        return {}
    lookup_id = TMDB_METADATA_OVERRIDES.get((tmdb_type, tmdb_id), tmdb_id)
    key = (tmdb_type, lookup_id)
    if key not in cache:
        details = fetch_tmdb_media_details(tmdb_type, lookup_id)
        if details is None:
            logger.warning(
                "TMDB no conoce %s/%s (%r): la obra se queda sin carátula ni sinopsis. "
                "Si el id lo da mal la fuente, añádelo a TMDB_METADATA_OVERRIDES.",
                tmdb_type, lookup_id, title or '?',
            )
            details = {}
        cache[key] = details
    return cache[key]


def metadata_for_work(cache, media_type, tmdb_id, title=''):
    """Metadatos de una obra del modelo, traduciendo `media_type` al espacio de TMDB.

    `cache` es un dict que el llamador reutiliza entre obras para no pedir dos veces la
    misma ficha; el anime llega partido por temporada y varias entradas caen en la misma.
    """
    tmdb_type = 'tv' if media_type == 'episode' else 'movie'
    return _get_tmdb_metadata(cache, tmdb_type, tmdb_id, title)


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


def _episode_index(cache, simkl_id, is_anime):
    """Índice de episodios de una obra, desde Simkl.

    Devuelve {(temporada, episodio) del listado: {'title', 'season', 'episode'}}, donde
    `season`/`episode` son la ubicación real dentro de la obra agrupada.

    Hace falta porque Simkl parte el anime por temporada y numera en absoluto: la
    segunda temporada de una serie es otra entrada cuyos episodios empiezan en 1. Cada
    episodio declara su equivalencia en TVDB, que es la numeración que ya usan los
    registros heredados de Trakt, así que se usa esa para ubicarlos.
    """
    if not simkl_id:
        return {}
    if simkl_id in cache:
        return cache[simkl_id]

    index = {}
    try:
        for episode in simkl.fetch_episodes(simkl_id, is_anime=is_anime):
            number = episode.get('episode')
            # Los specials repiten la numeración de los episodios normales (una serie
            # con 8 capítulos devuelve además 8 "Mini-Episode N"): si se indexaran,
            # pisarían al episodio real y se perdería su equivalencia con TVDB.
            if not number or episode.get('type') != 'episode':
                continue
            listed_season = 1 if is_anime else (episode.get('season') or 1)
            tvdb = episode.get('tvdb') or {}
            index[(listed_season, number)] = {
                'title': (episode.get('title') or '').strip(),
                'season': tvdb.get('season') or episode.get('season') or listed_season,
                'episode': tvdb.get('episode') or number,
            }
    except requests.RequestException:
        logger.warning("No se pudo traer el índice de episodios de simkl %s", simkl_id)

    cache[simkl_id] = index
    return index


def _resolve_tmdb_id(ids, is_anime):
    """Saca el id de TMDB de una obra, insistiendo si el listado no lo trae.

    `/sync/all-items` devuelve los ids abreviados y las secuelas de anime suelen llegar
    sin `tmdb`; la ficha completa sí lo tiene. Antes esas obras se descartaban y la
    serie se quedaba sin sus episodios nuevos.
    """
    raw = ids.get('tmdb')
    if not raw and ids.get('simkl'):
        try:
            detail_ids = (simkl.fetch_detail(ids['simkl'], is_anime=is_anime) or {}).get('ids') or {}
        except requests.RequestException:
            logger.warning("No se pudo consultar la ficha de simkl %s", ids.get('simkl'))
            detail_ids = {}
        raw = detail_ids.get('tmdb')
        if raw:
            logger.info("TMDB %s recuperado de la ficha de simkl %s", raw, ids['simkl'])

    try:
        return int(raw) if raw else None
    except (TypeError, ValueError):  # en anime llega como string
        return None


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


def _work_rows(item, media_type, episode_index):
    """Expande un ítem de Simkl a los eventos que le corresponden en el modelo.

    Devuelve [(season, episode, watched_at, título del episodio)]; para películas,
    [(None, None, fecha, '')]. La temporada y el número salen del índice cuando existe,
    que es lo que reubica las secuelas de anime en su temporada real.
    """
    if media_type == 'movie':
        watched_at = _parse_stamp(item.get('last_watched_at'))
        return [(None, None, watched_at, '')] if watched_at else []

    rows = []
    for season in item.get('seasons') or []:
        listed_season = season.get('number')
        for episode in season.get('episodes') or []:
            watched_at = _parse_stamp(episode.get('watched_at'))
            listed_episode = episode.get('number')
            if listed_season is None or not listed_episode or not watched_at:
                continue
            placement = episode_index.get((listed_season, listed_episode)) or {}
            rows.append((
                placement.get('season') or listed_season,
                placement.get('episode') or listed_episode,
                watched_at,
                placement.get('title') or '',
            ))
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
    episode_cache = {}
    created = 0
    updated = 0
    skipped = 0
    seen_keys = set()
    touched_works = {}  # (media_type, tmdb_id) -> datos de la obra en Simkl
    pending_works = set()  # tmdb_id de las obras a las que les queda algo por ver

    for group_key, media_type, is_anime in SIMKL_GROUPS:
        for item in payload.get(group_key) or []:
            media = item.get('show') or item.get('movie') or {}
            ids = media.get('ids') or {}
            tmdb_type = 'movie' if media_type == 'movie' else 'tv'

            tmdb_id = SIMKL_WORK_OVERRIDES.get(ids.get('simkl')) or _resolve_tmdb_id(ids, is_anime)
            if not tmdb_id:
                tmdb_id, _ = fetch_tmdb_id_by_imdb(ids.get('imdb'), expected_type=tmdb_type)
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

            episode_index = (
                _episode_index(episode_cache, ids.get('simkl'), is_anime)
                if media_type == 'episode' else {}
            )
            # Antes del corte por `rows`: el cour que se está emitiendo aún no tiene
            # ningún episodio visto, y es justo el que dice que la obra sigue en curso.
            if (
                media_type == 'episode'
                and item.get('status') == 'watching'
                and _pending_after_last_watched(item, episode_index)
            ):
                pending_works.add(tmdb_id)

            rows = _work_rows(item, media_type, episode_index)
            if not rows:
                continue

            metadata = _get_tmdb_metadata(
                tmdb_cache, tmdb_type, tmdb_id, (media.get('title') or '').strip()
            )
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

            for season, episode, watched_at, episode_title in rows:
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
                    episode_title=episode_title,
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

    # Solo se reescribe en el pull completo: uno incremental trae únicamente lo tocado
    # desde la última vez, así que dejaría fuera a las obras que no se movieron.
    if full:
        state.pending_ids = ','.join(str(tmdb_id) for tmdb_id in sorted(pending_works))
    if stamp:
        state.last_activity_at = stamp
    state.save(update_fields=['last_activity_at', 'pending_ids', 'last_synced_at'])

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


def _pending_after_last_watched(item, episode_index):
    """Episodios que quedan POR DELANTE del último visto, emitidos o no.

    Se cuenta por posición y no como "total menos vistos" a propósito: las temporadas
    viejas que nunca se marcaron en Simkl inflarían el pendiente y dejarían la serie
    para siempre en "Viendo". House of the Dragon era el caso: al día con la T3 pero
    con la T1 y la T2 sin marcar, salían 18 pendientes que no existían.

    Los que aún no se han emitido cuentan: una serie en curso de la que estás al día
    (Silo) sigue siendo algo que estás viendo. Lo que evita que el listón reviva al
    anunciarse una temporada nueva es la ventana de la vista, no este conteo.
    """
    if not episode_index:  # sin catálogo no se inventa nada
        return 0
    watched = [
        (season.get('number'), episode.get('number'))
        for season in item.get('seasons') or []
        for episode in season.get('episodes') or []
        if season.get('number') is not None and episode.get('number')
    ]
    if not watched:
        return len(episode_index)
    return sum(1 for key in episode_index if key > max(watched))

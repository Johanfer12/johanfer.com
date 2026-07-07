import logging
import os

import requests
from django.conf import settings
from django.utils.dateparse import parse_datetime

from home_page.utils import convert_to_webp
from .models import WatchedItem

logger = logging.getLogger(__name__)

TRAKT_API_BASE = 'https://api.trakt.tv'
TMDB_API_BASE = 'https://api.themoviedb.org/3'
TMDB_IMAGE_BASE = 'https://image.tmdb.org/t/p/w342'


def _trakt_headers():
    client_id = getattr(settings, 'TRAKT_CLIENT_ID', None)
    if not client_id:
        raise ValueError(
            "TRAKT_CLIENT_ID no configurado. Crea una app en "
            "https://trakt.tv/oauth/applications y agrega el Client ID al .env."
        )
    return {
        'Content-Type': 'application/json',
        'trakt-api-version': '2',
        'trakt-api-key': client_id,
    }


def fetch_trakt_history(page=1, limit=100):
    """Descarga una página del historial público del usuario en Trakt."""
    username = getattr(settings, 'TRAKT_USERNAME', None)
    if not username:
        raise ValueError("TRAKT_USERNAME no configurado en el .env.")
    response = requests.get(
        f"{TRAKT_API_BASE}/users/{username}/history",
        params={'page': page, 'limit': limit, 'extended': 'full'},
        headers=_trakt_headers(),
        timeout=15,
    )
    response.raise_for_status()
    return response.json()


def fetch_trakt_ratings():
    """Devuelve calificaciones públicas del usuario agrupadas por tipo e ID Trakt."""
    username = getattr(settings, 'TRAKT_USERNAME', None)
    if not username:
        raise ValueError("TRAKT_USERNAME no configurado en el .env.")
    response = requests.get(
        f"{TRAKT_API_BASE}/users/{username}/ratings/all",
        headers=_trakt_headers(),
        timeout=15,
    )
    response.raise_for_status()

    ratings = {'movie': {}, 'show': {}, 'episode': {}}
    for item in response.json() or []:
        media_type = item.get('type')
        rating = item.get('rating')
        payload = item.get(media_type) or {}
        ids = payload.get('ids') or {}
        trakt_id = ids.get('trakt')
        if media_type in ratings and trakt_id and rating:
            ratings[media_type][trakt_id] = rating
    return ratings


def fetch_trakt_watched_show_totals():
    """Total de episodios vistos por serie según Trakt."""
    username = getattr(settings, 'TRAKT_USERNAME', None)
    if not username:
        raise ValueError("TRAKT_USERNAME no configurado en el .env.")
    response = requests.get(
        f"{TRAKT_API_BASE}/users/{username}/watched/shows",
        headers=_trakt_headers(),
        timeout=15,
    )
    response.raise_for_status()

    totals = {}
    for item in response.json() or []:
        show = item.get('show') or {}
        ids = show.get('ids') or {}
        trakt_id = ids.get('trakt')
        plays = item.get('plays')
        if trakt_id and plays:
            totals[trakt_id] = plays
    return totals


def fetch_tmdb_media_details(tmdb_type, tmdb_id):
    """Metadatos en español de TMDB. tmdb_type: 'movie' | 'tv'."""
    api_key = getattr(settings, 'TMDB_API_KEY', None)
    if not api_key or not tmdb_id:
        return {}
    try:
        response = requests.get(
            f"{TMDB_API_BASE}/{tmdb_type}/{tmdb_id}",
            params={'api_key': api_key, 'language': 'es-ES'},
            timeout=15,
        )
        response.raise_for_status()
        payload = response.json() or {}
        poster_path = payload.get('poster_path')
        return {
            'overview': (payload.get('overview') or '').strip(),
            'public_rating': _normalize_tmdb_rating(payload.get('vote_average')),
            'available_episodes': payload.get('number_of_episodes'),
            'season_counts': _extract_season_counts(payload),
            'poster_url': f"{TMDB_IMAGE_BASE}{poster_path}" if poster_path else None,
        }
    except Exception:
        logger.exception("Error consultando metadatos en TMDB (%s %s)", tmdb_type, tmdb_id)
        return {}


def fetch_tmdb_poster_url(tmdb_type, tmdb_id):
    """URL del póster en TMDB o None. tmdb_type: 'movie' | 'tv'."""
    return fetch_tmdb_media_details(tmdb_type, tmdb_id).get('poster_url')


def _normalize_tmdb_rating(value):
    if value is None:
        return None
    try:
        return round(float(value), 1)
    except (TypeError, ValueError):
        return None


def _extract_season_counts(payload):
    season_counts = {}
    for season in payload.get('seasons') or []:
        season_number = season.get('season_number')
        episode_count = season.get('episode_count')
        if season_number and episode_count:
            season_counts[season_number] = episode_count
    return season_counts


def download_poster(poster_url, file_name):
    folder = os.path.join(settings.MEDIA_ROOT, 'Posters')
    os.makedirs(folder, exist_ok=True)
    file_path = os.path.join(folder, file_name)
    if os.path.exists(file_path):
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


def parse_history_item(item, ratings=None):
    """Normaliza un evento del historial de Trakt (movie o episode) a campos del modelo."""
    ratings = ratings or {}
    media_type = item.get('type')
    watched_at = parse_datetime(item.get('watched_at') or '')
    history_id = item.get('id')
    if not history_id or not watched_at or media_type not in ('movie', 'episode'):
        return None

    if media_type == 'movie':
        movie = item.get('movie') or {}
        ids = movie.get('ids') or {}
        slug = ids.get('slug') or ''
        return {
            'trakt_history_id': history_id,
            'media_type': 'movie',
            'title': (movie.get('title') or '').strip() or 'Sin título',
            'episode_title': '',
            'season': None,
            'episode': None,
            'year': movie.get('year'),
            'overview': (movie.get('overview') or '').strip(),
            'user_rating': (ratings.get('movie') or {}).get(ids.get('trakt')),
            'public_rating': None,
            'total_episodes': None,
            'available_episodes': None,
            'watched_at': watched_at,
            'trakt_id': ids.get('trakt') or 0,
            'tmdb_id': ids.get('tmdb'),
            'trakt_url': f"https://trakt.tv/movies/{slug}" if slug else '',
        }

    episode = item.get('episode') or {}
    show = item.get('show') or {}
    show_ids = show.get('ids') or {}
    slug = show_ids.get('slug') or ''
    show_overview = (show.get('overview') or '').strip()
    episode_overview = (episode.get('overview') or '').strip()
    return {
        'trakt_history_id': history_id,
        'media_type': 'episode',
        'title': (show.get('title') or '').strip() or 'Sin título',
        'episode_title': (episode.get('title') or '').strip(),
        'season': episode.get('season'),
        'episode': episode.get('number'),
        'year': show.get('year'),
        'overview': show_overview or episode_overview,
        'user_rating': (ratings.get('show') or {}).get(show_ids.get('trakt')),
        'public_rating': None,
        'total_episodes': None,
        'available_episodes': None,
        'watched_at': watched_at,
        'trakt_id': show_ids.get('trakt') or 0,
        'tmdb_id': show_ids.get('tmdb'),
        'trakt_url': f"https://trakt.tv/shows/{slug}" if slug else '',
    }


def refresh_watching_data(max_pages=5, stop_when_page_has_no_new=True):
    """Sincroniza el historial de Trakt: crea eventos nuevos y baja pósters faltantes."""
    existing_ids = set(WatchedItem.objects.values_list('trakt_history_id', flat=True))
    created = 0
    tmdb_cache = {}
    try:
        ratings = fetch_trakt_ratings()
    except requests.RequestException:
        logger.exception("Error descargando calificaciones de Trakt; se continúa sin notas.")
        ratings = {}
    try:
        show_totals = fetch_trakt_watched_show_totals()
    except requests.RequestException:
        logger.exception("Error descargando totales de series de Trakt; se continúa sin totales.")
        show_totals = {}

    for page in range(1, max_pages + 1):
        try:
            history = fetch_trakt_history(page=page)
        except requests.RequestException:
            logger.exception("Error descargando historial de Trakt (página %s); se procesa lo recolectado.", page)
            break
        if not history:
            break

        page_had_new = False
        for raw_item in history:
            data = parse_history_item(raw_item, ratings)
            if not data or data['trakt_history_id'] in existing_ids:
                continue
            tmdb_type = 'tv' if data['media_type'] == 'episode' else 'movie'
            metadata = _get_tmdb_metadata(tmdb_cache, tmdb_type, data.get('tmdb_id'))
            if metadata.get('overview'):
                data['overview'] = metadata['overview']
            if metadata.get('public_rating') is not None:
                data['public_rating'] = metadata['public_rating']
            if data['media_type'] == 'episode':
                data['available_episodes'] = metadata.get('available_episodes')
            watched = WatchedItem.objects.create(**data)
            existing_ids.add(watched.trakt_history_id)
            created += 1
            page_had_new = True

            poster_path = os.path.join(settings.MEDIA_ROOT, 'Posters', watched.poster_name)
            if not os.path.exists(poster_path):
                poster_url = metadata.get('poster_url')
                if poster_url:
                    download_poster(poster_url, watched.poster_name)

        # Página completa ya conocida: lo que sigue es aún más viejo, no hay que seguir.
        if stop_when_page_has_no_new and not page_had_new:
            break

    if ratings:
        _update_existing_ratings(ratings)
    _update_existing_overviews(tmdb_cache)
    _update_existing_episode_totals(show_totals, tmdb_cache)

    logger.info("Trakt sincronizado: %s eventos nuevos", created)
    return created


def _get_tmdb_metadata(cache, tmdb_type, tmdb_id):
    if not tmdb_id:
        return {}
    key = (tmdb_type, tmdb_id)
    if key not in cache:
        cache[key] = fetch_tmdb_media_details(tmdb_type, tmdb_id)
    return cache[key]


def _update_existing_ratings(ratings):
    movie_ratings = ratings.get('movie') or {}
    show_ratings = ratings.get('show') or {}

    for item in WatchedItem.objects.all().only('id', 'media_type', 'trakt_id', 'user_rating'):
        if item.media_type == 'movie':
            rating = movie_ratings.get(item.trakt_id)
        else:
            rating = show_ratings.get(item.trakt_id)
        if rating and item.user_rating != rating:
            item.user_rating = rating
            item.save(update_fields=['user_rating'])


def _update_existing_overviews(tmdb_cache):
    works = WatchedItem.objects.exclude(tmdb_id__isnull=True).values(
        'media_type',
        'trakt_id',
        'tmdb_id',
    ).distinct()

    for work in works:
        tmdb_type = 'tv' if work['media_type'] == 'episode' else 'movie'
        metadata = _get_tmdb_metadata(tmdb_cache, tmdb_type, work['tmdb_id'])
        overview = metadata.get('overview')
        public_rating = metadata.get('public_rating')
        available_episodes = metadata.get('available_episodes') if work['media_type'] == 'episode' else None
        updates = {}
        if overview:
            updates['overview'] = overview
        if public_rating is not None:
            updates['public_rating'] = public_rating
        if available_episodes:
            updates['available_episodes'] = available_episodes
        if not updates:
            continue
        WatchedItem.objects.filter(
            media_type=work['media_type'],
            trakt_id=work['trakt_id'],
        ).exclude(**updates).update(**updates)


def _update_existing_episode_totals(show_totals, tmdb_cache):
    works = WatchedItem.objects.filter(media_type='episode').exclude(tmdb_id__isnull=True).values(
        'trakt_id',
        'tmdb_id',
    ).distinct()

    for work in works:
        qs = WatchedItem.objects.filter(media_type='episode', trakt_id=work['trakt_id'])
        metadata = _get_tmdb_metadata(tmdb_cache, 'tv', work['tmdb_id'])
        total_episodes = _infer_seen_episode_total(
            qs.values('season', 'episode'),
            metadata.get('season_counts') or {},
            show_totals.get(work['trakt_id']),
        )
        if total_episodes:
            qs.exclude(total_episodes=total_episodes).update(total_episodes=total_episodes)


def _infer_seen_episode_total(episodes, season_counts, trakt_total=None):
    seen = [
        (episode['season'], episode['episode'])
        for episode in episodes
        if episode.get('season') is not None and episode.get('episode') is not None
    ]
    if not seen:
        return trakt_total

    unique_seen = set(seen)
    max_season = max(season for season, _ in unique_seen)
    max_episode_in_season = max(episode for season, episode in unique_seen if season == max_season)
    prior_seasons_total = sum(
        count
        for season, count in season_counts.items()
        if season < max_season
    )
    inferred_total = prior_seasons_total + max_episode_in_season
    candidates = [len(unique_seen), inferred_total]
    if trakt_total:
        candidates.append(trakt_total)
    return max(candidates)

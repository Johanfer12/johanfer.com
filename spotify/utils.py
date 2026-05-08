import spotipy
import spotipy.util as util
from datetime import datetime
from .models import SpotifyFavorites, SpotifyTopSongs, DeletedSongs
from django.utils import timezone
from django.conf import settings
import pytz
import requests
from bs4 import BeautifulSoup
import json
from jsonpath_ng import parse
import time
import logging


logger = logging.getLogger(__name__)


def _get_spotify_setting(name):
    value = getattr(settings, name, "")
    return (value or "").strip()


def _upsert_top_song(rank, track, preview_url):
    song_url = track['external_urls']['spotify']
    defaults = {
        'rank': rank,
        'song_name': track['name'],
        'artist_name': track['artists'][0]['name'],
        'album_cover': track['album']['images'][0]['url'] if track['album']['images'] else None,
        'preview_url': preview_url,
    }
    matches = SpotifyTopSongs.objects.filter(song_url=song_url).order_by('id')
    top_song = matches.first()
    if top_song:
        matches.exclude(id=top_song.id).delete()
        for field, value in defaults.items():
            setattr(top_song, field, value)
        top_song.save(update_fields=[*defaults.keys()])
        return top_song
    return SpotifyTopSongs.objects.create(song_url=song_url, **defaults)


def add_tracks_to_playlist(token, playlist_id, track_uris):
    if not playlist_id or not track_uris:
        return False

    response = requests.post(
        f"https://api.spotify.com/v1/playlists/{playlist_id}/items",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        json={"uris": track_uris},
        timeout=20,
    )
    response.raise_for_status()
    return True


def refresh_spotify_data():
    if not getattr(settings, 'SPOTIFY_REFRESH_ENABLED', True):
        logger.warning("Refresh de Spotify deshabilitado por SPOTIFY_REFRESH_ENABLED")
        return False

    client_id = _get_spotify_setting('SPOTIFY_CLIENT_ID')
    client_secret = _get_spotify_setting('SPOTIFY_CLIENT_SECRET')
    username = _get_spotify_setting('SPOTIFY_USERNAME')
    if not client_id or not client_secret or not username:
        logger.error("Faltan SPOTIFY_CLIENT_ID, SPOTIFY_CLIENT_SECRET o SPOTIFY_USERNAME")
        return False

    # Obtener el token de acceso
    scope = "user-library-read user-top-read playlist-modify-public playlist-modify-private playlist-read-private"
    redirect_uri = "http://localhost:8888/callback"
    try:
        token = util.prompt_for_user_token(
            username,
            scope,
            client_id=client_id,
            client_secret=client_secret,
            redirect_uri=redirect_uri
        )
        if not token:
             logger.error("No se pudo obtener el token de Spotify. Abortando refresh.")
             return
    except Exception:
        logger.exception("Error durante la obtención del token")
        return

    # Aumentar el timeout para las solicitudes
    sp = spotipy.Spotify(auth=token, requests_timeout=15)

    olvidadas_playlist_id = _get_spotify_setting('SPOTIFY_OLVIDADAS_PLAYLIST_ID')
    if olvidadas_playlist_id:
        logger.info(f"Usando playlist 'Olvidadas': {olvidadas_playlist_id}")

    # Optimización para canciones top
    top_tracks = sp.current_user_top_tracks(limit=5, time_range='short_term')

    # Actualizar el Top 5 sin borrar y recrear toda la lista.
    current_top_urls = []
    for rank, track in enumerate(top_tracks['items'], start=1):
        song_url = track['external_urls']['spotify']
        track_id = extract_track_id(song_url)
        preview_url = get_preview_url(track_id)
        _upsert_top_song(rank, track, preview_url)
        current_top_urls.append(song_url)

    if current_top_urls:
        SpotifyTopSongs.objects.exclude(song_url__in=current_top_urls).delete()

    # Optimización para favoritos
    results = sp.current_user_saved_tracks(limit=50)
    existing_favorites = {fav.song_url: fav for fav in SpotifyFavorites.objects.all()}
    current_favorites = set()
    artist_genres_cache = {}  # Cache para géneros de artistas

    while True:
        for item in results['items']:
            track = item['track']
            song_url = track['external_urls']['spotify']
            current_favorites.add(song_url)
            
            if song_url in existing_favorites:
                continue

            track_id = extract_track_id(song_url)
            preview_url = get_preview_url(track_id)
            album_cover = track['album']['images'][0]['url'] if track['album']['images'] else None
            added_at = pytz.utc.localize(datetime.strptime(item['added_at'], "%Y-%m-%dT%H:%M:%SZ"))

            # Cache de géneros para evitar llamadas repetidas
            artist_id = track['artists'][0]['id']
            if artist_id not in artist_genres_cache:
                artist_info = sp.artist(artist_id)
                artist_genres_cache[artist_id] = artist_info['genres'][0] if artist_info['genres'] else ''

            SpotifyFavorites.objects.create(
                song_url=song_url,
                song_name=track['name'],
                artist_name=track['artists'][0]['name'],
                duration_ms=track['duration_ms'],
                added_at=added_at,
                album_cover=album_cover,
                genre=artist_genres_cache[artist_id],
                preview_url=preview_url
            )

        if results['next']:
            results = sp.next(results)
        else:
            break

    # Mover canciones eliminadas
    for favorite in SpotifyFavorites.objects.exclude(song_url__in=current_favorites):
        # --- Inicio: Añadir a Playlist "Olvidadas" ---
        if olvidadas_playlist_id:
            try:
                track_id = extract_track_id(favorite.song_url)
                if track_id:
                    track_uri = f"spotify:track:{track_id}"
                    logger.info(f"Añadiendo '{favorite.song_name}' a playlist '{olvidadas_playlist_id}'...")
                    add_tracks_to_playlist(token, olvidadas_playlist_id, [track_uri])
                    logger.info(f"  -> Añadido '{favorite.song_name}' exitosamente.")
                else:
                    logger.warning(f"No se pudo extraer track_id para {favorite.song_name}, no se añade a playlist.")
            except spotipy.exceptions.SpotifyException as e:
                 logger.error(f"Error de API Spotify al añadir track {favorite.song_name} (URI: {track_uri}): {e.http_status} - {e.msg}")
            except Exception:
                 logger.exception("Error inesperado al añadir track %s", favorite.song_name)
        # --- Fin: Añadir a Playlist "Olvidadas" ---

        # Crear registro local en DeletedSongs
        DeletedSongs.objects.create(
            song_name=favorite.song_name,
            artist_name=favorite.artist_name,
            genre=favorite.genre,
            song_url=favorite.song_url,
            duration_ms=favorite.duration_ms,
            added_at=favorite.added_at,
            album_cover=favorite.album_cover,
            preview_url=favorite.preview_url,
            deleted_at=timezone.now()
        )
        favorite.delete() 

    return True

def get_preview_url(track_id):
    if not track_id:
        return None
    try:
        embed_url = f"https://open.spotify.com/embed/track/{track_id}"
        response = requests.get(embed_url, timeout=10)
        
        if not response.ok:
            return None
            
        soup = BeautifulSoup(response.text, 'html.parser')
        scripts = soup.find_all('script')
        
        for script in scripts:
            if script.string:
                try:
                    # Usar jsonpath para encontrar la URL de vista previa
                    jsonpath_expr = parse('$..audioPreview.url')
                    matches = [match.value for match in jsonpath_expr.find(json.loads(script.string))]
                    if matches:
                        return matches[0]
                except (TypeError, ValueError, json.JSONDecodeError):
                    continue
                    
        return None
    except Exception:
        logger.exception("Error getting preview URL")
        return None

def extract_track_id(spotify_url):
    return spotify_url.split('/')[-1].split('?')[0] 

import spotipy
import spotipy.util as util
from datetime import datetime
from config import CLIENT_ID, CLIENT_SECRET, USERNAME
from .models import SpotifyFavorites, SpotifyTopSongs, DeletedSongs
from django.utils import timezone
import pytz
import requests
from bs4 import BeautifulSoup
import json
from jsonpath_ng import parse
import time

def refresh_spotify_data():
    # Obtener el token de acceso
    scope = "user-library-read user-top-read playlist-modify-public playlist-modify-private playlist-read-private"
    redirect_uri = "http://localhost:8888/callback"
    try:
        token = util.prompt_for_user_token(
            USERNAME,
            scope,
            client_id=CLIENT_ID,
            client_secret=CLIENT_SECRET,
            redirect_uri=redirect_uri
        )
        if not token:
             print("Error: No se pudo obtener el token de Spotify. Abortando refresh.")
             return
    except Exception as e:
        print(f"Error durante la obtención del token: {e}")
        return

    # Aumentar el timeout para las solicitudes
    sp = spotipy.Spotify(auth=token, requests_timeout=15)

    # Usar directamente el ID de la playlist "Olvidadas"
    olvidadas_playlist_id = "1ktjWnNpAeK5N7s6UEdRif" 
    print(f"Usando ID de playlist 'Olvidadas' hardcodeado: {olvidadas_playlist_id}")

    # Optimización para canciones top
    top_tracks = sp.current_user_top_tracks(limit=5, time_range='short_term')
    
    # Reiniciamos las canciones top existentes
    SpotifyTopSongs.objects.all().delete()
    
    # Crear los nuevos registros para las 5 canciones top actuales
    for track in top_tracks['items']:
        song_url = track['external_urls']['spotify']
        album_cover = track['album']['images'][0]['url'] if track['album']['images'] else None
        track_id = extract_track_id(song_url)
        preview_url = get_preview_url(track_id)
        
        SpotifyTopSongs.objects.create(
            song_name=track['name'],
            artist_name=track['artists'][0]['name'],
            song_url=song_url,
            album_cover=album_cover,
            preview_url=preview_url
        )

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
                    print(f"Añadiendo '{favorite.song_name}' a playlist '{olvidadas_playlist_id}'...")
                    sp.playlist_add_items(olvidadas_playlist_id, [track_uri])
                    print(f"  -> Añadido '{favorite.song_name}' exitosamente.")
                else:
                    print(f"  -> No se pudo extraer track_id para {favorite.song_name}, no se añade a playlist.")
            except spotipy.exceptions.SpotifyException as e:
                 print(f"  -> Error de API Spotify al añadir track {favorite.song_name} (URI: {track_uri}): {e.http_status} - {e.msg}")
            except Exception as e:
                 print(f"  -> Error inesperado al añadir track {favorite.song_name}: {e}")
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

def get_preview_url(track_id):
    try:
        embed_url = f"https://open.spotify.com/embed/track/{track_id}"
        response = requests.get(embed_url)
        
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
                except:
                    continue
                    
        return None
    except Exception as e:
        print(f"Error getting preview URL: {e}")
        return None

def extract_track_id(spotify_url):
    return spotify_url.split('/')[-1].split('?')[0] 
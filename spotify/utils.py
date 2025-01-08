import spotipy
import spotipy.util as util
from datetime import datetime
from config import CLIENT_ID, CLIENT_SECRET, USERNAME
from .models import SpotifyFavorites, SpotifyTopSongs, DeletedSongs
from django.utils import timezone
import pytz

def refresh_spotify_data():
    # Obtener el token de acceso
    scope = "user-library-read user-top-read"
    redirect_uri = "http://localhost:8888/callback"
    token = util.prompt_for_user_token(
        USERNAME, 
        scope, 
        client_id=CLIENT_ID, 
        client_secret=CLIENT_SECRET, 
        redirect_uri=redirect_uri
    )

    sp = spotipy.Spotify(auth=token)

    # Actualizar canciones top
    top_tracks = sp.current_user_top_tracks(limit=5, time_range='short_term')
    SpotifyTopSongs.objects.all().delete()
    
    for track in top_tracks['items']:
        # Obtener la URL de la carátula del álbum (usar la imagen más grande)
        album_cover = None
        if track['album']['images']:
            album_cover = track['album']['images'][0]['url']

        SpotifyTopSongs.objects.create(
            song_name=track['name'],
            artist_name=track['artists'][0]['name'],
            song_url=track['external_urls']['spotify'],
            album_cover=album_cover
        )

    # Obtener y actualizar favoritos
    results = sp.current_user_saved_tracks(limit=50)
    current_favorites = set()

    while True:
        for item in results['items']:
            track = item['track']
            song_url = track['external_urls']['spotify']
            current_favorites.add(song_url)

            # Obtener la URL de la carátula del álbum (usar la imagen más grande)
            album_cover = None
            if track['album']['images']:
                album_cover = track['album']['images'][0]['url']

            # Convertir la fecha UTC string a datetime con timezone
            added_at = datetime.strptime(item['added_at'], "%Y-%m-%dT%H:%M:%SZ")
            added_at = pytz.utc.localize(added_at)

            # Obtener el género principal del artista (solo el primero)
            artist_id = track['artists'][0]['id']
            artist_info = sp.artist(artist_id)
            genre = artist_info['genres'][0] if artist_info['genres'] else ''

            favorite, created = SpotifyFavorites.objects.get_or_create(
                song_url=song_url,
                defaults={
                    'song_name': track['name'],
                    'artist_name': track['artists'][0]['name'],
                    'duration_ms': track['duration_ms'],
                    'added_at': added_at,
                    'album_cover': album_cover,
                    'genre': genre
                }
            )

            # Actualizar carátula y género incluso si la canción ya existe
            if not created:
                favorite.album_cover = album_cover
                favorite.genre = genre
                favorite.save()

        if results['next']:
            results = sp.next(results)
        else:
            break

    # Mover canciones eliminadas
    for favorite in SpotifyFavorites.objects.exclude(song_url__in=current_favorites):
        DeletedSongs.objects.create(
            song_name=favorite.song_name,
            artist_name=favorite.artist_name,
            genre=favorite.genre,
            song_url=favorite.song_url,
            duration_ms=favorite.duration_ms,
            added_at=favorite.added_at,
            deleted_at=timezone.now()
        )
        favorite.delete() 
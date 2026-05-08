from django.shortcuts import render
from .models import SpotifyFavorites, SpotifyTopSongs, DeletedSongs
from .utils import refresh_spotify_data
from django.contrib import messages
from django.db.models import Count
from django.db.models.functions import TruncMonth
import json
import logging


logger = logging.getLogger(__name__)

TOP_PLAYLIST_ID = '1sZ3u7s7hpzjTc9I5BgwEb'
TOP_PLAYLIST_URL = f'https://open.spotify.com/playlist/{TOP_PLAYLIST_ID}'
TOP_PLAYLIST_EMBED_URL = f'https://open.spotify.com/embed/playlist/{TOP_PLAYLIST_ID}?utm_source=generator'


def spotify_dashboard(request):
    if request.method == 'POST' and 'update_spotify' in request.POST:  # Verificar si el botón fue presionado
        try:
            refreshed = refresh_spotify_data()
            if refreshed:
                messages.success(request, '¡Datos de Spotify actualizados correctamente!')
            else:
                messages.warning(request, 'No se actualizaron datos de Spotify; se mantiene la información guardada.')
        except Exception as e:
            logger.exception("Error actualizando datos de Spotify desde la vista")
            messages.error(request, f'Error al actualizar datos: {str(e)}')
    
    context = {
        'spotify_playlist_url': TOP_PLAYLIST_URL,
        'spotify_playlist_embed_url': TOP_PLAYLIST_EMBED_URL,
        'spotify_playlist_title': 'Mis Top Canciones',
    }
    return render(request, 'dashboard.html', context)

def spotify_stats(request):
    # Top 5 géneros (excluyendo N/A)
    top_genres = SpotifyFavorites.objects.values('genre')\
        .exclude(genre='')\
        .exclude(genre='N/A')\
        .annotate(total=Count('id'))\
        .order_by('-total')[:5]
    
    # Capitalizar cada palabra en los géneros
    genres_labels = [' '.join(word.capitalize() for word in entry['genre'].split()) for entry in top_genres]
    genres_values = [entry['total'] for entry in top_genres]

    # Top 5 artistas
    top_artists = SpotifyFavorites.objects.values('artist_name')\
        .annotate(total=Count('id'))\
        .order_by('-total')[:5]
    
    artists_labels = [entry['artist_name'] for entry in top_artists]
    artists_values = [entry['total'] for entry in top_artists]

    # Canciones por mes
    songs_by_month = SpotifyFavorites.objects.annotate(
        month=TruncMonth('added_at')
    ).values('month').annotate(
        total=Count('id')
    ).order_by('month')

    months_labels = [entry['month'].strftime('%B %Y') for entry in songs_by_month]
    months_values = [entry['total'] for entry in songs_by_month]

    context = {
        'genres_labels': json.dumps(genres_labels),
        'genres_values': json.dumps(genres_values),
        'artists_labels': json.dumps(artists_labels),
        'artists_values': json.dumps(artists_values),
        'months_labels': json.dumps(months_labels),
        'months_values': json.dumps(months_values),
    }

    return render(request, 'sp_stats.html', context)

def spotify_deleted(request):
    deleted_songs = DeletedSongs.objects.all().order_by('-deleted_at')
    context = {
        'deleted_songs': deleted_songs,
        'total_deleted': deleted_songs.count()
    }
    return render(request, 'sp_deleted.html', context)

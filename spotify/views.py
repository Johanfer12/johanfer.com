from django.shortcuts import render
from .models import SpotifyFavorites, SpotifyTopSongs, DeletedSongs
from .utils import refresh_spotify_data
from django.contrib import messages

def spotify_dashboard(request):
    if request.method == 'POST' and 'update_spotify' in request.POST:  # Verificar si el botón fue presionado
        try:
            refresh_spotify_data()
            messages.success(request, '¡Datos de Spotify actualizados correctamente!')
        except Exception as e:
            messages.error(request, f'Error al actualizar datos: {str(e)}')
    
    favorite_songs = SpotifyFavorites.objects.all()
    context = {
        'favorite_songs': favorite_songs[:10],  # últimas 10 canciones
        'top_songs': SpotifyTopSongs.objects.all(),
        'total_songs': favorite_songs.count()  #Conteo de canciones
    }
    return render(request, 'dashboard.html', context)

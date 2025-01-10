from .utils import refresh_spotify_data

def update_spotify_cron():
    try:
        refresh_spotify_data()
        print("Spotify data updated successfully")
    except Exception as e:
        print(f"Error updating Spotify data: {str(e)}") 
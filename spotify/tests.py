from datetime import datetime, timezone
import json

from django.test import TestCase
from django.urls import reverse

from spotify.models import SpotifyFavorites


class SpotifyStatsTests(TestCase):
    def test_monthly_labels_are_in_spanish(self):
        # strftime('%B') depende del locale del sistema y salía en inglés.
        for n, month in enumerate((2, 11)):
            SpotifyFavorites.objects.create(
                song_name=f'Canción {n}',
                artist_name='Artista',
                genre='Rock',
                song_url=f'https://open.spotify.com/track/{n}',
                duration_ms=1000,
                added_at=datetime(2017, month, 10, tzinfo=timezone.utc),
            )

        response = self.client.get(reverse('spotify:stats'))

        self.assertEqual(
            json.loads(response.context['months_labels']),
            ['febrero 2017', 'noviembre 2017'],
        )

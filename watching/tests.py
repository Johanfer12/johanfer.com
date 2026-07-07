from datetime import timedelta
from unittest.mock import patch, MagicMock

from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from .models import WatchedItem
from .utils import fetch_tmdb_media_details, parse_history_item, refresh_watching_data

SAMPLE_MOVIE_EVENT = {
    'id': 111,
    'watched_at': '2026-07-01T02:10:00.000Z',
    'type': 'movie',
    'movie': {
        'title': 'Dune: Part Two',
        'year': 2024,
        'overview': 'Paul Atreides se une a los Fremen.',
        'ids': {'trakt': 12345, 'slug': 'dune-part-two-2024', 'tmdb': 693134},
    },
}

SAMPLE_EPISODE_EVENT = {
    'id': 222,
    'watched_at': '2026-07-02T03:00:00.000Z',
    'type': 'episode',
    'episode': {
        'season': 1,
        'number': 3,
        'title': 'El largo y oscuro té de la tarde del alma',
        'overview': 'Sinopsis del episodio.',
        'ids': {'trakt': 999},
    },
    'show': {
        'title': 'Dirk Gently',
        'year': 2016,
        'overview': 'Sinopsis de la serie.',
        'ids': {'trakt': 55555, 'slug': 'dirk-gently', 'tmdb': 67386},
    },
}


class ParseHistoryItemTests(TestCase):
    def test_parses_movie_event(self):
        data = parse_history_item(SAMPLE_MOVIE_EVENT)

        self.assertEqual(data['media_type'], 'movie')
        self.assertEqual(data['title'], 'Dune: Part Two')
        self.assertEqual(data['trakt_id'], 12345)
        self.assertEqual(data['tmdb_id'], 693134)
        self.assertEqual(data['trakt_url'], 'https://trakt.tv/movies/dune-part-two-2024')

    def test_parses_episode_event_with_show_data(self):
        data = parse_history_item(SAMPLE_EPISODE_EVENT)

        self.assertEqual(data['media_type'], 'episode')
        self.assertEqual(data['title'], 'Dirk Gently')
        self.assertEqual(data['season'], 1)
        self.assertEqual(data['episode'], 3)
        self.assertEqual(data['trakt_id'], 55555)
        self.assertEqual(data['overview'], 'Sinopsis de la serie.')
        self.assertEqual(data['trakt_url'], 'https://trakt.tv/shows/dirk-gently')

    def test_rejects_unknown_or_incomplete_events(self):
        self.assertIsNone(parse_history_item({'id': 1, 'type': 'season', 'watched_at': '2026-07-01T00:00:00Z'}))
        self.assertIsNone(parse_history_item({'type': 'movie', 'watched_at': 'no-es-fecha'}))


@override_settings(TMDB_API_KEY='test-tmdb')
class TmdbDetailsTests(TestCase):
    @patch('watching.utils.requests.get')
    def test_fetches_spanish_overview_and_public_rating(self, mock_get):
        response = MagicMock()
        response.json.return_value = {
            'overview': 'Sinopsis en español.',
            'poster_path': '/poster.jpg',
            'vote_average': 8.56,
            'number_of_episodes': 18,
            'seasons': [
                {'season_number': 0, 'episode_count': 2},
                {'season_number': 1, 'episode_count': 10},
                {'season_number': 2, 'episode_count': 8},
            ],
        }
        response.raise_for_status.return_value = None
        mock_get.return_value = response

        data = fetch_tmdb_media_details('tv', 123)

        self.assertEqual(data['overview'], 'Sinopsis en español.')
        self.assertEqual(data['public_rating'], 8.6)
        self.assertEqual(data['available_episodes'], 18)
        self.assertEqual(data['season_counts'], {1: 10, 2: 8})
        self.assertTrue(data['poster_url'].endswith('/poster.jpg'))
        self.assertEqual(mock_get.call_args.kwargs['params']['language'], 'es-ES')


@override_settings(TRAKT_CLIENT_ID='test-client', TRAKT_USERNAME='johan', TMDB_API_KEY=None)
class RefreshWatchingDataTests(TestCase):
    def _mock_response(self, payload):
        response = MagicMock()
        response.json.return_value = payload
        response.raise_for_status.return_value = None
        return response

    @patch('watching.utils.requests.get')
    def test_creates_items_and_deduplicates_on_second_run(self, mock_get):
        # Página 1 con eventos, página 2 vacía (fin del historial)
        mock_get.side_effect = [
            self._mock_response([]),
            self._mock_response([]),
            self._mock_response([SAMPLE_MOVIE_EVENT, SAMPLE_EPISODE_EVENT]),
            self._mock_response([]),
        ]
        created = refresh_watching_data()

        self.assertEqual(created, 2)
        self.assertEqual(WatchedItem.objects.count(), 2)

        # Segunda corrida: los mismos eventos no deben duplicarse
        mock_get.side_effect = [
            self._mock_response([]),
            self._mock_response([]),
            self._mock_response([SAMPLE_MOVIE_EVENT, SAMPLE_EPISODE_EVENT]),
        ]
        created_again = refresh_watching_data()

        self.assertEqual(created_again, 0)
        self.assertEqual(WatchedItem.objects.count(), 2)

    @patch('watching.utils.requests.get')
    def test_stops_when_page_has_no_new_events(self, mock_get):
        mock_get.side_effect = [
            self._mock_response([]),
            self._mock_response([]),
            self._mock_response([SAMPLE_MOVIE_EVENT]),
            self._mock_response([]),
        ]
        refresh_watching_data()

        # Calificaciones + totales + dos páginas de historial (la segunda vacía corta el bucle)
        self.assertEqual(mock_get.call_count, 4)

    @patch('watching.utils.requests.get')
    def test_fetches_and_applies_trakt_ratings(self, mock_get):
        mock_get.side_effect = [
            self._mock_response([
                {'type': 'movie', 'rating': 9, 'movie': {'ids': {'trakt': 12345}}},
                {'type': 'show', 'rating': 8, 'show': {'ids': {'trakt': 55555}}},
            ]),
            self._mock_response([]),
            self._mock_response([SAMPLE_MOVIE_EVENT, SAMPLE_EPISODE_EVENT]),
            self._mock_response([]),
        ]

        refresh_watching_data()

        self.assertEqual(WatchedItem.objects.get(media_type='movie').user_rating, 9)
        self.assertEqual(WatchedItem.objects.get(media_type='episode').user_rating, 8)

    @patch('watching.utils.requests.get')
    def test_fetches_and_applies_show_episode_totals(self, mock_get):
        mock_get.side_effect = [
            self._mock_response([]),
            self._mock_response([
                {'show': {'ids': {'trakt': 55555}}, 'plays': 21},
            ]),
            self._mock_response([SAMPLE_EPISODE_EVENT]),
            self._mock_response([]),
        ]

        refresh_watching_data()

        self.assertEqual(WatchedItem.objects.get(media_type='episode').total_episodes, 21)

    @override_settings(TMDB_API_KEY='test-tmdb')
    @patch('watching.utils.requests.get')
    def test_infers_previous_seasons_as_seen_from_latest_episode(self, mock_get):
        tmdb_response = self._mock_response({
            'overview': 'Sinopsis en español.',
            'vote_average': 8.5,
            'seasons': [
                {'season_number': 1, 'episode_count': 10},
                {'season_number': 2, 'episode_count': 8},
                {'season_number': 3, 'episode_count': 8},
            ],
        })
        mock_get.side_effect = [
            self._mock_response([]),
            self._mock_response([]),
            self._mock_response([SAMPLE_EPISODE_EVENT | {
                'episode': SAMPLE_EPISODE_EVENT['episode'] | {'season': 3, 'number': 3},
            }]),
            tmdb_response,
            self._mock_response([]),
        ]

        refresh_watching_data()

        self.assertEqual(WatchedItem.objects.get(media_type='episode').total_episodes, 21)


class WatchingViewTests(TestCase):
    def _create_episode(self, history_id, show_trakt_id, season, episode, watched_at, title='Avenue 5'):
        return WatchedItem.objects.create(
            trakt_history_id=history_id,
            media_type='episode',
            title=title,
            season=season,
            episode=episode,
            watched_at=watched_at,
            trakt_id=show_trakt_id,
        )

    def _create_movie(self, history_id, trakt_id, watched_at, title='Blade Runner 2049'):
        return WatchedItem.objects.create(
            trakt_history_id=history_id,
            media_type='movie',
            title=title,
            year=2017,
            watched_at=watched_at,
            trakt_id=trakt_id,
        )

    def test_default_view_shows_series_and_hides_movies(self):
        now = timezone.now()
        self._create_episode(1, 500, 1, 1, now)
        self._create_movie(2, 42, now)

        response = self.client.get(reverse('watching:index'))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['active_tipo'], 'series')
        self.assertContains(response, 'Avenue 5')
        self.assertNotContains(response, 'Blade Runner 2049')
        self.assertContains(response, '1 series')

    def test_movies_tab_shows_movies_and_counter_label(self):
        now = timezone.now()
        self._create_episode(1, 500, 1, 1, now)
        self._create_movie(2, 42, now)

        response = self.client.get(reverse('watching:index'), {'tipo': 'peliculas'})

        self.assertEqual(response.context['active_tipo'], 'peliculas')
        self.assertContains(response, 'Blade Runner 2049')
        self.assertNotContains(response, 'Avenue 5')
        self.assertContains(response, '1 películas')

    def test_invalid_tipo_falls_back_to_series(self):
        response = self.client.get(reverse('watching:index'), {'tipo': 'podcasts'})

        self.assertEqual(response.context['active_tipo'], 'series')

    def test_episodes_of_same_show_group_into_one_card(self):
        now = timezone.now()
        self._create_episode(1, 500, 1, 1, now - timedelta(days=2))
        self._create_episode(2, 500, 1, 2, now - timedelta(days=1))
        self._create_episode(3, 500, 1, 3, now)

        response = self.client.get(reverse('watching:index'))

        self.assertEqual(len(response.context['cards']), 1)
        card = response.context['cards'][0]
        self.assertEqual(card['plays'], 3)
        self.assertEqual(card['episode_count'], 3)
        self.assertEqual(card['episode_total'], 3)
        # El evento más reciente representa a la tarjeta
        self.assertEqual(card['latest'].episode, 3)
        self.assertContains(response, 'Episodios vistos')

    def test_rewatched_episode_counts_as_one_seen_episode(self):
        now = timezone.now()
        self._create_episode(1, 500, 1, 1, now - timedelta(days=1))
        self._create_episode(2, 500, 1, 1, now)

        response = self.client.get(reverse('watching:index'))

        card = response.context['cards'][0]
        self.assertEqual(card['plays'], 2)
        self.assertEqual(card['episode_count'], 1)
        self.assertEqual(card['episode_total'], 1)

    def test_show_card_uses_total_episodes_when_available(self):
        item = self._create_episode(1, 500, 1, 1, timezone.now())
        item.total_episodes = 21
        item.save(update_fields=['total_episodes'])

        response = self.client.get(reverse('watching:index'))

        self.assertEqual(response.context['cards'][0]['episode_total'], 21)
        self.assertContains(response, '21')

    def test_recent_show_gets_watching_ribbon_and_old_show_does_not(self):
        now = timezone.now()
        self._create_episode(1, 500, 1, 1, now, title='Serie Reciente')
        self._create_episode(2, 600, 2, 5, now - timedelta(days=40), title='Serie Vieja')

        response = self.client.get(reverse('watching:index'))

        cards = {card['latest'].title: card for card in response.context['cards']}
        self.assertTrue(cards['Serie Reciente']['is_watching'])
        self.assertFalse(cards['Serie Vieja']['is_watching'])
        self.assertContains(response, 'watching-ribbon', count=1)

    def test_recent_complete_show_does_not_get_watching_ribbon(self):
        now = timezone.now()
        item = self._create_episode(1, 500, 1, 8, now, title='Serie Completa')
        item.total_episodes = 8
        item.available_episodes = 8
        item.save(update_fields=['total_episodes', 'available_episodes'])

        response = self.client.get(reverse('watching:index'))

        self.assertFalse(response.context['cards'][0]['is_watching'])
        self.assertNotContains(response, 'watching-ribbon')

    def test_rewatched_movie_groups_and_shows_play_count(self):
        now = timezone.now()
        for i in range(2):
            self._create_movie(10 + i, 77, now - timedelta(days=i), title='Interstellar')

        response = self.client.get(reverse('watching:index'), {'tipo': 'peliculas'})

        self.assertEqual(len(response.context['cards']), 1)
        self.assertEqual(response.context['cards'][0]['plays'], 2)
        self.assertContains(response, '2 veces')

    def test_toggle_buttons_mark_active_tab(self):
        response = self.client.get(reverse('watching:index'))

        self.assertContains(response, 'watch-toggle-btn shows active')
        self.assertNotContains(response, 'watch-toggle-btn movies active')

    def test_page_renders_empty_state(self):
        response = self.client.get(reverse('watching:index'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Aún no hay series')

    def test_ratings_render_as_five_star_scale(self):
        item = self._create_episode(1, 500, 1, 1, timezone.now())
        item.user_rating = 9
        item.public_rating = 8.6
        item.save(update_fields=['user_rating', 'public_rating'])

        response = self.client.get(reverse('watching:index'))

        self.assertContains(response, 'Mi Calificación')
        self.assertContains(response, 'Calificación General')
        self.assertContains(response, '4.5 de 5')

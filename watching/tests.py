from datetime import timedelta
from unittest.mock import MagicMock, patch

from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from .models import SimklSyncState, WatchedItem
from .utils import fetch_tmdb_media_details, refresh_watching_from_simkl

SIMKL_MOVIE = {
    'last_watched_at': '2026-07-01T02:10:00Z',
    'user_rating': 9,
    'movie': {
        'title': 'Dune: Part Two',
        'year': 2024,
        'ids': {'simkl': 111, 'slug': 'dune-part-two', 'imdb': 'tt15239678', 'tmdb': 693134},
    },
}

SIMKL_SHOW = {
    'last_watched_at': '2026-07-03T03:00:00Z',
    'user_rating': 8,
    'status': 'watching',
    'watched_episodes_count': 2,
    'total_episodes_count': 8,
    'not_aired_episodes_count': 2,
    'show': {
        'title': 'Dirk Gently',
        'year': 2016,
        'ids': {'simkl': 222, 'slug': 'dirk-gently', 'tmdb': 67386},
    },
    'seasons': [{
        'number': 1,
        'episodes': [
            {'number': 1, 'watched_at': '2026-07-02T03:00:00Z'},
            {'number': 2, 'watched_at': '2026-07-03T03:00:00Z'},
        ],
    }],
}

# En anime el id de TMDB llega como string y la numeración es absoluta.
SIMKL_ANIME = {
    'last_watched_at': '2021-11-30T15:00:00Z',
    'watched_episodes_count': 1,
    'total_episodes_count': 12,
    'not_aired_episodes_count': 0,
    'show': {
        'title': 'JoJo no Kimyou na Bouken: Stone Ocean',
        'year': 2021,
        'ids': {'simkl': 1599907, 'slug': 'stone-ocean', 'imdb': 'tt2359704', 'tmdb': '45790'},
    },
    'seasons': [{'number': 1, 'episodes': [{'number': 1, 'watched_at': '2021-11-30T15:00:00Z'}]}],
}


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
        }
        response.raise_for_status.return_value = None
        mock_get.return_value = response

        data = fetch_tmdb_media_details('tv', 123)

        self.assertEqual(data['overview'], 'Sinopsis en español.')
        self.assertEqual(data['public_rating'], 8.6)
        self.assertEqual(data['available_episodes'], 18)
        self.assertTrue(data['poster_url'].endswith('/poster.jpg'))
        self.assertEqual(mock_get.call_args.kwargs['params']['language'], 'es-ES')


@override_settings(TMDB_API_KEY=None)
@patch('watching.utils.simkl.fetch_detail', return_value={})
@patch('watching.utils.simkl.fetch_playback', return_value=[])
@patch('watching.utils.simkl.fetch_episodes', return_value=[])
class RefreshFromSimklTests(TestCase):
    def _sync(self, payload, activities=None, full=False):
        with patch('watching.utils.simkl.fetch_activities',
                   return_value=activities or {'all': '2026-07-03T03:00:00Z'}), \
             patch('watching.utils.simkl.fetch_all_items', return_value=payload) as all_items:
            created = refresh_watching_from_simkl(full=full)
        return created, all_items

    def test_expands_movies_and_episodes_into_rows(self, _episodes, _playback, _detail):
        created, _ = self._sync({'movies': [SIMKL_MOVIE], 'shows': [SIMKL_SHOW]})

        self.assertEqual(created, 3)  # una película + dos episodios
        self.assertEqual(WatchedItem.objects.count(), 3)

        movie = WatchedItem.objects.get(media_type='movie')
        self.assertEqual(movie.dedup_key, 'movie:693134')
        self.assertEqual(movie.source, 'simkl')
        self.assertEqual(movie.user_rating, 9)
        self.assertEqual(movie.imdb_id, 'tt15239678')
        self.assertEqual(movie.detail_url, 'https://simkl.com/movies/111/dune-part-two/')

        episode = WatchedItem.objects.get(media_type='episode', episode=2)
        self.assertEqual(episode.dedup_key, 'show:67386:s01e02')
        self.assertEqual(episode.title, 'Dirk Gently')
        self.assertEqual(episode.user_rating, 8)
        # Cuenta los 8, incluidos los 2 sin emitir: si no, una serie en curso de la que
        # estás al día se daría por terminada y perdería el listón "Viendo".
        self.assertEqual(episode.available_episodes, 8)
        # vistos: se cuentan en local, no se toman de Simkl a secas
        self.assertEqual(episode.total_episodes, 2)

    def test_second_run_does_not_duplicate(self, _episodes, _playback, _detail):
        self._sync({'shows': [SIMKL_SHOW]})
        created_again, _ = self._sync({'shows': [SIMKL_SHOW]}, activities={'all': 'otro-timestamp'})

        self.assertEqual(created_again, 0)
        self.assertEqual(WatchedItem.objects.count(), 2)

    def test_skips_download_when_simkl_reports_no_changes(self, _episodes, _playback, _detail):
        self._sync({'shows': [SIMKL_SHOW]}, activities={'all': 'sello-1'})
        _, all_items = self._sync({'shows': [SIMKL_SHOW]}, activities={'all': 'sello-1'})

        all_items.assert_not_called()

    def test_full_run_ignores_the_gate(self, _episodes, _playback, _detail):
        self._sync({'shows': [SIMKL_SHOW]}, activities={'all': 'sello-1'})
        _, all_items = self._sync({'shows': [SIMKL_SHOW]}, activities={'all': 'sello-1'}, full=True)

        all_items.assert_called_once()

    def test_handles_anime_with_string_tmdb_id(self, _episodes, _playback, _detail):
        created, _ = self._sync({'anime': [SIMKL_ANIME]})

        self.assertEqual(created, 1)
        item = WatchedItem.objects.get()
        self.assertEqual(item.tmdb_id, 45790)
        self.assertEqual(item.dedup_key, 'show:45790:s01e01')

    def test_keeps_the_date_of_rows_inherited_from_trakt(self, _episodes, _playback, _detail):
        real_date = timezone.now() - timedelta(days=900)
        WatchedItem.objects.create(
            dedup_key='show:67386:s01e01', source='trakt', media_type='episode',
            title='Dirk Gently', season=1, episode=1, watched_at=real_date, tmdb_id=67386,
        )

        self._sync({'shows': [SIMKL_SHOW]})

        untouched = WatchedItem.objects.get(dedup_key='show:67386:s01e01')
        self.assertEqual(untouched.watched_at, real_date)
        self.assertEqual(untouched.source, 'trakt')

    def test_reconciliation_never_deletes_trakt_rows(self, _episodes, _playback, _detail):
        WatchedItem.objects.create(
            dedup_key='movie:999', source='trakt', media_type='movie',
            title='Peli vieja de Trakt', watched_at=timezone.now(), tmdb_id=999,
        )
        self._sync({'movies': [SIMKL_MOVIE]}, full=True)
        self.assertEqual(WatchedItem.objects.count(), 2)

        # La película de Simkl desaparece de la fuente: se borra solo esa.
        self._sync({}, activities={'all': 'sello-2'}, full=True)

        self.assertEqual(WatchedItem.objects.count(), 1)
        self.assertEqual(WatchedItem.objects.get().source, 'trakt')

    def test_takes_episode_titles_from_simkl(self, mock_episodes, _playback, _detail):
        mock_episodes.return_value = [
            {'season': 1, 'episode': 1, 'title': 'Horizontes'},
            {'season': 1, 'episode': 2, 'title': 'Interconectividad'},
        ]

        self._sync({'shows': [SIMKL_SHOW]})

        self.assertEqual(WatchedItem.objects.get(episode=2).episode_title, 'Interconectividad')

    def test_stores_in_progress_ids_for_the_watching_ribbon(self, _episodes, mock_playback, _detail):
        mock_playback.return_value = [{
            'progress': 42.0,
            'episode': {'season': 1, 'number': 3},
            'show': {'ids': {'tmdb': '67386'}},
        }]

        self._sync({'shows': [SIMKL_SHOW]})

        self.assertEqual(SimklSyncState.load().in_progress_tmdb_ids, {67386})

    def test_ignores_anime_films_that_simkl_lists_as_one_episode_series(self, _episodes, _playback, _detail):
        """Si la obra ya existe como película, no se crea además como serie.

        Simkl cataloga las películas de anime como series de un episodio. Dejarlas pasar
        duplicaba la obra y pedía el id de película por la ruta /tv/ de TMDB, que
        devuelve otra obra distinta (una película quedó con el póster de otra serie).
        """
        WatchedItem.objects.create(
            dedup_key='movie:15370', source='trakt', media_type='movie',
            title='Neko no Ongaeshi', watched_at=timezone.now(), tmdb_id=15370,
        )
        created, _ = self._sync({'anime': [{
            'last_watched_at': '2026-07-18T22:11:00Z',
            'show': {'title': 'Neko no Ongaeshi', 'ids': {'simkl': 55, 'tmdb': '15370'}},
            'seasons': [{'number': 1, 'episodes': [{'number': 1, 'watched_at': '2026-07-18T22:11:00Z'}]}],
        }]})

        self.assertEqual(created, 0)
        self.assertEqual(WatchedItem.objects.count(), 1)
        self.assertEqual(WatchedItem.objects.get().media_type, 'movie')

    def test_resolves_anime_sequels_from_the_detail_endpoint(self, mock_episodes, _playback, _detail):
        """Las secuelas de anime llegan sin tmdb en el listado, pero la ficha sí lo trae.

        Y sus episodios reempiezan en 1: la equivalencia con TVDB los reubica en la
        temporada real, que es la numeración que ya usan los registros de Trakt.
        """
        mock_episodes.return_value = [
            {'episode': 4, 'season': None, 'title': 'Episode 4', 'tvdb': {'season': 2, 'episode': 4}},
        ]
        with patch('watching.utils.simkl.fetch_detail',
                   return_value={'ids': {'simkl': 1670325, 'tmdb': '69346', 'tvdb': '315500'}}) as detail:
            created, _ = self._sync({'anime': [{
                'last_watched_at': '2026-07-30T03:01:00Z',
                'show': {'title': 'Youjo Senki II', 'year': 2026, 'ids': {'simkl': 1670325}},
                'seasons': [{'number': 1, 'episodes': [{'number': 4, 'watched_at': '2026-07-30T03:01:00Z'}]}],
            }]})

        detail.assert_called_once()
        self.assertEqual(created, 1)
        item = WatchedItem.objects.get()
        self.assertEqual(item.tmdb_id, 69346)
        self.assertEqual((item.season, item.episode), (2, 4))
        self.assertEqual(item.dedup_key, 'show:69346:s02e04')
        self.assertEqual(item.episode_title, 'Episode 4')

    def test_sums_counters_when_several_simkl_entries_map_to_one_work(self, _episodes, _playback, _detail):
        """El anime viene partido por temporada: la secuela no debe pisar a la obra."""
        temporada_1 = {
            'last_watched_at': '2026-07-01T03:00:00Z',
            'watched_episodes_count': 12, 'total_episodes_count': 12, 'not_aired_episodes_count': 0,
            'show': {'title': 'Saga of Tanya the Evil', 'ids': {'simkl': 1, 'tmdb': '69346'}},
            'seasons': [{'number': 1, 'episodes': [{'number': 1, 'watched_at': '2026-07-01T03:00:00Z'}]}],
        }
        temporada_2 = {
            'last_watched_at': '2026-07-30T03:01:00Z',
            'watched_episodes_count': 4, 'total_episodes_count': 12, 'not_aired_episodes_count': 8,
            'show': {'title': 'Youjo Senki II', 'ids': {'simkl': 1670325}},
            'seasons': [{'number': 1, 'episodes': [{'number': 4, 'watched_at': '2026-07-30T03:01:00Z'}]}],
        }
        with patch('watching.utils.simkl.fetch_detail',
                   return_value={'ids': {'tmdb': '69346'}}):
            self._sync({'anime': [temporada_1, temporada_2]})

        item = WatchedItem.objects.filter(tmdb_id=69346).first()
        self.assertEqual(item.available_episodes, 24)  # 12 + 12, no los 12 de la secuela

    def test_keeps_the_title_the_work_already_had(self, _episodes, _playback, _detail):
        """Simkl nombra distinto que Trakt; la tarjeta no debe cambiar de nombre."""
        WatchedItem.objects.create(
            dedup_key='show:69346:s02e03', source='trakt', media_type='episode',
            title='Saga of Tanya the Evil', year=2017, season=2, episode=3,
            watched_at=timezone.now() - timedelta(days=10), tmdb_id=69346,
        )
        _episodes.return_value = [
            {'episode': 4, 'season': None, 'title': 'Episode 4', 'tvdb': {'season': 2, 'episode': 4}},
        ]
        with patch('watching.utils.simkl.fetch_detail',
                   return_value={'ids': {'tmdb': '69346'}}):
            self._sync({'anime': [{
                'last_watched_at': '2026-07-30T03:01:00Z',
                'show': {'title': 'Youjo Senki II', 'year': 2026, 'ids': {'simkl': 1670325}},
                'seasons': [{'number': 1, 'episodes': [{'number': 4, 'watched_at': '2026-07-30T03:01:00Z'}]}],
            }]})

        self.assertEqual(
            WatchedItem.objects.get(dedup_key='show:69346:s02e04').title,
            'Saga of Tanya the Evil',
        )
        # El año también: la secuela es de 2026, pero la obra es de 2017.
        self.assertEqual(WatchedItem.objects.get(dedup_key='show:69346:s02e04').year, 2017)

    def test_skips_items_without_any_resolvable_id(self, _episodes, _playback, _detail):
        created, _ = self._sync({'shows': [{
            'last_watched_at': '2026-07-02T03:00:00Z',
            'show': {'title': 'Sin ids', 'ids': {'simkl': 5}},
            'seasons': [{'number': 1, 'episodes': [{'number': 1, 'watched_at': '2026-07-02T03:00:00Z'}]}],
        }]})

        self.assertEqual(created, 0)
        self.assertEqual(WatchedItem.objects.count(), 0)


class WatchingViewTests(TestCase):
    def _create_episode(self, tmdb_id, season, episode, watched_at, title='Avenue 5', suffix=''):
        return WatchedItem.objects.create(
            dedup_key=f"show:{tmdb_id}:s{season:02d}e{episode:02d}{suffix}",
            source='simkl',
            media_type='episode',
            title=title,
            season=season,
            episode=episode,
            watched_at=watched_at,
            tmdb_id=tmdb_id,
        )

    def _create_movie(self, tmdb_id, watched_at, title='Blade Runner 2049', suffix=''):
        return WatchedItem.objects.create(
            dedup_key=f"movie:{tmdb_id}{suffix}",
            source='simkl',
            media_type='movie',
            title=title,
            year=2017,
            watched_at=watched_at,
            tmdb_id=tmdb_id,
        )

    def test_default_view_shows_series_and_hides_movies(self):
        now = timezone.now()
        self._create_episode(500, 1, 1, now)
        self._create_movie(42, now)

        response = self.client.get(reverse('watching:index'))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['active_tipo'], 'series')
        self.assertContains(response, 'Avenue 5')
        self.assertNotContains(response, 'Blade Runner 2049')
        # El header singulariza: "1 serie", "2 series"
        self.assertContains(response, '1 serie')

    def test_movies_tab_shows_movies_and_counter_label(self):
        now = timezone.now()
        self._create_episode(500, 1, 1, now)
        self._create_movie(42, now)

        response = self.client.get(reverse('watching:index'), {'tipo': 'peliculas'})

        self.assertEqual(response.context['active_tipo'], 'peliculas')
        self.assertContains(response, 'Blade Runner 2049')
        self.assertNotContains(response, 'Avenue 5')
        self.assertContains(response, '1 película')

    def test_invalid_tipo_falls_back_to_series(self):
        response = self.client.get(reverse('watching:index'), {'tipo': 'podcasts'})

        self.assertEqual(response.context['active_tipo'], 'series')

    def test_episodes_of_same_show_group_into_one_card(self):
        now = timezone.now()
        self._create_episode(500, 1, 1, now - timedelta(days=2))
        self._create_episode(500, 1, 2, now - timedelta(days=1))
        self._create_episode(500, 1, 3, now)

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
        self._create_episode(500, 1, 1, now - timedelta(days=1))
        self._create_episode(500, 1, 1, now, suffix='#2')

        response = self.client.get(reverse('watching:index'))

        card = response.context['cards'][0]
        self.assertEqual(card['plays'], 2)
        self.assertEqual(card['episode_count'], 1)
        self.assertEqual(card['episode_total'], 1)

    def test_show_card_uses_total_episodes_when_available(self):
        item = self._create_episode(500, 1, 1, timezone.now())
        item.total_episodes = 21
        item.save(update_fields=['total_episodes'])

        response = self.client.get(reverse('watching:index'))

        self.assertEqual(response.context['cards'][0]['episode_total'], 21)
        self.assertContains(response, '21')

    def test_recent_show_gets_watching_ribbon_and_old_show_does_not(self):
        now = timezone.now()
        self._create_episode(500, 1, 1, now, title='Serie Reciente')
        self._create_episode(600, 2, 5, now - timedelta(days=40), title='Serie Vieja')

        response = self.client.get(reverse('watching:index'))

        cards = {card['latest'].title: card for card in response.context['cards']}
        self.assertTrue(cards['Serie Reciente']['is_watching'])
        self.assertFalse(cards['Serie Vieja']['is_watching'])
        self.assertContains(response, 'watching-ribbon', count=1)

    def test_simkl_progress_decides_the_ribbon_when_available(self):
        now = timezone.now()
        # La reciente no está a medias en Simkl; la vieja sí: manda el dato, no la ventana.
        self._create_episode(500, 1, 1, now, title='Serie Reciente')
        self._create_episode(600, 2, 5, now - timedelta(days=40), title='Serie Vieja')
        state = SimklSyncState.load()
        state.in_progress_ids = '600'
        state.save(update_fields=['in_progress_ids'])

        response = self.client.get(reverse('watching:index'))

        cards = {card['latest'].title: card for card in response.context['cards']}
        self.assertFalse(cards['Serie Reciente']['is_watching'])
        self.assertTrue(cards['Serie Vieja']['is_watching'])

    def test_recent_complete_show_does_not_get_watching_ribbon(self):
        now = timezone.now()
        item = self._create_episode(500, 1, 8, now, title='Serie Completa')
        item.total_episodes = 8
        item.available_episodes = 8
        item.save(update_fields=['total_episodes', 'available_episodes'])

        response = self.client.get(reverse('watching:index'))

        self.assertFalse(response.context['cards'][0]['is_watching'])
        self.assertNotContains(response, 'watching-ribbon')

    def test_rewatched_movie_groups_and_shows_play_count(self):
        now = timezone.now()
        for i in range(2):
            self._create_movie(77, now - timedelta(days=i), title='Interstellar', suffix=f"#{i}")

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
        item = self._create_episode(500, 1, 1, timezone.now())
        item.user_rating = 9
        item.public_rating = 8.6
        item.save(update_fields=['user_rating', 'public_rating'])

        response = self.client.get(reverse('watching:index'))

        self.assertContains(response, 'Mi Calificación')
        self.assertContains(response, 'Calificación General')
        self.assertContains(response, '4.5 de 5')

    def test_stats_page_groups_by_tmdb_id(self):
        now = timezone.now()
        self._create_episode(500, 1, 1, now)
        self._create_episode(500, 1, 2, now)
        self._create_movie(42, now)

        response = self.client.get(reverse('watching:stats'))

        self.assertEqual(response.status_code, 200)
        # Dos episodios de la misma serie cuentan como una sola serie en el año
        self.assertContains(response, '[1]')

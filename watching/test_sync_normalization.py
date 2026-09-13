import copy
import io
import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import requests
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import SimpleTestCase, TestCase, override_settings

from . import simkl
from .anime_mapping import UnresolvedEpisode, resolve_series_anime
from .models import SimklSyncState, WatchedItem
from .nuvio import read_watched, recovery_candidates
from .tests import SIMKL_SHOW
from .utils import _pending_after_last_watched, refresh_watching_from_simkl


CATALOG = [{'episode': 8, 'type': 'episode', 'aired': True,
            'tvdb': {'season': 17, 'episode': 48}}]


class AnimeTranslationTests(SimpleTestCase):
    def test_bleach_series_to_native_anime(self):
        target = resolve_series_anime('tt14986406', 4, 8, lambda *a, **kw: CATALOG)
        self.assertEqual((target.simkl_id, target.number, target.season, target.episode), (2671730, 8, 17, 48))

    def test_ambiguous_missing_or_special_catalog_never_marks(self):
        for catalog in ([], CATALOG * 2, [dict(CATALOG[0], type='special')]):
            with self.subTest(catalog=catalog), self.assertRaises(UnresolvedEpisode):
                resolve_series_anime('tt14986406', 4, 8, lambda *a, **kw: catalog)

    def test_unknown_season_is_not_extrapolated(self):
        with self.assertRaises(UnresolvedEpisode):
            resolve_series_anime('tt14986406', 3, 8, lambda *a, **kw: CATALOG)

    def test_properties_decodes_java_escaping_and_selects_profile(self):
        payload = {'items': [{'id': 'mal:41467', 'name': 'Bleach: final', 'entries': []}]}
        encoded = json.dumps(payload).replace(':', '\\:').replace('=', '\\=')
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'watched.properties'
            path.write_text('watched_2=' + encoded, encoding='utf-8')
            self.assertEqual(read_watched(path, '2'), payload['items'])
            with self.assertRaises(ValueError):
                read_watched(path, '1')

    def test_properties_uses_simkl_groups_in_desktop_snapshot(self):
        groups = [{'id': 'mal:41467', 'entries': [{'season': 4, 'episode': 8}]}]
        payload = {'items': [], 'providerPayloads': {'simkl': {'itemGroups': groups}}}
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'watched.properties'
            path.write_text('watched_1=' + json.dumps(payload).replace(':', '\\:'), encoding='utf-8')
            self.assertEqual(read_watched(path), groups)

    def test_recovery_deduplicates_explicit_marks_and_keeps_first_date(self):
        records = [{'id': 'mal:41467', 'entries': [
            {'season': 4, 'episode': 8, 'markedAtEpochMs': 1789242855621},
            {'season': 4, 'episode': 8, 'markedAtEpochMs': 1789242856621},
        ]}]
        candidates, errors = recovery_candidates(records, 'mal:41467', datetime(2026, 9, 12, tzinfo=timezone.utc), lambda *a, **kw: CATALOG)
        self.assertEqual(len(candidates), 1)
        self.assertEqual(errors, [])
        self.assertEqual(candidates[0][1].timestamp(), 1789242855.621)

    def test_silo_future_season_does_not_keep_watching(self):
        item = {'seasons': [{'number': 3, 'episodes': [{'number': 10, 'watched_at': '2026-09-05T03:19:46Z'}]}]}
        self.assertEqual(_pending_after_last_watched(item, {(3, 10): {'aired': True}, (4, 1): {'aired': False}}), 0)

    def test_current_season_stays_watching_between_weekly_releases(self):
        item = {'seasons': [{'number': 3, 'episodes': [{'number': 9, 'watched_at': '2026-09-05T03:19:46Z'}]}]}
        self.assertEqual(_pending_after_last_watched(item, {(3, 10): {'aired': False}, (4, 1): {'aired': False}}), 1)

    def test_future_cour_with_no_watches_does_not_reactivate(self):
        self.assertEqual(_pending_after_last_watched({}, {(1, 1): {'aired': False}}), 0)
        self.assertEqual(_pending_after_last_watched({}, {(1, 1): {'aired': True}}), 1)

    def test_unknown_air_date_does_not_invent_a_premiere(self):
        self.assertEqual(_pending_after_last_watched({}, {(1, 1): {'date': None}}), 0)

    @patch('watching.simkl._get', return_value={'error': 'unavailable'})
    def test_malformed_library_is_not_treated_as_empty(self, get):
        with self.assertRaises(ValueError):
            simkl.fetch_all_items()

    @patch('watching.simkl._get', return_value={})
    def test_requests_explicit_anime_mapping(self, get):
        self.assertEqual(simkl.fetch_all_items(), {})
        self.assertEqual(get.call_args.kwargs['extended'], 'full_anime_seasons')


@override_settings(TMDB_API_KEY=None)
class NormalizationSyncTests(TestCase):
    def sync(self, payload, catalog=None):
        with patch('watching.utils.simkl.fetch_activities', return_value={'all': '2026-09-13T00:00:00Z'}), patch('watching.utils.simkl.fetch_all_items', return_value=payload), patch('watching.utils.simkl.fetch_detail', return_value={}), patch('watching.utils.simkl.fetch_episodes', return_value=catalog or []):
            return refresh_watching_from_simkl(full=True)

    def test_inline_tvdb_mapping_in_shows_is_authoritative(self):
        item = copy.deepcopy(SIMKL_SHOW)
        item['anime_type'] = 'tv'
        item['seasons'] = [{'number': 1, 'episodes': [{'number': 8, 'watched_at': '2026-09-12T19:54:15Z', 'tvdb': {'season': 17, 'episode': 48}}]}]
        self.sync({'shows': [item]}, CATALOG)
        row = WatchedItem.objects.get()
        self.assertEqual((row.season, row.episode), (17, 48))

    def test_series_coordinates_and_anime_coordinates_deduplicate(self):
        series = {'show': {'ids': {'simkl': 999, 'imdb': 'tt14986406', 'tmdb': '30984'}}, 'seasons': [{'number': 4, 'episodes': [{'number': 8, 'watched_at': '2026-09-12T19:54:15Z'}]}]}
        anime = {'show': {'ids': {'simkl': 2671730}}, 'seasons': [{'number': 1, 'episodes': [{'number': 8, 'watched_at': '2026-09-12T19:54:15Z'}]}]}
        self.sync({'shows': [series], 'anime': [anime]}, CATALOG)
        self.assertEqual(WatchedItem.objects.count(), 1)
        self.assertEqual(WatchedItem.objects.get().dedup_key, 'show:329809:s17e48')

    def test_simkl_identity_survives_a_tmdb_change(self):
        self.sync({'shows': [SIMKL_SHOW]})
        changed = copy.deepcopy(SIMKL_SHOW)
        changed['show']['ids']['tmdb'] = 987654
        self.sync({'shows': [changed]})
        self.assertEqual(set(WatchedItem.objects.values_list('tmdb_id', flat=True)), {67386})

    def test_bleach_repair_preserves_original_series_and_trakt_date(self):
        when = datetime(2020, 1, 1, tzinfo=timezone.utc)
        for tid, sid, source in [(329809, None, 'trakt'), (30984, 1300367, 'simkl'), (30984, None, 'trakt')]:
            episode = 1 if sid or tid == 329809 else 2
            WatchedItem.objects.create(tmdb_id=tid, simkl_id=sid, source=source, media_type='episode', title='Bleach', season=17, episode=episode, watched_at=when, dedup_key=f'show:{tid}:s17e{episode:02d}')
        item = {'show': {'ids': {'simkl': 1300367, 'tmdb': '30984'}}, 'seasons': [{'number': 1, 'episodes': [{'number': 1, 'watched_at': '2026-08-02T18:36:37Z', 'tvdb': {'season': 17, 'episode': 1}}]}]}
        self.sync({'anime': [item]})
        self.sync({'anime': [item]})
        self.assertEqual(WatchedItem.objects.count(), 2)
        self.assertEqual(WatchedItem.objects.get(tmdb_id=329809).watched_at, when)
        self.assertTrue(WatchedItem.objects.filter(tmdb_id=30984, episode=2).exists())

    def test_catalog_failure_rolls_back_identity_repairs(self):
        WatchedItem.objects.create(tmdb_id=30984, simkl_id=1300367, media_type='episode', title='Bleach', season=17, episode=1, watched_at=datetime.now(timezone.utc), dedup_key='show:30984:s17e01')
        with patch('watching.utils.simkl.fetch_activities', return_value={'all': 'new'}), patch('watching.utils.simkl.fetch_all_items', return_value={'shows': [SIMKL_SHOW]}), patch('watching.utils.simkl.fetch_episodes', side_effect=requests.Timeout):
            with self.assertRaises(requests.Timeout):
                refresh_watching_from_simkl(full=True)
        self.assertEqual(WatchedItem.objects.get().tmdb_id, 30984)

    def test_duplicate_category_does_not_double_aggregates(self):
        self.sync({'shows': [SIMKL_SHOW], 'anime': [SIMKL_SHOW]})
        self.assertEqual(WatchedItem.objects.count(), 2)
        self.assertEqual(WatchedItem.objects.first().available_episodes, 8)

    def test_incremental_completion_preserves_other_cour(self):
        state = SimklSyncState.load()
        state.last_activity_at = 'old'
        state.pending_ids = '67386,999'
        state.entry_pending = {'222': {'tmdb_id': 67386, 'pending': True}, '333': {'tmdb_id': 67386, 'pending': True}, '444': {'tmdb_id': 999, 'pending': True}}
        state.save()
        completed = dict(SIMKL_SHOW, status='completed')
        with patch('watching.utils.simkl.fetch_activities', return_value={'all': 'new'}), patch('watching.utils.simkl.fetch_all_items', return_value={'shows': [completed]}), patch('watching.utils.simkl.fetch_episodes', return_value=[]):
            refresh_watching_from_simkl()
        self.assertEqual(SimklSyncState.load().pending_tmdb_ids, {67386, 999})
        self.assertFalse(SimklSyncState.load().entry_pending['222']['pending'])


class RecoveryCommandTests(SimpleTestCase):
    @override_settings(SIMKL_CLIENT_ID='test', SIMKL_ACCESS_TOKEN='test')
    @patch('watching.simkl.requests.post')
    def test_write_uses_only_native_cour_and_episode(self, post):
        post.return_value.json.return_value = {'added': {'episodes': 1}}
        simkl.add_anime_history(2671730, 8, datetime(2026, 9, 12, tzinfo=timezone.utc))
        body = post.call_args.kwargs['json']
        self.assertEqual(body['shows'][0]['ids'], {'simkl': 2671730})
        self.assertEqual(body['shows'][0]['episodes'][0]['number'], 8)
        self.assertNotIn('seasons', body['shows'][0])

    @override_settings(SIMKL_CLIENT_ID='test', SIMKL_ACCESS_TOKEN='test')
    @patch('watching.simkl.requests.post')
    def test_not_found_is_a_failure_even_with_http_200(self, post):
        post.return_value.json.return_value = {'not_found': {'shows': [{'ids': {'simkl': 2671730}}]}}
        with self.assertRaises(ValueError):
            simkl.add_anime_history(2671730, 8, datetime.now(timezone.utc))

    @patch('watching.management.commands.recover_nuvio_watched.read_watched')
    @patch('watching.simkl.fetch_episodes', return_value=CATALOG)
    @patch('watching.simkl.fetch_all_items', return_value={})
    @patch('watching.simkl.add_anime_history')
    def test_default_is_dry_run(self, write, library, catalog, read):
        read.return_value = [{'id': 'mal:41467', 'entries': [{'season': 4, 'episode': 8, 'markedAtEpochMs': 1789242855621}]}]
        out = io.StringIO()
        call_command('recover_nuvio_watched', 'unused', content_id='mal:41467', since='2026-09-12T00:00:00-05:00', stdout=out)
        write.assert_not_called()
        self.assertEqual(json.loads(out.getvalue())['pending'][0]['episode'], 8)

    @patch('watching.management.commands.recover_nuvio_watched.read_watched')
    @patch('watching.simkl.fetch_episodes', return_value=CATALOG)
    @patch('watching.simkl.fetch_all_items', return_value={})
    @patch('watching.simkl.add_anime_history')
    def test_unconfirmed_write_is_not_reported_as_success(self, write, library, catalog, read):
        read.return_value = [{'id': 'mal:41467', 'entries': [{'season': 4, 'episode': 8, 'markedAtEpochMs': 1789242855621}]}]
        with self.assertRaises(CommandError):
            call_command('recover_nuvio_watched', 'unused', content_id='mal:41467', since='2026-09-12T00:00:00-05:00', apply=True, stdout=io.StringIO())
        write.assert_called_once()

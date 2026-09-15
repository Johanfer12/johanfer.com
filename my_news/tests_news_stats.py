import json
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .models import FeedSource, News


class NewsStatsTests(TestCase):
    """Panel de «cuántas noticias trae cada fuente»."""

    def setUp(self):
        self.user = get_user_model().objects.create_superuser(
            username='admin', email='admin@example.com', password='pass'
        )
        self.client.force_login(self.user)
        self.gizmodo = FeedSource.objects.create(name='Gizmodo', url='https://a.test/feed')
        self.wowhead = FeedSource.objects.create(name='Wowhead', url='https://b.test/feed')
        self.counter = 0

    def make_news(self, source, *, days_ago=0, hour=12, **flags):
        self.counter += 1
        published = timezone.localtime().replace(
            hour=hour, minute=0, second=0, microsecond=0
        ) - timedelta(days=days_ago)
        return News.objects.create(
            title=f'Noticia {self.counter}',
            description='Resumen',
            link=f'https://example.test/{self.counter}',
            published_date=published,
            source=source,
            guid=f'guid-{self.counter}',
            is_ai_processed=flags.pop('is_ai_processed', True),
            **flags,
        )

    def stats(self, **params):
        return self.client.get(reverse('my_news:news_stats'), params)

    def payload(self, response, key):
        return json.loads(response.context[key])

    def test_requires_superuser(self):
        self.client.logout()
        response = self.stats()

        self.assertEqual(response.status_code, 302)
        self.assertIn('/noticias/login/', response.url)

    def test_sources_are_ranked_by_volume_and_split_by_outcome(self):
        for _ in range(4):
            self.make_news(self.gizmodo)
        self.make_news(self.gizmodo, is_filtered=True)
        self.make_news(self.wowhead)
        self.make_news(self.wowhead, is_redundant=True)

        response = self.stats(dias=7)

        self.assertEqual(self.payload(response, 'source_labels_json'), ['Gizmodo', 'Wowhead'])
        self.assertEqual(self.payload(response, 'source_feed_json'), [4, 1])
        self.assertEqual(self.payload(response, 'source_discarded_json'), [1, 1])
        self.assertEqual(response.context['total_news_window'], 7)
        self.assertEqual(response.context['total_feed'], 5)
        self.assertEqual(response.context['total_discarded'], 2)

    def test_unprocessed_news_counts_as_discarded(self):
        # Sin pasar por la IA no llega al feed, aunque no la haya filtrado nadie.
        self.make_news(self.gizmodo, is_ai_processed=False)

        response = self.stats()

        self.assertEqual(response.context['total_feed'], 0)
        self.assertEqual(response.context['total_discarded'], 1)

    def test_read_news_still_counts_as_having_reached_the_feed(self):
        # Borrar es «ya la leí»: la noticia sí llegó, y contarla como descartada
        # diría que la fuente trae basura cuando pasa justo lo contrario.
        self.make_news(self.gizmodo, is_deleted=True)

        response = self.stats()

        self.assertEqual(response.context['total_feed'], 1)
        self.assertEqual(response.context['total_discarded'], 0)

    def test_window_covers_whole_local_days_so_both_charts_agree(self):
        # Una noticia temprana del día más viejo de la ventana: con un corte de
        # «hace N×24 h» se colaría o se perdería según la hora de la petición.
        self.make_news(self.gizmodo, days_ago=6, hour=1)
        self.make_news(self.gizmodo, days_ago=7, hour=23)

        response = self.stats(dias=7)

        day_feed = self.payload(response, 'day_feed_json')
        day_discarded = self.payload(response, 'day_discarded_json')
        self.assertEqual(len(day_feed), 7)
        self.assertEqual(response.context['total_news_window'], 1)
        self.assertEqual(sum(day_feed) + sum(day_discarded), 1)

    def test_days_without_news_stay_in_the_series_as_zero(self):
        # Un hueco es justo lo que delata que la ingesta se paró.
        self.make_news(self.gizmodo, days_ago=0)

        response = self.stats(dias=7)

        self.assertEqual(self.payload(response, 'day_feed_json'), [0, 0, 0, 0, 0, 0, 1])
        self.assertEqual(len(self.payload(response, 'day_labels_json')), 7)

    def test_today_window_only_covers_today(self):
        self.make_news(self.gizmodo, days_ago=0)
        self.make_news(self.gizmodo, days_ago=1)

        response = self.stats(dias=1)

        self.assertEqual(response.context['total_news_window'], 1)
        self.assertEqual(len(self.payload(response, 'day_labels_json')), 1)

    def test_unsupported_window_falls_back_to_a_week(self):
        for value in ('30', 'abc', '', '0'):
            self.assertEqual(self.stats(dias=value).context['days'], 7)

    def test_empty_window_renders_without_charts_or_division_errors(self):
        response = self.stats(dias=1)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['discarded_share'], 0)
        self.assertEqual(response.context['daily_average'], 0)
        self.assertContains(response, 'No hay noticias en este periodo')
        self.assertNotContains(response, 'perSourceChart')

    def test_source_with_a_blank_name_still_gets_a_bar(self):
        # La fuente es obligatoria, así que nunca falta; lo que sí puede pasar
        # es que se haya guardado sin nombre.
        anonima = FeedSource.objects.create(name='', url='https://c.test/feed')
        self.make_news(anonima)

        response = self.stats()

        self.assertEqual(self.payload(response, 'source_labels_json'), ['Sin nombre'])

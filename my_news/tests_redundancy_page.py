from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .models import FeedSource, FilterWord, News


class RedundancyPageTests(TestCase):
    """Página de diagnóstico del filtrado, con sus filas por tandas."""

    def setUp(self):
        self.user = get_user_model().objects.create_superuser(
            username='admin', email='admin@example.com', password='pass'
        )
        self.client.force_login(self.user)
        self.source = FeedSource.objects.create(name='Gizmodo', url='https://a.test/feed')
        self.word = FilterWord.objects.create(word='horóscopo')
        self.counter = 0

    def make_news(self, *, created_at=None, **flags):
        self.counter += 1
        news = News.objects.create(
            title=f'Noticia {self.counter}',
            description='Texto largo de la noticia.',
            link=f'https://example.test/{self.counter}',
            published_date=timezone.now(),
            source=self.source,
            guid=f'guid-{self.counter}',
            is_ai_processed=True,
            **flags,
        )
        if created_at is not None:
            News.objects.filter(pk=news.pk).update(created_at=created_at)
            news.refresh_from_db()
        return news

    def rows(self, **params):
        params.setdefault('tab', 'keyword')
        return self.client.get(reverse('my_news:redundancy_rows'), params)

    def test_page_ships_without_any_news_row(self):
        self.make_news(filtered_by=self.word, is_filtered=True)

        response = self.client.get(reverse('my_news:redundancy_test'))

        self.assertEqual(response.status_code, 200)
        # El contador sí sale; el texto de la noticia, no: lo pide la pestaña.
        self.assertContains(response, 'data-rows-tab="keyword"')
        self.assertNotContains(response, 'Texto largo de la noticia')

    def test_tabs_do_not_double_count_a_news_item(self):
        # Redundante y además cazada por una palabra filtro: pertenece a la
        # categoría de más peso y solo a esa.
        self.make_news(filtered_by=self.word, is_filtered=True, is_redundant=True,
                       similar_to=self.make_news())

        self.assertEqual(self.rows(tab='keyword').json()['matched'], 0)
        self.assertEqual(self.rows(tab='redundant').json()['matched'], 1)

    def test_redundant_rows_show_both_sides_of_the_pair(self):
        original = self.make_news()
        original.title = 'La original'
        original.save(update_fields=['title'])
        self.make_news(is_redundant=True, similar_to=original, similarity_score=0.91)

        html = self.rows(tab='redundant').json()['html']

        self.assertIn('La original', html)
        self.assertIn('0.9100', html)

    def test_redundant_without_its_pair_is_left_out(self):
        # Sin `similar_to` no hay nada con lo que comparar, y la fila saldría
        # a medias.
        self.make_news(is_redundant=True)

        self.assertEqual(self.rows(tab='redundant').json()['matched'], 0)

    def test_rows_are_limited_to_the_requested_day(self):
        self.make_news(filtered_by=self.word, is_filtered=True)
        yesterday = timezone.now() - timedelta(days=1)
        self.make_news(filtered_by=self.word, is_filtered=True, created_at=yesterday)

        today = self.rows(date=timezone.localdate().isoformat()).json()
        before = self.rows(date=timezone.localdate(yesterday).isoformat()).json()

        self.assertEqual(today['matched'], 1)
        self.assertEqual(before['matched'], 1)

    def test_batches_walk_the_list_without_repeating(self):
        from my_news.views import REDUNDANCY_PAGE_SIZE
        total = REDUNDANCY_PAGE_SIZE + 3
        for _ in range(total):
            self.make_news(filtered_by=self.word, is_filtered=True)

        first = self.rows().json()
        second = self.rows(offset=first['next_offset']).json()

        self.assertEqual(first['returned'], REDUNDANCY_PAGE_SIZE)
        self.assertTrue(first['has_more'])
        self.assertEqual(second['returned'], 3)
        self.assertFalse(second['has_more'])
        self.assertEqual(first['matched'], total)

    def test_unknown_tab_is_rejected(self):
        self.assertEqual(self.rows(tab='inventada').status_code, 400)

    def test_unreadable_date_and_offset_fall_back_to_today_and_zero(self):
        self.make_news(filtered_by=self.word, is_filtered=True)

        payload = self.rows(date='no-es-fecha', offset='abc').json()

        self.assertEqual(payload['matched'], 1)
        self.assertEqual(payload['next_offset'], 1)

    def test_rows_endpoint_is_superuser_only(self):
        self.client.logout()
        response = self.rows()

        self.assertEqual(response.status_code, 302)
        self.assertIn('/noticias/login/', response.url)

    def test_page_counters_agree_with_the_rows_endpoint(self):
        # Ambos calculan el día por su cuenta; si divergieran, la pestaña
        # diría un número y traería otro.
        for _ in range(3):
            self.make_news(filtered_by=self.word, is_filtered=True)
        self.make_news(is_ai_filtered=True)

        page = self.client.get(reverse('my_news:redundancy_test'))

        self.assertEqual(
            page.context['filtered_keyword_today_count'], self.rows(tab='keyword').json()['matched']
        )
        self.assertEqual(
            page.context['filtered_ai_today_count'], self.rows(tab='ai').json()['matched']
        )

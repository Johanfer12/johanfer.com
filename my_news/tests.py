from datetime import timedelta
import uuid

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .models import FeedSource, News


class NewsFeedOrderingTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.source = FeedSource.objects.create(
            name='Test Feed',
            url='https://example.com/rss.xml',
        )
        cls.superuser = get_user_model().objects.create_superuser(
            username='news-admin',
            email='news-admin@example.com',
            password='test-pass-123',
        )

    def create_news_batch(self, count, *, prefix='news', published_dates=None):
        base_time = timezone.now()
        created = []

        for index in range(count):
            published_at = (
                published_dates[index]
                if published_dates is not None
                else base_time - timedelta(minutes=index)
            )
            created.append(
                News.objects.create(
                    title=f'{prefix} {index}',
                    description=f'Description for {prefix} {index}',
                    link=f'https://example.com/{prefix}/{index}',
                    published_date=published_at,
                    source=self.source,
                    guid=f'{prefix}-{uuid.uuid4().hex}-{index}',
                )
            )

        return created

    def setUp(self):
        cache.clear()

    def test_get_page_orders_descending_with_id_tiebreaker(self):
        same_time = timezone.now()
        older_time = same_time - timedelta(hours=1)

        self.create_news_batch(
            5,
            prefix='desc-order',
            published_dates=[same_time, same_time, older_time, older_time, older_time],
        )

        response = self.client.get(reverse('my_news:get_page'), {'order': 'desc', 'page': 1})
        payload = response.json()

        expected_ids = list(
            News.visible.order_by('-published_date', '-id').values_list('id', flat=True)
        )
        returned_ids = [card['id'] for card in payload['cards']]

        self.assertEqual(returned_ids, expected_ids)

    def test_get_page_orders_ascending_with_id_tiebreaker(self):
        same_time = timezone.now()
        newer_time = same_time + timedelta(hours=1)

        self.create_news_batch(
            5,
            prefix='asc-order',
            published_dates=[same_time, same_time, newer_time, newer_time, newer_time],
        )

        response = self.client.get(reverse('my_news:get_page'), {'order': 'asc', 'page': 1})
        payload = response.json()

        expected_ids = list(
            News.visible.order_by('published_date', 'id').values_list('id', flat=True)
        )
        returned_ids = [card['id'] for card in payload['cards']]

        self.assertEqual(returned_ids, expected_ids)

    def test_delete_returns_actual_page_replacement_and_undo_restores_original_page(self):
        self.create_news_batch(26, prefix='delete-flow')
        ordered_ids = list(
            News.visible.order_by('-published_date', '-id').values_list('id', flat=True)
        )
        deleted_id = ordered_ids[10]
        expected_replacement_id = ordered_ids[25]

        delete_response = self.client.post(
            reverse('my_news:delete_news', args=[deleted_id]),
            {
                'current_page': 1,
                'order': 'desc',
                'saved_only': 'false',
            },
        )
        delete_payload = delete_response.json()

        self.assertEqual(delete_payload['status'], 'success')
        self.assertEqual(delete_payload['card']['id'], expected_replacement_id)

        current_page_ids = [
            card['id']
            for card in self.client.get(
                reverse('my_news:get_page'),
                {'order': 'desc', 'page': 1},
            ).json()['cards']
        ]
        expected_after_delete = [news_id for news_id in ordered_ids if news_id != deleted_id][:25]
        self.assertEqual(current_page_ids, expected_after_delete)

        undo_response = self.client.post(
            reverse('my_news:undo_delete', args=[deleted_id]),
            {'saved_only': 'false'},
        )
        undo_payload = undo_response.json()

        self.assertEqual(undo_payload['status'], 'success')
        self.assertEqual(undo_payload['card']['id'], deleted_id)

        restored_page_ids = [
            card['id']
            for card in self.client.get(
                reverse('my_news:get_page'),
                {'order': 'desc', 'page': 1},
            ).json()['cards']
        ]
        self.assertEqual(restored_page_ids, ordered_ids[:25])

    def test_initial_backup_cards_follow_same_ordering_rule(self):
        same_time = timezone.now()
        self.create_news_batch(30, prefix='backup-order', published_dates=[same_time] * 30)

        self.client.force_login(self.superuser)
        response = self.client.get(reverse('my_news:news_list'), {'order': 'asc'})

        backup_ids = [card['id'] for card in response.context['backup_cards']]
        expected_backup_ids = list(
            News.visible.filter(is_saved=False)
            .order_by('published_date', 'id')
            .values_list('id', flat=True)[25:30]
        )

        self.assertEqual(backup_ids, expected_backup_ids)

    def test_template_pagination_keeps_order_and_search_query(self):
        self.create_news_batch(26, prefix='foo-news')

        self.client.force_login(self.superuser)
        response = self.client.get(
            reverse('my_news:news_list'),
            {'order': 'asc', 'q': 'foo-news'},
        )

        self.assertContains(response, '?page=2&order=asc')
        self.assertContains(response, 'q=foo-news')

from datetime import timedelta
import uuid

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import SimpleTestCase
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .models import FeedSource, News
from .services import FeedService, GroqRateLimiter


class GroqRateLimiterTests(SimpleTestCase):
    def setUp(self):
        FeedService._GROQ_RATE_LIMITER = GroqRateLimiter()
        FeedService._GROQ_RATE_LIMITER.SAFE_RPM_CAP = 100

    def test_model_limits_are_conservative_for_news_processing(self):
        limiter = GroqRateLimiter()

        self.assertEqual(limiter.get_limits('openai/gpt-oss-120b'), (6_000, 1))
        self.assertEqual(limiter.get_limits('qwen/qwen3-32b'), (4_500, 1))

    def test_retry_after_is_read_from_response_headers(self):
        class Response:
            headers = {'Retry-After': '42'}

        error = Exception('429 rate limit exceeded')
        error.response = Response()

        self.assertEqual(FeedService._extract_retry_after_seconds(error), 42)

    def test_retry_after_is_read_from_error_message(self):
        error = Exception('Rate limit reached. Please try again in 12.4s.')

        self.assertEqual(FeedService._extract_retry_after_seconds(error), 13)

    def test_long_retry_after_postpones_news_instead_of_sleeping(self):
        class Response:
            headers = {'Retry-After': '600'}

        class Completions:
            def create(self, **kwargs):
                error = Exception('429 rate limit exceeded')
                error.response = Response()
                raise error

        class Chat:
            completions = Completions()

        class Client:
            chat = Chat()

        description, short_answer, ai_filter = FeedService.process_content_with_groq(
            'Titulo',
            'Descripcion original',
            Client(),
            'openai/gpt-oss-120b',
            FeedService._DEFAULT_FILTER_INSTRUCTIONS,
            max_retries=2,
        )

        self.assertIsNone(description)
        self.assertIsNone(short_answer)
        self.assertIsNone(ai_filter)

    def test_single_large_request_does_not_wait_forever(self):
        limiter = GroqRateLimiter()
        limiter.MODEL_LIMITS = {'tiny-model': {'tpm': 100, 'rpm': 20}}

        estimated_tokens = limiter.acquire('tiny-model', 'x' * 1000, 1024)

        self.assertGreater(estimated_tokens, 25)

    def test_groq_failure_returns_empty_result_instead_of_original_content(self):
        class Completions:
            def create(self, **kwargs):
                raise Exception('429 rate limit exceeded')

        class Chat:
            completions = Completions()

        class Client:
            chat = Chat()

        description, short_answer, ai_filter = FeedService.process_content_with_groq(
            'Titulo',
            'Descripcion original sin procesar',
            Client(),
            'openai/gpt-oss-120b',
            FeedService._DEFAULT_FILTER_INSTRUCTIONS,
            max_retries=1,
        )

        self.assertIsNone(description)
        self.assertIsNone(short_answer)
        self.assertIsNone(ai_filter)

    def test_json_validation_error_retries_without_response_format(self):
        class Message:
            content = '{"summary": "Resumen procesado.", "short_answer": null, "ai_filter": null}'

        class Choice:
            message = Message()

        class Response:
            choices = [Choice()]

        class Completions:
            def __init__(self):
                self.calls = []

            def create(self, **kwargs):
                self.calls.append(kwargs)
                if len(self.calls) == 1:
                    raise Exception('Error code: 400 - json_validate_failed')
                return Response()

        class Chat:
            def __init__(self):
                self.completions = Completions()

        class Client:
            def __init__(self):
                self.chat = Chat()

        client = Client()
        description, short_answer, ai_filter = FeedService.process_content_with_groq(
            'Titulo',
            'Descripcion original',
            client,
            'openai/gpt-oss-120b',
            FeedService._DEFAULT_FILTER_INSTRUCTIONS,
            max_retries=2,
        )

        self.assertEqual(description, 'Resumen procesado.')
        self.assertIsNone(short_answer)
        self.assertIsNone(ai_filter)
        self.assertIn('response_format', client.chat.completions.calls[0])
        self.assertNotIn('response_format', client.chat.completions.calls[1])
        self.assertEqual(client.chat.completions.calls[1]['reasoning_effort'], 'low')

    def test_empty_groq_response_is_not_saved_as_summary(self):
        class Message:
            content = ''

        class Choice:
            message = Message()

        class Response:
            choices = [Choice()]

        class Completions:
            def create(self, **kwargs):
                return Response()

        class Chat:
            completions = Completions()

        class Client:
            chat = Chat()

        description, short_answer, ai_filter = FeedService.process_content_with_groq(
            'Titulo',
            'Descripcion original',
            Client(),
            'openai/gpt-oss-120b',
            FeedService._DEFAULT_FILTER_INSTRUCTIONS,
            max_retries=1,
        )

        self.assertIsNone(description)
        self.assertIsNone(short_answer)
        self.assertIsNone(ai_filter)


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
        self.client.force_login(self.superuser)
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
        self.client.force_login(self.superuser)
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
        self.client.force_login(self.superuser)
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

    def test_delete_respects_search_filter_when_computing_replacement(self):
        self.client.force_login(self.superuser)
        base_time = timezone.now()
        matching_dates = [base_time - timedelta(minutes=index) for index in range(26)]
        non_matching_dates = [base_time - timedelta(days=1, minutes=index) for index in range(3)]

        self.create_news_batch(26, prefix='query-hit', published_dates=matching_dates)
        self.create_news_batch(3, prefix='query-miss', published_dates=non_matching_dates)

        filtered_ids = list(
            News.visible.filter(title__icontains='query-hit')
            .order_by('-published_date', '-id')
            .values_list('id', flat=True)
        )
        deleted_id = filtered_ids[5]
        expected_replacement_id = filtered_ids[25]

        delete_response = self.client.post(
            reverse('my_news:delete_news', args=[deleted_id]),
            {
                'current_page': 1,
                'order': 'desc',
                'saved_only': 'false',
                'q': 'query-hit',
            },
        )
        delete_payload = delete_response.json()

        self.assertEqual(delete_payload['status'], 'success')
        self.assertEqual(delete_payload['total_news'], 25)
        self.assertEqual(delete_payload['card']['id'], expected_replacement_id)

        current_page_ids = [
            card['id']
            for card in self.client.get(
                reverse('my_news:get_page'),
                {'order': 'desc', 'page': 1, 'q': 'query-hit'},
            ).json()['cards']
        ]
        expected_after_delete = [news_id for news_id in filtered_ids if news_id != deleted_id][:25]
        self.assertEqual(current_page_ids, expected_after_delete)

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

    def test_public_news_view_shows_latest_available_day_and_ignores_personal_delete_flag(self):
        latest_time = timezone.now() - timedelta(days=38)
        previous_time = latest_time - timedelta(days=1)
        latest_date = timezone.localtime(latest_time).date()

        latest_public_news = News.objects.create(
            title='public latest',
            description='Visible en la fecha mas reciente',
            link='https://example.com/public-latest',
            published_date=latest_time,
            source=self.source,
            guid=f'public-latest-{uuid.uuid4().hex}',
            is_deleted=True,
        )
        News.objects.create(
            title='public previous',
            description='No visible porque es de un dia anterior',
            link='https://example.com/public-previous',
            published_date=previous_time,
            source=self.source,
            guid=f'public-previous-{uuid.uuid4().hex}',
        )

        response = self.client.get(reverse('my_news:news_list'))

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'news_public.html')
        self.assertTrue(response.context['public_news_mode'])
        self.assertContains(response, 'Noticias de Hoy')
        self.assertContains(response, 'public latest')
        self.assertNotContains(response, 'public previous')
        self.assertEqual(list(response.context['object_list']), [latest_public_news])
        self.assertEqual(response.context['public_news_date'], latest_date.strftime('%d/%m/%Y'))
        self.assertEqual(response.context['public_storage_key'], f'public-news-hidden:{latest_date.isoformat()}')

    def test_private_json_endpoint_requires_superuser(self):
        response = self.client.get(reverse('my_news:get_page'), {'page': 1, 'order': 'desc'})
        self.assertEqual(response.status_code, 302)
        self.assertIn('/noticias/login/', response['Location'])

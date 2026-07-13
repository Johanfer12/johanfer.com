from datetime import date, datetime, time, timedelta
from types import SimpleNamespace
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.utils import timezone as dj_timezone

from .models import Book, VisitLog
from .utils import build_shelf_url, sync_currently_reading

READING_ENTRY = {
    'book_id': '777',
    'title': 'Proyecto Hail Mary',
    'author_name': 'Andy Weir',
    'average_rating': '4.5',
    'book_description': 'Un hombre despierta solo en una nave.',
    'num_pages': '496',
    'book_published': '2021',
    'link': 'https://www.goodreads.com/review/show/777',
}


class CurrentlyReadingSyncTests(TestCase):
    def test_build_shelf_url_swaps_shelf_param(self):
        url = build_shelf_url('https://www.goodreads.com/review/list_rss/1?shelf=read', 'currently-reading')

        self.assertIn('shelf=currently-reading', url)
        self.assertNotIn('shelf=read&', url + '&')

    @patch('home_page.utils.fetch_feed_with_timeout')
    def test_creates_reading_book_without_date_or_rating(self, mock_fetch):
        mock_fetch.return_value = SimpleNamespace(entries=[READING_ENTRY])

        reading_ids = sync_currently_reading('https://example.com/rss?shelf=read', '/tmp')

        self.assertEqual(len(reading_ids), 1)
        book = Book.objects.get(id=reading_ids[0])
        self.assertTrue(book.is_reading)
        self.assertIsNone(book.date_read)
        self.assertEqual(book.my_rating, 0)

        # Segunda corrida: actualiza el mismo libro, no duplica
        reading_ids_again = sync_currently_reading('https://example.com/rss?shelf=read', '/tmp')
        self.assertEqual(reading_ids, reading_ids_again)
        self.assertEqual(Book.objects.count(), 1)


class BookshelfReadingViewTests(TestCase):
    def _create_read_book(self, pk_hint='read'):
        return Book.objects.create(
            title=f'Libro terminado {pk_hint}',
            author='Autor',
            cover_link='',
            my_rating=4,
            public_rating='4.1',
            date_read=date(2026, 1, 15),
            book_link=f'/book/show/{pk_hint}',
        )

    def _create_reading_book(self):
        return Book.objects.create(
            title='Libro en curso',
            author='Autora',
            cover_link='',
            my_rating=0,
            public_rating='4.5',
            date_read=None,
            is_reading=True,
            book_link='/book/show/reading-1',
        )

    def test_reading_book_appears_first_with_ribbon_and_no_details(self):
        self._create_read_book()
        self._create_reading_book()

        response = self.client.get('/bookshelf/')

        books = list(response.context['page_obj'])
        self.assertTrue(books[0].is_reading)
        self.assertContains(response, 'watching-ribbon')
        self.assertContains(response, 'Leyendo')

    def test_ajax_payload_handles_reading_book(self):
        self._create_reading_book()

        response = self.client.get('/bookshelf/', HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        payload = response.json()

        card = payload['books'][0]
        self.assertTrue(card['is_reading'])
        self.assertIsNone(card['date_read'])

    def test_stats_ignores_books_without_date(self):
        self._create_read_book()
        self._create_reading_book()

        response = self.client.get('/bookshelf/stats/')

        self.assertEqual(response.status_code, 200)
        self.assertNotIn('null', response.context['books_per_year_labels'])


class VisitLogMiddlewareTests(TestCase):
    def test_news_page_is_logged(self):
        response = self.client.get('/noticias/', HTTP_ACCEPT='text/html')

        self.assertEqual(response.status_code, 200)
        self.assertTrue(VisitLog.objects.filter(path='/noticias/').exists())

    def test_news_internal_endpoint_is_not_logged(self):
        response = self.client.get('/noticias/get-page/', HTTP_ACCEPT='text/html')

        self.assertEqual(response.status_code, 302)
        self.assertFalse(VisitLog.objects.filter(path='/noticias/get-page/').exists())


class VisitsViewTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = get_user_model().objects.create_superuser(
            username='admin-visitas',
            email='admin@example.com',
            password='test-password',
        )

    def setUp(self):
        self.client.force_login(self.admin)
        session = self.client.session
        session['visit_visitor_id'] = 'visitor-owner'
        session.save()

    def test_groups_visits_by_country_and_summarizes_own_visits(self):
        VisitLog.objects.create(
            ip_address='203.0.113.10',
            visitor_id='visitor-owner',
            country_code='NL',
            country='Netherlands',
            path='/bookshelf/',
        )
        VisitLog.objects.create(
            ip_address='203.0.113.11',
            visitor_id='visitor-other',
            country_code='NL',
            country='Netherlands',
            path='/spotify/',
        )
        VisitLog.objects.create(
            ip_address='203.0.113.12',
            visitor_id='visitor-other',
            country_code='TR',
            country='Turkey',
            path='/',
        )

        response = self.client.get('/visitas/')

        self.assertEqual(response.status_code, 200)
        groups = {group['country']: group for group in response.context['visit_groups']}
        self.assertEqual(groups['Netherlands']['visit_count'], 2)
        self.assertEqual(groups['Netherlands']['self_count'], 1)
        self.assertEqual(groups['Turkey']['visit_count'], 1)
        self.assertEqual(groups['Turkey']['self_count'], 0)
        self.assertContains(response, '2 visitas')
        self.assertContains(response, '(1 tuya)')

    def test_country_panels_are_closed_by_default(self):
        VisitLog.objects.create(
            ip_address='203.0.113.20',
            country_code='CO',
            country='Colombia',
            path='/',
        )

        response = self.client.get('/visitas/')

        self.assertContains(response, '<details class="visit-country-group">')
        self.assertNotContains(response, '<details class="visit-country-group" open>')

    def test_shows_all_visits_without_pagination(self):
        VisitLog.objects.bulk_create([
            VisitLog(
                ip_address=f'203.0.113.{index % 250}',
                country_code='NL',
                country='Netherlands',
                path=f'/page/{index}/',
            )
            for index in range(125)
        ])

        response = self.client.get('/visitas/')

        self.assertEqual(response.context['visit_groups'][0]['visit_count'], 125)
        self.assertNotContains(response, 'Siguiente')
        self.assertNotContains(response, 'pagination')

    def test_colombia_is_always_the_first_country(self):
        VisitLog.objects.create(
            ip_address='203.0.113.40',
            country_code='TR',
            country='Turkey',
            path='/',
        )
        VisitLog.objects.create(
            ip_address='203.0.113.41',
            country_code='CO',
            country='Colombia',
            path='/',
        )

        response = self.client.get('/visitas/')

        self.assertEqual(response.context['visit_groups'][0]['country'], 'Colombia')

    def test_date_filters_include_the_whole_selected_day(self):
        selected_day = date(2026, 7, 12)
        selected_visit = VisitLog.objects.create(
            ip_address='203.0.113.50',
            country='Colombia',
            path='/selected-day/',
        )
        other_visit = VisitLog.objects.create(
            ip_address='203.0.113.51',
            country='Colombia',
            path='/other-day/',
        )
        selected_at = dj_timezone.make_aware(
            datetime.combine(selected_day, time(23, 45)),
            dj_timezone.get_current_timezone(),
        )
        VisitLog.objects.filter(pk=selected_visit.pk).update(visited_at=selected_at)
        VisitLog.objects.filter(pk=other_visit.pk).update(
            visited_at=selected_at + timedelta(days=1),
        )

        response = self.client.get('/visitas/', {
            'from': selected_day.isoformat(),
            'to': selected_day.isoformat(),
        })

        self.assertEqual(response.context['total_visits'], 1)
        self.assertContains(response, '/selected-day/')
        self.assertNotContains(response, '/other-day/')

    def test_date_fields_use_native_editable_date_inputs(self):
        response = self.client.get('/visitas/')

        self.assertContains(response, 'type="date" name="from"')
        self.assertContains(response, 'type="date" name="to"')
        self.assertNotContains(response, 'showPicker')

    def test_deletes_selected_visits_from_compact_id_list(self):
        visits = [
            VisitLog.objects.create(
                ip_address=f'203.0.113.{60 + index}',
                country='Colombia',
                path=f'/delete/{index}/',
            )
            for index in range(3)
        ]

        response = self.client.post('/visitas/', {
            'action': 'delete_selected',
            'selected_visits': f'{visits[0].pk},{visits[2].pk}',
        })

        self.assertEqual(response.status_code, 302)
        self.assertQuerySetEqual(
            VisitLog.objects.order_by('pk'),
            [visits[1]],
        )

    @override_settings(DEBUG=True, VISITS_ALLOW_LOCAL_WITHOUT_LOGIN=True)
    def test_local_development_flag_allows_access_without_login(self):
        self.client.logout()

        response = self.client.get('/visitas/')

        self.assertEqual(response.status_code, 200)

    @override_settings(DEBUG=False, VISITS_ALLOW_LOCAL_WITHOUT_LOGIN=True)
    def test_local_development_flag_does_not_bypass_login_in_production(self):
        self.client.logout()

        response = self.client.get('/visitas/')

        self.assertEqual(response.status_code, 302)
        self.assertIn('/noticias/login/', response.url)

from datetime import date, datetime, time, timedelta
import io
import os
import tempfile
from types import SimpleNamespace
from unittest.mock import patch

from PIL import Image

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.utils import timezone as dj_timezone

from django.core.cache import cache

from .models import Book, OwnerSignature, VisitLog
from .utils import build_shelf_url, download_as_webp, sync_currently_reading
from .visit_stats import badge_count

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

    def test_country_cards_open_hidden_visit_modals(self):
        VisitLog.objects.create(
            ip_address='203.0.113.20',
            country_code='CO',
            country='Colombia',
            path='/',
        )

        response = self.client.get('/visitas/')

        self.assertContains(response, 'class="country-card-open"')
        self.assertContains(response, 'data-country-modal-target="country-visits-1"')
        self.assertContains(
            response,
            'class="country-visits-modal" id="country-visits-1"',
        )
        self.assertContains(response, 'aria-haspopup="dialog"')

    def test_each_country_group_has_a_select_all_control(self):
        VisitLog.objects.create(
            ip_address='203.0.113.21',
            country_code='CO',
            country='Colombia',
            path='/',
        )
        VisitLog.objects.create(
            ip_address='203.0.113.22',
            country_code='TR',
            country='Turkey',
            path='/',
        )

        response = self.client.get('/visitas/')

        self.assertContains(response, 'class="select-country-visits"', count=2)
        self.assertContains(response, 'Seleccionar todas las visitas de Colombia')
        self.assertContains(response, 'Seleccionar todas las visitas de Turkey')

    def test_local_and_unknown_countries_use_distinct_icons(self):
        VisitLog.objects.create(
            ip_address='127.0.0.1',
            country='Local',
            path='/local/',
        )
        VisitLog.objects.create(
            ip_address='203.0.113.24',
            country='',
            country_code='',
            path='/unknown/',
        )

        response = self.client.get('/visitas/')

        groups = {group['country']: group for group in response.context['visit_groups']}
        self.assertTrue(groups['Local']['is_local'])
        self.assertTrue(groups['País desconocido']['is_unknown'])
        self.assertContains(response, 'class="country-type-icon"', count=2)
        self.assertContains(response, '🏠')
        self.assertContains(response, '🌐')

    def test_delete_actions_use_custom_confirmation_modal(self):
        VisitLog.objects.create(
            ip_address='203.0.113.23',
            country='Colombia',
            path='/',
        )

        response = self.client.get('/visitas/')

        self.assertContains(response, 'id="delete-confirmation-modal"')
        self.assertContains(response, 'data-confirm-delete="selected"')
        self.assertContains(response, 'data-confirm-delete="country"')
        self.assertContains(response, 'data-confirm-delete="filtered"')
        self.assertContains(response, 'data-confirm-delete="one"')
        self.assertNotContains(response, 'id="select-all-visits"')
        self.assertNotContains(response, 'onclick="return confirm(')

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

    def test_offers_deleting_only_my_visits_in_the_country_modal(self):
        VisitLog.objects.create(
            ip_address='190.0.0.1',
            visitor_id='visitor-owner',
            country_code='CO',
            country='Colombia',
            path='/bookshelf/',
        )
        VisitLog.objects.create(
            ip_address='181.50.0.9',
            visitor_id='visitor-other',
            country_code='CO',
            country='Colombia',
            path='/',
        )

        response = self.client.get('/visitas/')

        self.assertContains(response, 'Eliminar mías')
        # El botón se lleva las marcadas: una sola fila la lleva.
        self.assertContains(response, 'data-self="1"', count=1)

    def test_hides_the_delete_mine_button_when_no_visit_is_mine(self):
        VisitLog.objects.create(
            ip_address='181.50.0.9',
            visitor_id='visitor-other',
            country_code='CO',
            country='Colombia',
            path='/',
        )

        response = self.client.get('/visitas/')

        self.assertNotContains(response, 'Eliminar mías')

    def test_delete_all_respects_the_active_filters(self):
        colombia_visit = VisitLog.objects.create(
            ip_address='203.0.113.70',
            country='Colombia',
            path='/delete-colombia/',
        )
        japan_visit = VisitLog.objects.create(
            ip_address='203.0.113.71',
            country='Japan',
            path='/keep-japan/',
        )

        response = self.client.post('/visitas/', {
            'action': 'delete_all_filtered',
            'country': 'Colombia',
        })

        self.assertEqual(response.status_code, 302)
        self.assertFalse(VisitLog.objects.filter(pk=colombia_visit.pk).exists())
        self.assertTrue(VisitLog.objects.filter(pk=japan_visit.pk).exists())

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


class VisitsBadgeTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = get_user_model().objects.create_superuser(
            username='admin-contador',
            email='admin-contador@example.com',
            password='test-password',
        )

    def setUp(self):
        cache.clear()

    def _colombian_visit(self, ip, visitor_id='visitor-ajeno'):
        return VisitLog.objects.create(
            ip_address=ip,
            visitor_id=visitor_id,
            country_code='CO',
            country='Colombia',
            path='/bookshelf/',
        )

    def test_login_records_the_owner_signature(self):
        session = self.client.session
        session['visit_visitor_id'] = 'visitor-propio'
        session.save()

        self.client.post(
            '/noticias/login/',
            {'username': 'admin-contador', 'password': 'test-password'},
            REMOTE_ADDR='190.0.0.1',
        )

        self.assertTrue(
            OwnerSignature.objects.filter(
                ip_address='190.0.0.1',
                visitor_id='visitor-propio',
            ).exists()
        )

    def test_counts_only_foreign_colombian_visits(self):
        OwnerSignature.objects.create(ip_address='190.0.0.1', visitor_id='visitor-propio')

        self._colombian_visit('181.50.0.9')
        self._colombian_visit('181.50.0.10')
        self._colombian_visit('190.0.0.1', visitor_id='otro-navegador')  # misma IP: mía
        self._colombian_visit('190.0.0.55', visitor_id='visitor-propio')  # otra IP: mía
        VisitLog.objects.create(
            ip_address='203.0.113.4',
            visitor_id='visitor-ajeno',
            country_code='NL',
            country='Netherlands',
            path='/',
        )

        self.assertEqual(badge_count(), 2)

    def test_counts_old_rows_without_country_code(self):
        VisitLog.objects.create(
            ip_address='181.50.0.9',
            country_code='',
            country='Colombia',
            path='/',
        )

        self.assertEqual(badge_count(), 1)

    def test_header_shows_the_badge_only_when_there_is_something_to_see(self):
        self.client.force_login(self.admin)

        response = self.client.get('/bookshelf/')
        self.assertNotContains(response, 'visits-badge')

        self._colombian_visit('181.50.0.9')
        cache.clear()

        response = self.client.get('/bookshelf/')
        self.assertContains(response, 'visits-badge')

    def test_opening_the_visits_page_turns_the_badge_off(self):
        self.client.force_login(self.admin)
        self._colombian_visit('181.50.0.9')
        self.assertEqual(badge_count(), 1)

        self.client.get('/visitas/')
        cache.clear()

        self.assertEqual(badge_count(), 0)
        # La visita sigue ahí: verla no es borrarla.
        self.assertEqual(VisitLog.objects.count(), 1)

    def test_a_visit_arriving_after_the_review_lights_the_badge_again(self):
        self.client.force_login(self.admin)
        self._colombian_visit('181.50.0.9')
        self.client.get('/visitas/')
        cache.clear()

        self._colombian_visit('181.50.0.20')
        cache.clear()

        self.assertEqual(badge_count(), 1)

    def test_a_filtered_review_leaves_the_rest_pending(self):
        self.client.force_login(self.admin)
        self._colombian_visit('181.50.0.9')
        self._colombian_visit('181.50.0.20')

        self.client.get('/visitas/?ip=181.50.0.9')
        cache.clear()

        self.assertEqual(badge_count(), 1)

    def test_badge_is_not_computed_for_anonymous_visitors(self):
        self._colombian_visit('181.50.0.9')

        response = self.client.get('/bookshelf/')

        self.assertNotIn('visits_badge_count', response.context)


class DownloadAsWebpTests(TestCase):
    """La descarga de imagenes que comparten las portadas y las caratulas.

    Estaba duplicada en home_page y en watching, y no la cubria ningun test,
    justo la parte que borra el temporal pase lo que pase.
    """

    def jpeg_bytes(self):
        buffer = io.BytesIO()
        Image.new('RGB', (600, 900), (10, 20, 30)).save(buffer, 'JPEG')
        return buffer.getvalue()

    def test_saves_a_webp_and_leaves_no_temporary_file(self):
        respuesta = SimpleNamespace(content=self.jpeg_bytes(), raise_for_status=lambda: None)

        with tempfile.TemporaryDirectory() as carpeta:
            destino = os.path.join(carpeta, 'portada.webp')
            with patch('home_page.utils.requests.get', return_value=respuesta):
                download_as_webp('https://example.com/x.jpg', destino, error_label='portada')

            with Image.open(destino) as imagen:
                self.assertEqual(imagen.format, 'WEBP')
                self.assertEqual(imagen.size, (300, 450))
            self.assertEqual(os.listdir(carpeta), ['portada.webp'])

    def test_a_failed_download_leaves_nothing_behind(self):
        with tempfile.TemporaryDirectory() as carpeta:
            destino = os.path.join(carpeta, 'portada.webp')
            with patch('home_page.utils.requests.get', side_effect=Exception('sin red')):
                with self.assertLogs('home_page.utils', level='ERROR'):
                    download_as_webp('https://example.com/x.jpg', destino, error_label='portada')

            self.assertEqual(os.listdir(carpeta), [])

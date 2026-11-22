from datetime import date, datetime, time, timedelta
import io
import os
import tempfile
from types import SimpleNamespace
from unittest.mock import patch

from PIL import Image

from django.contrib.auth import get_user_model
from django.templatetags.static import static
from django.test import TestCase, override_settings
from django.utils import timezone as dj_timezone

from django.core.cache import cache
from django.core.management import call_command
from django.urls import reverse

from . import views
from .models import Book, OwnerSignature, VisitLog
from .utils import build_shelf_url, download_as_webp, sync_currently_reading
from .visit_stats import badge_count

# Las visitas con IP pública preguntan el operador a ipwho.is en un hilo. En
# los tests, ni red ni hilos: cada test que lo necesite parchea _lookup_isp.
_isp_patches = [
    patch('home_page.middleware.VisitLogMiddleware.ISP_LOOKUP_IN_THREAD', False),
    patch('home_page.middleware.VisitLogMiddleware._lookup_isp', return_value=''),
]


def setUpModule():
    for p in _isp_patches:
        p.start()


def tearDownModule():
    for p in reversed(_isp_patches):
        p.stop()


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


READ_ENTRY = {
    'book_id': '888',
    'title': 'El nombre del viento',
    'author_name': 'Patrick Rothfuss',
    'average_rating': '4.5',
    'user_rating': '5',
    'user_read_at': 'Mon, 12 Jan 2026 10:00:00 -0800',
    'user_date_added': 'Sat, 03 Jan 2026 09:30:00 -0800',
    'book_description': '<p>Una <b>historia</b> <script>x</script></p>',
    'num_pages': '662',
    'book_published': '2007',
}


class RssBookWritesTests(TestCase):
    """Un libro que no cambió en Goodreads no debe volver a escribirse."""

    def _refresh(self, entries):
        from .utils import refresh_books_data

        with patch('home_page.utils.sync_currently_reading', return_value=None), \
                patch('home_page.utils.fetch_goodreads_rss_entries', return_value=entries):
            refresh_books_data()

    def test_unchanged_read_book_is_not_saved(self):
        self._refresh([READ_ENTRY])
        book = Book.objects.get(goodreads_id='888')
        self.assertEqual(book.date_read, date(2026, 1, 12))
        self.assertEqual(book.my_rating, 5)

        # Sin cambios: ni una escritura, aunque haya HTML que sanear y fechas
        # en otra zona horaria que comparar.
        with patch.object(Book, 'save', autospec=True) as save:
            self._refresh([READ_ENTRY])
        save.assert_not_called()

    def test_changed_field_saves_only_that_field(self):
        self._refresh([READ_ENTRY])

        with patch.object(Book, 'save', autospec=True) as save:
            self._refresh([{**READ_ENTRY, 'average_rating': '4.6'}])
        save.assert_called_once()
        self.assertEqual(save.call_args.kwargs, {'update_fields': ['public_rating']})

    @patch('home_page.utils.fetch_feed_with_timeout')
    def test_unchanged_reading_book_is_not_saved(self, mock_fetch):
        mock_fetch.return_value = SimpleNamespace(entries=[READING_ENTRY])
        sync_currently_reading('https://example.com/rss?shelf=read', '/tmp')

        with patch.object(Book, 'save', autospec=True) as save:
            sync_currently_reading('https://example.com/rss?shelf=read', '/tmp')
        save.assert_not_called()


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


class VisitClientHintsTests(TestCase):
    """Chromium congela su UA; el modelo llega por Client Hints."""

    UA = ('Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 '
          '(KHTML, like Gecko) Chrome/154.0.0.0 Mobile Safari/537.36')
    HINTS = {
        'HTTP_SEC_CH_UA_MODEL': '"SM-A256E"',
        'HTTP_SEC_CH_UA_PLATFORM': '"Android"',
        'HTTP_SEC_CH_UA_PLATFORM_VERSION': '"16.0.0"',
    }

    def _get(self, **headers):
        headers = {'HTTP_ACCEPT': 'text/html', 'HTTP_USER_AGENT': self.UA, **headers}
        return self.client.get('/about/', **headers)

    def test_html_responses_ask_for_the_hints(self):
        response = self._get()

        self.assertIn('Sec-CH-UA-Model', response['Accept-CH'])
        self.assertEqual(response['Critical-CH'], response['Accept-CH'])

    def test_hints_are_stored_without_their_quotes(self):
        self._get(**self.HINTS)

        visit = VisitLog.objects.get(path='/about/')
        self.assertEqual((visit.device_model, visit.os_version), ('SM-A256E', 'Android 16.0.0'))

    def test_critical_ch_retry_completes_the_first_visit(self):
        self._get()
        self._get(**self.HINTS)

        visit = VisitLog.objects.get(path='/about/')
        self.assertEqual(visit.device_model, 'SM-A256E')

    def test_browser_without_hints_is_logged_as_before(self):
        self._get(HTTP_USER_AGENT='Mozilla/5.0 (X11; Linux x86_64; rv:153.0) Firefox/153.0')

        visit = VisitLog.objects.get(path='/about/')
        self.assertEqual((visit.device_model, visit.os_version), ('', ''))

    def test_desktop_sends_an_empty_model(self):
        self._get(
            HTTP_SEC_CH_UA_MODEL='""',
            HTTP_SEC_CH_UA_PLATFORM='"Windows"',
            HTTP_SEC_CH_UA_PLATFORM_VERSION='"19.0.0"',
        )

        visit = VisitLog.objects.get(path='/about/')
        self.assertEqual((visit.device_model, visit.os_version), ('', 'Windows 11'))

    def test_windows_platform_version_is_translated(self):
        from .middleware import os_label

        self.assertEqual(os_label('Windows', '19.0.0'), 'Windows 11')
        self.assertEqual(os_label('Windows', '13.0.0'), 'Windows 11')
        self.assertEqual(os_label('Windows', '10.0.0'), 'Windows 10')
        self.assertEqual(os_label('Windows', '0.3.0'), 'Windows 7/8')
        self.assertEqual(os_label('Android', '16.0.0'), 'Android 16.0.0')
        self.assertEqual(os_label('Linux', ''), 'Linux')

    def test_first_language_is_stored(self):
        self._get(HTTP_ACCEPT_LANGUAGE='es-CO,es;q=0.9,en;q=0.8')

        self.assertEqual(VisitLog.objects.get(path='/about/').language, 'es-CO')

    def test_city_comes_from_cloudflare_for_the_logged_ip(self):
        cache.clear()
        # «Bogotá» en UTF-8, leído como latin-1, que es como llega por WSGI.
        bogota = 'Bogotá'.encode('utf-8').decode('latin-1')
        self._get(
            HTTP_X_REAL_IP='8.8.8.8', HTTP_CF_CONNECTING_IP='8.8.8.8',
            HTTP_CF_IPCOUNTRY='CO', HTTP_CF_IPCITY=bogota,
            HTTP_CF_REGION='Bogota D.C.',
        )

        self.assertEqual(VisitLog.objects.get(path='/about/').city, 'Bogotá, Bogota D.C.')

    def test_city_of_another_ip_is_ignored(self):
        cache.clear()
        with patch('home_page.middleware.VisitLogMiddleware._lookup_ipwho', return_value=('', '')):
            self._get(
                HTTP_X_REAL_IP='8.8.8.8', HTTP_CF_CONNECTING_IP='9.9.9.9',
                HTTP_CF_IPCITY='Medellin',
            )

        self.assertEqual(VisitLog.objects.get(path='/about/').city, '')

    def test_next_page_fills_the_page_the_service_worker_left_without_hints(self):
        # La portada la pidió el service worker: sin hints y sin repetición.
        self.client.get('/', HTTP_ACCEPT='text/html', HTTP_USER_AGENT=self.UA)
        self._get(**self.HINTS)

        home = VisitLog.objects.get(path='/')
        self.assertEqual((home.device_model, home.os_version), ('SM-A256E', 'Android 16.0.0'))
        self.assertEqual(VisitLog.objects.count(), 2)

    def test_backfill_does_not_touch_another_visitor(self):
        VisitLog.objects.create(
            ip_address='127.0.0.1', visitor_id='otro', path='/', user_agent=self.UA,
        )
        self._get(**self.HINTS)

        self.assertEqual(VisitLog.objects.get(visitor_id='otro').device_model, '')

    def test_isp_is_looked_up_and_reused_for_the_same_ip(self):
        cache.clear()
        headers = {'HTTP_X_REAL_IP': '8.8.8.8', 'HTTP_CF_CONNECTING_IP': '8.8.8.8',
                   'HTTP_CF_IPCOUNTRY': 'CO'}
        with patch('home_page.middleware.VisitLogMiddleware._lookup_isp',
                   return_value='Telmex Colombia S.A.') as lookup:
            self._get(**headers)
            cache.clear()  # La segunda tiene que salir de la visita anterior.
            self.client.get('/', HTTP_ACCEPT='text/html', **headers)

        lookup.assert_called_once_with('8.8.8.8')
        self.assertEqual(
            set(VisitLog.objects.values_list('isp', flat=True)),
            {'Telmex Colombia S.A.'},
        )

    def test_private_ip_does_not_ask_for_the_isp(self):
        with patch('home_page.middleware.VisitLogMiddleware._lookup_isp') as lookup:
            self._get()

        lookup.assert_not_called()

    def test_backfill_fills_only_empty_fields_of_the_country(self):
        old = VisitLog.objects.create(ip_address='8.8.8.8', country_code='CO', path='/')
        kept = VisitLog.objects.create(
            ip_address='8.8.8.8', country_code='CO', path='/b/', city='Chía, Cundinamarca',
        )
        foreign = VisitLog.objects.create(ip_address='9.9.9.9', country_code='US', path='/')
        details = {'isp': 'Telmex Colombia S.A.', 'city': 'Bogota, Bogota D.C.'}

        with patch('home_page.middleware.VisitLogMiddleware.lookup_ip_details',
                   return_value=details) as lookup:
            call_command('backfill_visit_ip_data', '--apply', '--pausa', '0', stdout=io.StringIO())

        lookup.assert_called_once_with('8.8.8.8')  # Una por IP, solo Colombia.
        old.refresh_from_db(), kept.refresh_from_db(), foreign.refresh_from_db()
        self.assertEqual((old.isp, old.city), ('Telmex Colombia S.A.', 'Bogota, Bogota D.C.'))
        self.assertEqual(kept.city, 'Chía, Cundinamarca')  # No pisa la de Cloudflare.
        self.assertEqual(foreign.isp, '')

    def test_backfill_without_apply_only_counts(self):
        VisitLog.objects.create(ip_address='8.8.8.8', country_code='CO', path='/')

        with patch('home_page.middleware.VisitLogMiddleware.lookup_ip_details') as lookup:
            call_command('backfill_visit_ip_data', stdout=io.StringIO())

        lookup.assert_not_called()

    def test_redirect_is_not_logged_as_a_visit(self):
        response = self.client.get('/bookshelf', HTTP_ACCEPT='text/html', HTTP_USER_AGENT=self.UA)

        self.assertEqual(response.status_code, 301)
        self.assertFalse(VisitLog.objects.exists())

    BOT_UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
              '(KHTML, like Gecko) Chrome/124.0.6367.207 Safari/537.36')
    REAL_CHROME = {
        'HTTP_X_REAL_IP': '8.8.8.8', 'HTTP_CF_CONNECTING_IP': '8.8.8.8',
        'HTTP_CF_IPCOUNTRY': 'CO', 'HTTP_SEC_CH_UA': '"Chromium";v="157"',
        'HTTP_ACCEPT_LANGUAGE': 'es-CO',
    }

    def test_full_chrome_version_is_flagged_as_bot(self):
        cache.clear()
        self._get(**{**self.REAL_CHROME, 'HTTP_USER_AGENT': self.BOT_UA})

        reasons = VisitLog.objects.get(path='/about/').bot_reason.split(',')
        self.assertIn('version-completa', reasons)
        self.assertIn('navegador-viejo', reasons)

    def test_real_chrome_through_cloudflare_is_not_flagged(self):
        cache.clear()
        self._get(**self.REAL_CHROME)
        # Hasta que la página avisa, la visita está en duda.
        self.assertEqual(VisitLog.objects.get(path='/about/').bot_reason, 'sin-javascript')

        self.client.post('/visitas/js/', **self.REAL_CHROME)

        self.assertEqual(VisitLog.objects.get(path='/about/').bot_reason, '')

    def test_beacon_before_the_visit_still_counts(self):
        # La portada de la PWA se pinta de la caché: el aviso puede llegar
        # antes que la petición a la red que apunta la visita.
        cache.clear()
        self._get(**self.REAL_CHROME)
        self.client.post('/visitas/js/', **self.REAL_CHROME)
        self.client.get('/', HTTP_ACCEPT='text/html', HTTP_USER_AGENT=self.UA, **self.REAL_CHROME)

        self.assertEqual(VisitLog.objects.get(path='/').bot_reason, '')

    def test_manifest_or_ajax_also_prove_javascript(self):
        # Edge en Android no manda el aviso, pero pide el manifiesto y hace
        # las llamadas AJAX del feed: eso también es ejecutar la página.
        for proof in (
            lambda: self.client.get('/manifest.webmanifest', HTTP_USER_AGENT=self.UA, **self.REAL_CHROME),
            lambda: self.client.get('/visitas/insignia/', HTTP_X_REQUESTED_WITH='XMLHttpRequest',
                                    HTTP_USER_AGENT=self.UA, **self.REAL_CHROME),
        ):
            with self.subTest():
                cache.clear()
                VisitLog.objects.all().delete()
                self._get(**self.REAL_CHROME)
                proof()
                self.assertEqual(VisitLog.objects.get(path='/about/').bot_reason, '')

    def test_proof_before_the_visit_still_counts(self):
        cache.clear()
        self.client.get('/manifest.webmanifest', HTTP_USER_AGENT=self.UA, **self.REAL_CHROME)
        self._get(**self.REAL_CHROME)

        self.assertEqual(VisitLog.objects.get(path='/about/').bot_reason, '')

    def test_beacon_only_clears_its_own_browser(self):
        cache.clear()
        other = VisitLog.objects.create(ip_address='8.8.4.4', visitor_id='otro', path='/',
                                        bot_reason='sin-javascript')
        self._get(**self.REAL_CHROME)
        self.client.post('/visitas/js/', **self.REAL_CHROME)

        other.refresh_from_db()
        self.assertEqual(other.bot_reason, 'sin-javascript')

    def test_beacon_keeps_the_other_reasons(self):
        cache.clear()
        self._get(**{**self.REAL_CHROME, 'HTTP_USER_AGENT': self.BOT_UA})
        self.client.post('/visitas/js/', **{**self.REAL_CHROME, 'HTTP_USER_AGENT': self.BOT_UA})

        self.assertEqual(VisitLog.objects.get(path='/about/').bot_reason,
                         'version-completa,navegador-viejo')

    def test_datacenter_isp_adds_a_reason(self):
        cache.clear()
        with patch('home_page.middleware.VisitLogMiddleware._lookup_isp',
                   return_value='DigitalOcean, LLC'):
            self._get(**self.REAL_CHROME)

        reasons = VisitLog.objects.get(path='/about/').bot_reason.split(',')
        self.assertIn('centro-de-datos', reasons)

    def test_new_declared_scanners(self):
        from datetime import date
        from .bot_detection import user_agent_reasons

        for ua in (
            'nameserver-checker-http-validator/1.0',
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko; '
            'compatible; CriminalIP; +https://www.criminalip.io) Chrome/153.0.0.0 Safari/537.36',
        ):
            with self.subTest(ua=ua[:40]):
                self.assertEqual(user_agent_reasons(ua, date(2026, 11, 17)), ['declarado'])

    def test_chrome_without_client_hints_or_language_is_flagged(self):
        cache.clear()
        headers = {k: v for k, v in self.REAL_CHROME.items()
                   if k not in ('HTTP_SEC_CH_UA', 'HTTP_ACCEPT_LANGUAGE')}
        self._get(**headers)

        self.assertEqual(VisitLog.objects.get(path='/about/').bot_reason,
                         'sin-client-hints,sin-idioma,sin-javascript')

    def test_header_signals_are_not_used_outside_cloudflare(self):
        # Por la LAN el sitio va en http y Chrome no manda Client Hints.
        self._get()

        self.assertEqual(VisitLog.objects.get(path='/about/').bot_reason, 'sin-javascript')

    def test_bots_do_not_count_in_the_header_badge(self):
        cache.clear()
        VisitLog.objects.create(ip_address='8.8.8.8', country_code='CO', path='/')
        VisitLog.objects.create(ip_address='8.8.4.4', country_code='CO', path='/',
                                bot_reason='version-completa')

        self.assertEqual(badge_count(), 1)

    def test_flag_command_marks_old_visits_by_user_agent(self):
        bot = VisitLog.objects.create(ip_address='8.8.8.8', path='/', user_agent=self.BOT_UA)
        person = VisitLog.objects.create(ip_address='8.8.4.4', path='/', user_agent=self.UA)

        call_command('flag_bot_visits', '--apply', stdout=io.StringIO())

        bot.refresh_from_db(), person.refresh_from_db()
        self.assertIn('version-completa', bot.bot_reason)
        self.assertEqual(person.bot_reason, '')

    def test_scanner_probing_a_path_that_does_not_exist_is_flagged(self):
        self.client.get(
            '/api/session/properties', HTTP_ACCEPT='text/html',
            HTTP_USER_AGENT='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        )

        reasons = VisitLog.objects.get(path='/api/session/properties').bot_reason.split(',')
        self.assertEqual(reasons, ['ua-incompleto', 'ruta-inexistente', 'sin-javascript'])

    def test_flag_command_also_uses_the_path(self):
        probe = VisitLog.objects.create(ip_address='8.8.8.8', path='/wp-login.php', user_agent=self.UA)
        page = VisitLog.objects.create(ip_address='8.8.8.8', path='/viendo/', user_agent=self.UA)
        # Sin barra existe (Django redirige): no es una ruta inventada.
        no_slash = VisitLog.objects.create(ip_address='8.8.8.8', path='/viendo', user_agent=self.UA)

        call_command('flag_bot_visits', '--apply', stdout=io.StringIO())

        for visit in (probe, page, no_slash):
            visit.refresh_from_db()
        self.assertEqual(
            (probe.bot_reason, page.bot_reason, no_slash.bot_reason),
            ('ruta-inexistente', '', ''),
        )

    def test_in_app_browsers_and_phone_models_are_not_bots(self):
        from datetime import date
        from .bot_detection import user_agent_reasons

        today = date(2026, 11, 17)
        for ua in (
            'Mozilla/5.0 (Linux; Android 16; SM-A256E Build/BP4A; wv) AppleWebKit/537.36 '
            '(KHTML, like Gecko) Version/4.0 Chrome/151.0.7922.104 Mobile Safari/537.36 Instagram 442',
            'Mozilla/5.0 (Linux; Android 12; CUBOT X30 Build/SP1A; wv) AppleWebKit/537.36 '
            '(KHTML, like Gecko) Version/4.0 Chrome/150.0.0.0 Mobile Safari/537.36',
            'Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) '
            'SamsungBrowser/30.0 Chrome/143.0.0.0 Mobile Safari/537.36',
            'Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) '
            'Chrome/157.0.0.0 Mobile Safari/537.36 Telegram-Android/11.2',
            # Facebook en iOS: sin «Safari/», pero con «like Gecko».
            'Mozilla/5.0 (iPhone; CPU iPhone OS 17_1 like Mac OS X) AppleWebKit/605.1.15 '
            '(KHTML, like Gecko) Mobile/15E148 [FBAN/FBIOS;FBAV/450.0]',
        ):
            with self.subTest(ua=ua[-40:]):
                self.assertEqual(user_agent_reasons(ua, today), [])

    def test_known_operators_show_their_brand(self):
        from .middleware import isp_label

        self.assertEqual(isp_label('Telmex Colombia S.A.'), 'Claro (Telmex Colombia S.A.)')
        self.assertEqual(isp_label('UNE EPM Telecomunicaciones S.A.'),
                         'Tigo (UNE EPM Telecomunicaciones S.A.)')
        self.assertEqual(isp_label('Google LLC'), 'Google LLC')
        self.assertEqual(isp_label('ETB - Colombia'), 'ETB - Colombia')

    def test_official_region_names_are_shortened(self):
        from .middleware import short_region

        self.assertEqual(short_region('Departamento del Valle del Cauca'), 'Valle del Cauca')
        self.assertEqual(short_region('Departamento de Antioquia'), 'Antioquia')
        self.assertEqual(short_region('Cundinamarca'), 'Cundinamarca')

    def test_a_later_visit_with_hints_is_not_merged_into_an_old_one(self):
        self._get()
        VisitLog.objects.update(visited_at=dj_timezone.now() - timedelta(minutes=5))
        self._get(**self.HINTS)

        self.assertEqual(VisitLog.objects.filter(path='/about/').count(), 2)


class VisitCountryFromCloudflareTests(TestCase):
    """El país de Cloudflare solo vale si es el de la IP que se guarda."""

    # IPs públicas de verdad: las de documentación (203.0.113.x) cuentan como
    # privadas y la visita se guardaría como 'Local' sin mirar el país.
    IP = '8.8.8.8'
    IPWHO = 'home_page.middleware.VisitLogMiddleware._lookup_ipwho'

    def setUp(self):
        cache.clear()
        self.addCleanup(cache.clear)
        # Una visita anterior: de ella sale el nombre del país.
        VisitLog.objects.create(
            ip_address='1.1.1.1', visitor_id='x', country='Colombia',
            country_code='CO', path='/',
        )

    def _visit(self, **headers):
        self.client.get('/about/', HTTP_ACCEPT='text/html', **headers)
        return VisitLog.objects.filter(path='/about/').latest('id')

    def test_uses_cloudflare_country_when_it_is_for_the_logged_ip(self):
        with patch(self.IPWHO) as ipwho:
            visit = self._visit(
                HTTP_X_REAL_IP=self.IP,
                HTTP_CF_CONNECTING_IP=self.IP,
                HTTP_CF_IPCOUNTRY='co',
            )

        ipwho.assert_not_called()
        self.assertEqual(visit.ip_address, self.IP)
        self.assertEqual((visit.country, visit.country_code), ('Colombia', 'CO'))

    def test_ignores_cloudflare_country_of_another_ip(self):
        with patch(self.IPWHO, return_value=('Germany', 'DE')) as ipwho:
            visit = self._visit(
                HTTP_X_REAL_IP=self.IP,
                HTTP_CF_CONNECTING_IP='9.9.9.9',
                HTTP_CF_IPCOUNTRY='CO',
            )

        ipwho.assert_called_once_with(self.IP)
        self.assertEqual((visit.country, visit.country_code), ('Germany', 'DE'))

    def test_ignores_country_header_without_connecting_ip(self):
        with patch(self.IPWHO, return_value=('Germany', 'DE')) as ipwho:
            visit = self._visit(HTTP_X_REAL_IP=self.IP, HTTP_CF_IPCOUNTRY='CO')

        ipwho.assert_called_once_with(self.IP)
        self.assertEqual(visit.country_code, 'DE')

    def test_unknown_and_tor_codes_are_not_countries(self):
        for code in ('XX', 'T1', '', 'COL'):
            with self.subTest(code=code), patch(
                self.IPWHO, return_value=('Germany', 'DE'),
            ) as ipwho:
                cache.clear()
                visit = self._visit(
                    HTTP_X_REAL_IP=self.IP,
                    HTTP_CF_CONNECTING_IP=self.IP,
                    HTTP_CF_IPCOUNTRY=code,
                )
                ipwho.assert_called_once_with(self.IP)
                self.assertEqual(visit.country_code, 'DE')

    def test_ipv6_is_compared_as_an_address_not_as_text(self):
        with patch(self.IPWHO) as ipwho:
            visit = self._visit(
                HTTP_X_REAL_IP='2606:4700:4700::1111',
                HTTP_CF_CONNECTING_IP='2606:4700:4700:0000:0000:0000:0000:1111',
                HTTP_CF_IPCOUNTRY='CO',
            )

        ipwho.assert_not_called()
        self.assertEqual(visit.country_code, 'CO')

    def test_new_country_takes_its_name_from_ipwho(self):
        with patch(self.IPWHO, return_value=('Japan', 'JP')) as ipwho:
            visit = self._visit(
                HTTP_X_REAL_IP=self.IP,
                HTTP_CF_CONNECTING_IP=self.IP,
                HTTP_CF_IPCOUNTRY='JP',
            )

        ipwho.assert_called_once_with(self.IP)
        self.assertEqual((visit.country, visit.country_code), ('Japan', 'JP'))

    def test_new_country_keeps_cloudflare_code_if_ipwho_fails(self):
        with patch(self.IPWHO, return_value=('', '')):
            visit = self._visit(
                HTTP_X_REAL_IP=self.IP,
                HTTP_CF_CONNECTING_IP=self.IP,
                HTTP_CF_IPCOUNTRY='JP',
            )

        self.assertEqual((visit.country, visit.country_code), ('', 'JP'))


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

    def test_delete_bots_removes_only_bots_inside_the_filter(self):
        person = VisitLog.objects.create(ip_address='203.0.113.30', country='Colombia', path='/')
        bot_co = VisitLog.objects.create(ip_address='203.0.113.31', country='Colombia', path='/',
                                         bot_reason='version-completa')
        bot_us = VisitLog.objects.create(ip_address='203.0.113.32', country='United States',
                                         path='/', bot_reason='declarado')

        page = self.client.get('/visitas/')
        self.assertContains(page, 'Eliminar robots (2)')

        response = self.client.post(
            '/visitas/', {'action': 'delete_bots', 'country': 'Colombia'},
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )

        self.assertEqual(response.json()['deleted'], 1)
        remaining = set(VisitLog.objects.values_list('pk', flat=True))
        self.assertEqual(remaining, {person.pk, bot_us.pk})
        self.assertNotIn(bot_co.pk, remaining)

    def test_delete_bots_button_hides_without_bots(self):
        VisitLog.objects.create(ip_address='203.0.113.30', country='Colombia', path='/')

        self.assertNotContains(self.client.get('/visitas/'), 'Eliminar robots')

    def test_countries_are_ordered_by_latest_visit_with_colombia_first(self):
        now = dj_timezone.now()
        for code, name, minutes_ago, copies in (
            ('US', 'United States', 60, 5),  # Más visitas, pero viejas.
            ('MX', 'Mexico', 1, 1),          # La más reciente.
            ('CO', 'Colombia', 600, 1),      # La más vieja, y aun así primero.
        ):
            for _ in range(copies):
                visit = VisitLog.objects.create(
                    ip_address='203.0.113.20', country_code=code, country=name, path='/',
                )
                VisitLog.objects.filter(pk=visit.pk).update(
                    visited_at=now - timedelta(minutes=minutes_ago),
                )

        response = self.client.get('/visitas/')

        order = [group['country'] for group in response.context['visit_groups']]
        self.assertEqual(order[:3], ['Colombia', 'Mexico', 'United States'])

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
        self.assertContains(response, 'data-confirm-delete="self"')
        self.assertNotContains(response, 'id="select-all-visits"')
        self.assertNotContains(response, 'onclick="return confirm(')

    def test_the_page_only_carries_country_cards_not_their_rows(self):
        # Con miles de visitas, pintar todas las tablas costaba segundos de
        # plantilla: la tarjeta lleva el total y las filas se piden aparte.
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
        self.assertContains(response, 'data-group-key="cc:NL"')
        self.assertNotContains(response, '/page/0/')

    def test_country_rows_endpoint_serves_the_visits_of_one_country(self):
        VisitLog.objects.create(
            ip_address='203.0.113.80',
            country_code='NL',
            country='Netherlands',
            path='/holanda/',
        )
        VisitLog.objects.create(
            ip_address='203.0.113.81',
            country_code='TR',
            country='Turkey',
            path='/turquia/',
        )

        response = self.client.get('/visitas/filas/', {'group': 'cc:NL'})

        payload = response.json()
        self.assertEqual([row['path'] for row in payload['rows']], ['/holanda/'])
        self.assertFalse(payload['has_more'])

    def test_country_rows_endpoint_rejects_an_unknown_group(self):
        response = self.client.get('/visitas/filas/', {'group': 'cc:NOPE'})

        self.assertEqual(response.status_code, 400)

    def test_country_rows_endpoint_pages_the_visits(self):
        VisitLog.objects.bulk_create([
            VisitLog(
                ip_address='203.0.113.90',
                country_code='NL',
                country='Netherlands',
                path=f'/pagina/{index}/',
            )
            for index in range(views.VISITS_ROWS_PAGE_SIZE + 5)
        ])

        first = self.client.get('/visitas/filas/', {'group': 'cc:NL'}).json()
        second = self.client.get(
            '/visitas/filas/',
            {'group': 'cc:NL', 'offset': first['offset']},
        ).json()

        self.assertEqual(len(first['rows']), views.VISITS_ROWS_PAGE_SIZE)
        self.assertTrue(first['has_more'])
        self.assertEqual(len(second['rows']), 5)
        self.assertFalse(second['has_more'])

    def test_deleting_a_country_needs_no_id_list(self):
        colombia = VisitLog.objects.create(
            ip_address='181.50.0.9',
            country_code='CO',
            country='Colombia',
            path='/',
        )
        turkey = VisitLog.objects.create(
            ip_address='203.0.113.91',
            country_code='TR',
            country='Turkey',
            path='/',
        )

        response = self.client.post(
            '/visitas/',
            {'action': 'delete_group', 'group': 'cc:CO'},
            headers={'x-requested-with': 'XMLHttpRequest'},
        )

        self.assertEqual(response.json()['deleted'], 1)
        self.assertFalse(VisitLog.objects.filter(pk=colombia.pk).exists())
        self.assertTrue(VisitLog.objects.filter(pk=turkey.pk).exists())

    def test_deleting_only_mine_keeps_the_rest_of_the_country(self):
        mine = VisitLog.objects.create(
            ip_address='190.0.0.1',
            visitor_id='visitor-owner',
            country_code='CO',
            country='Colombia',
            path='/bookshelf/',
        )
        other = VisitLog.objects.create(
            ip_address='181.50.0.9',
            visitor_id='visitor-other',
            country_code='CO',
            country='Colombia',
            path='/',
        )

        response = self.client.post(
            '/visitas/',
            {'action': 'delete_group', 'group': 'cc:CO', 'self_only': '1'},
            headers={'x-requested-with': 'XMLHttpRequest'},
        )

        payload = response.json()
        self.assertEqual(payload['deleted'], 1)
        # El modal se queda abierto, así que la respuesta trae los contadores
        # con los que repintarlo.
        self.assertEqual(payload['group_count'], 1)
        self.assertEqual(payload['group_self_count'], 0)
        self.assertFalse(VisitLog.objects.filter(pk=mine.pk).exists())
        self.assertTrue(VisitLog.objects.filter(pk=other.pk).exists())

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
        rows = self.client.get('/visitas/filas/', {
            'group': 'name:colombia',
            'from': selected_day.isoformat(),
            'to': selected_day.isoformat(),
        }).json()['rows']
        self.assertEqual([row['path'] for row in rows], ['/selected-day/'])

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

        self.assertContains(response, 'data-self-count="1"')
        self.assertContains(response, 'Eliminar mías')
        rows = self.client.get('/visitas/filas/', {'group': 'cc:CO'}).json()['rows']
        self.assertEqual(
            {row['ip_address']: row['is_self'] for row in rows},
            {'190.0.0.1': True, '181.50.0.9': False},
        )

    def test_hides_the_delete_mine_button_when_no_visit_is_mine(self):
        VisitLog.objects.create(
            ip_address='181.50.0.9',
            visitor_id='visitor-other',
            country_code='CO',
            country='Colombia',
            path='/',
        )

        response = self.client.get('/visitas/')

        # El botón viaja oculto: al borrar sin recargar, el JavaScript lo
        # enseña o lo esconde según el contador que devuelve el servidor.
        self.assertContains(response, 'data-self-count="0"')
        self.assertContains(response, 'data-confirm-delete="self" hidden')

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
            # El webp y el índice de colores (home_page/cover_colors.py); ningún temporal.
            self.assertEqual(sorted(os.listdir(carpeta)), ['.colors.json', 'portada.webp'])

    def test_a_failed_download_leaves_nothing_behind(self):
        with tempfile.TemporaryDirectory() as carpeta:
            destino = os.path.join(carpeta, 'portada.webp')
            with patch('home_page.utils.requests.get', side_effect=Exception('sin red')):
                with self.assertLogs('home_page.utils', level='ERROR'):
                    download_as_webp('https://example.com/x.jpg', destino, error_label='portada')

            self.assertEqual(os.listdir(carpeta), [])


class SitemapTests(TestCase):
    """El sitemap tiene que listar todas las secciones publicas.

    Se olvidaba la seccion TV: estaba en el menu y en robots.txt como rastreable, pero
    no en el sitemap, asi que era la unica seccion que los buscadores tenian que
    encontrar por su cuenta.
    """

    def test_lists_every_public_section(self):
        respuesta = self.client.get('/sitemap.xml')
        cuerpo = respuesta.content.decode()

        self.assertEqual(respuesta.status_code, 200)
        for ruta in ('/', '/bookshelf/', '/bookshelf/stats/', '/about/',
                     '/spotify/', '/spotify/stats/', '/spotify/deleted/',
                     '/viendo/', '/viendo/stats/'):
            with self.subTest(ruta=ruta):
                self.assertIn(f'<loc>http://testserver{ruta}</loc>', cuerpo)

    def test_does_not_advertise_what_robots_blocks(self):
        cuerpo = self.client.get('/sitemap.xml').content.decode()

        self.assertNotIn('/noticias/', cuerpo)
        self.assertNotIn('/j_admin/', cuerpo)


class VisitsBadgeLiveUpdateTests(TestCase):
    """Sondeo que mantiene la insignia al día sin recargar la página."""

    @classmethod
    def setUpTestData(cls):
        cls.admin = get_user_model().objects.create_superuser(
            username='admin-sondeo',
            email='admin-sondeo@example.com',
            password='test-password',
        )

    def setUp(self):
        cache.clear()

    def _colombian_visit(self, ip):
        return VisitLog.objects.create(
            ip_address=ip, visitor_id=f'visitante-{ip}',
            country_code='CO', country='Colombia', path='/bookshelf/',
        )

    def badge(self):
        return self.client.get(reverse('home_page:visits_badge_state'))

    def test_endpoint_reports_the_same_number_the_header_paints(self):
        self.client.force_login(self.admin)
        self._colombian_visit('181.50.0.9')
        cache.clear()

        self.assertEqual(self.badge().json()['badge'], badge_count())

    def test_endpoint_follows_the_count_up_and_down(self):
        self.client.force_login(self.admin)
        self.assertEqual(self.badge().json()['badge'], 0)

        self._colombian_visit('181.50.0.9')
        cache.clear()
        self.assertEqual(self.badge().json()['badge'], 1)

        # Mirar las visitas las apaga, y el sondeo lo refleja sin recargar.
        self.client.get('/visitas/')
        cache.clear()
        self.assertEqual(self.badge().json()['badge'], 0)

    def test_endpoint_is_superuser_only(self):
        response = self.badge()
        self.assertEqual(response.status_code, 302)
        self.assertIn('/noticias/login/', response.url)

        self.client.force_login(get_user_model().objects.create_user('lector', password='x'))
        self.assertEqual(self.badge().status_code, 302)

    def test_polling_does_not_register_itself_as_a_visit(self):
        # El sondeo manda la cabecera de AJAX; sin ella cada consulta de la
        # insignia se anotaría como una visita más.
        self.client.force_login(self.admin)
        before = VisitLog.objects.count()

        self.client.get(
            reverse('home_page:visits_badge_state'),
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
            REMOTE_ADDR='181.50.0.44',
        )

        self.assertEqual(VisitLog.objects.count(), before)

    def test_header_carries_what_the_script_needs(self):
        self.client.force_login(self.admin)

        response = self.client.get('/bookshelf/')

        self.assertContains(response, 'data-badge-url="/visitas/insignia/"')
        # static() y no el nombre a pelo: en producción lleva el hash del manifest.
        self.assertContains(response, static('js/visits_badge.js'))

    def test_the_visits_page_itself_does_not_poll(self):
        # Allí no hay insignia que refrescar: el botón ni siquiera se pinta.
        self.client.force_login(self.admin)

        response = self.client.get('/visitas/')

        self.assertNotContains(response, static('js/visits_badge.js'))


class SiteNavTests(TestCase):
    """La cabecera: título, sección marcada y adónde vuelve cada página."""

    def test_stats_page_goes_back_to_its_section_with_an_arrow_not_the_house(self):
        response = self.client.get('/bookshelf/stats/')

        nav = response.context['site_nav']
        self.assertEqual(nav['title'], 'Libros')
        self.assertEqual(nav['subtitle'], 'Estadísticas')
        self.assertEqual(nav['back'], {'url': '/bookshelf/', 'label': 'Volver a Libros'})
        # La casa sigue, pero lleva a la portada.
        self.assertContains(response, 'href="/" aria-label="Inicio"')

    def test_the_current_section_is_marked(self):
        response = self.client.get('/viendo/stats/')

        current = [s['label'] for s in response.context['site_nav']['sections'] if s['current']]
        self.assertEqual(current, ['TV'])
        self.assertContains(response, 'aria-label="TV" data-tip="TV" aria-current="true"')

    def test_movies_are_their_own_section_but_not_on_the_home_page(self):
        response = self.client.get('/viendo/', {'tipo': 'peliculas'})

        nav = response.context['site_nav']
        self.assertEqual(nav['title'], 'Películas')
        current = [s['key'] for s in nav['sections'] if s['current']]
        self.assertEqual(current, ['peliculas'])
        self.assertContains(response, 'aria-label="Películas" data-tip="Películas" aria-current="page"')

        # En la portada TV cubre series y películas: siguen siendo cuatro.
        self.assertNotContains(self.client.get('/'), 'Películas')

    def test_about_remembers_movies_as_the_origin(self):
        response = self.client.get('/about/', HTTP_REFERER='http://testserver/viendo/?tipo=peliculas')
        self.assertEqual(response.context['site_nav']['back']['label'], 'Volver a Películas')

    def test_every_section_front_page_has_the_info_button(self):
        for path in ('/bookshelf/', '/viendo/', '/spotify/'):
            with self.subTest(path=path):
                self.assertContains(self.client.get(path), 'href="/about/" aria-label="Información"')

    def test_about_goes_back_to_where_it_was_opened_from(self):
        response = self.client.get('/about/', HTTP_REFERER='http://testserver/viendo/')
        self.assertEqual(response.context['site_nav']['back']['url'], '/viendo/')

        # Al recargar ya no hay Referer útil: se recuerda el origen.
        response = self.client.get('/about/', HTTP_REFERER='http://testserver/about/')
        self.assertEqual(response.context['site_nav']['back']['url'], '/viendo/')

        # Desde la portada no hay sección a la que volver: basta la casa.
        response = self.client.get('/about/', HTTP_REFERER='http://testserver/')
        self.assertIsNone(response.context['site_nav']['back'])

    def test_404_does_not_claim_to_be_a_section(self):
        response = views.custom_404_view(self.client.get('/').wsgi_request, None)

        self.assertEqual(response.status_code, 404)
        self.assertNotIn(b'<h1>Libros</h1>', response.content)
        self.assertIn('Rincón de Johan'.encode(), response.content)


class CoverColorTests(TestCase):
    """Color medio de las portadas para pintar el hueco mientras cargan."""

    def setUp(self):
        self.media = tempfile.mkdtemp()
        self.covers = os.path.join(self.media, 'Covers')
        os.makedirs(self.covers)
        self.override = override_settings(MEDIA_ROOT=self.media)
        self.override.enable()

    def tearDown(self):
        self.override.disable()
        import shutil
        shutil.rmtree(self.media, ignore_errors=True)

    def _image(self, name, color):
        # PNG y no WebP: WebP comprime con pérdida y movería el color un punto.
        # El índice guarda lo que diga el nombre, así que la extensión da igual.
        path = os.path.join(self.covers, name)
        Image.new('RGB', (20, 30), color).save(path, 'PNG')
        return path

    def test_remember_writes_the_average_color_to_the_index(self):
        from . import cover_colors

        path = self._image('7.webp', (200, 40, 10))

        self.assertEqual(cover_colors.remember(path), '#c8280a')
        self.assertEqual(cover_colors.color_for('Covers', '7.webp'), '#c8280a')

    def test_tag_paints_the_color_and_nothing_when_unknown(self):
        from django.template import Context, Template
        from . import cover_colors

        cover_colors.remember(self._image('7.webp', (0, 128, 255)))
        tpl = Template('{% load covers %}<i{% cover_style "Covers" id ".webp" %}>')

        self.assertEqual(tpl.render(Context({'id': 7})), '<i style="--cover-color: #0080ff">')
        self.assertEqual(tpl.render(Context({'id': 8})), '<i>')

    def test_command_backfills_and_drops_colors_of_deleted_images(self):
        from django.core.management import call_command
        from . import cover_colors

        self._image('1.webp', (10, 10, 10))
        cover_colors.save_index(self.covers, {'borrada.webp': '#ffffff'})

        call_command('cover_colors', stdout=io.StringIO())

        self.assertEqual(cover_colors.load_index(self.covers), {'1.webp': '#0a0a0a'})


class AxesClientIpTests(TestCase):
    """axes tiene que ver la IP del visitante, no la de nginx."""

    def test_failed_admin_login_is_recorded_with_the_real_ip(self):
        from axes.models import AccessAttempt

        self.client.post(
            '/j_admin/login/?next=/j_admin/',
            {'username': 'nadie', 'password': 'mal'},
            REMOTE_ADDR='127.0.0.1',
            HTTP_X_REAL_IP='203.0.113.77',
        )

        self.assertEqual(
            list(AccessAttempt.objects.values_list('ip_address', flat=True)),
            ['203.0.113.77'],
        )


class ScheduledCommandsExitCodeTests(TestCase):
    """Los temporizadores de systemd solo ven el código de salida del comando."""

    COMANDOS = (
        ('update_books', 'home_page.management.commands.update_books.update_books_cron'),
        ('update_watching', 'watching.management.commands.update_watching.update_watching_cron'),
        ('update_news', 'my_news.management.commands.update_news.update_news_cron'),
    )

    def test_a_failed_task_makes_the_command_fail(self):
        from django.core.management.base import CommandError

        for comando, tarea in self.COMANDOS:
            with self.subTest(comando=comando), patch(tarea, return_value=False):
                with self.assertRaises(CommandError):
                    call_command(comando)

    def test_a_task_that_works_exits_cleanly(self):
        for comando, tarea in self.COMANDOS:
            with self.subTest(comando=comando), patch(tarea, return_value=True) as mock:
                call_command(comando)
                mock.assert_called_once_with()


class ClearExpiredSessionsTests(TestCase):
    def test_the_nightly_command_deletes_only_expired_sessions(self):
        from django.contrib.sessions.models import Session

        ahora = dj_timezone.now()
        Session.objects.create(session_key='vieja', session_data='x', expire_date=ahora - timedelta(days=1))
        Session.objects.create(session_key='viva', session_data='x', expire_date=ahora + timedelta(days=1))

        with patch('home_page.management.commands.update_books.update_books_cron', return_value=True):
            call_command('update_books')

        self.assertEqual(list(Session.objects.values_list('session_key', flat=True)), ['viva'])

    def test_a_cleanup_failure_does_not_fail_the_books_pass(self):
        with patch('home_page.tasks.call_command', side_effect=RuntimeError('boom')),                 patch('home_page.management.commands.update_books.update_books_cron', return_value=True) as libros:
            with self.assertLogs('home_page.tasks', level='ERROR'):
                call_command('update_books')

        libros.assert_called_once_with()

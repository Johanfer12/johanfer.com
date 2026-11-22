"""Endpoints HTTP del feed de noticias, de punta a punta.

Nacieron como tests de regresión de la migración SSE→polling, y el nombre que
tenían (``tests_smoke_changes``) los hacía parecer un resto temporal. No lo son:
medido con coverage, este fichero es lo ÚNICO que cubre 15 líneas de
``my_news/views/``, entre ellas el cuerpo entero de ``toggle_save_news``. Si se
borran, guardar y desguardar una noticia se queda sin ninguna prueba.

Cubren la ausencia del endpoint news-stream, el chequeo por cursor del sondeo,
las mutaciones (guardar, eliminar, deshacer), el redirect del login y el botón
de acceso de la cabecera pública.
"""
from django.contrib.auth.models import User
from django.core.cache import cache
from django.test import TestCase
from django.urls import NoReverseMatch, reverse
from django.utils import timezone
from datetime import timedelta

from .models import FeedSource, News


def make_news(source, title, minutes_ago=120, **kwargs):
    now = timezone.now()
    news = News.objects.create(
        guid=f"guid-{title}",
        title=title,
        description=f"desc {title}",
        link=f"https://example.com/{title}",
        published_date=now - timedelta(minutes=minutes_ago),
        source=source,
        is_ai_processed=True,
        **kwargs,
    )
    # created_at es auto_now_add; lo retrasamos para superar el settle delay (60s)
    News.objects.filter(pk=news.pk).update(created_at=now - timedelta(minutes=minutes_ago))
    news.refresh_from_db()
    return news


class StreamRemovalTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_superuser('admin', 'a@a.com', 'pass')
        self.client.force_login(self.user)
        self.source = FeedSource.objects.create(name='Fuente', url='https://example.com/rss')

    def test_news_stream_url_removed(self):
        with self.assertRaises(NoReverseMatch):
            reverse('my_news:news_stream')
        response = self.client.get('/noticias/news-stream/')
        self.assertEqual(response.status_code, 404)

    def test_check_new_news_returns_fresh_items_after_cursor(self):
        old = make_news(self.source, 'vieja', minutes_ago=180)
        cursor = f"{old.created_at.isoformat()}|{old.id}"
        nueva = make_news(self.source, 'nueva', minutes_ago=90)

        response = self.client.get(reverse('my_news:check_new_news'), {'cursor': cursor})
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['status'], 'success')
        ids = [card['id'] for card in data['news_cards']]
        self.assertEqual(ids, [nueva.id])
        self.assertTrue(data['cursor'].endswith(f"|{nueva.id}"))

    def test_toggle_save_news_still_accepts_post(self):
        # Regresión: al eliminar news_stream quedó un @require_GET huérfano que
        # caía sobre esta vista y la habría dejado siempre en 405.
        news = make_news(self.source, 'guardable')
        url = reverse('my_news:toggle_save_news', args=[news.id])

        response = self.client.post(url, {'saved_only': 'false'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['status'], 'success')
        news.refresh_from_db()
        self.assertTrue(news.is_saved)

        # GET debe seguir rechazado (405) por @require_POST
        self.assertEqual(self.client.get(url).status_code, 405)

    def test_delete_and_undo_roundtrip(self):
        news = make_news(self.source, 'borrable')
        delete_url = reverse('my_news:delete_news', args=[news.id])
        response = self.client.post(delete_url, {'current_page': 1})
        self.assertEqual(response.json()['status'], 'success')
        news.refresh_from_db()
        self.assertTrue(news.is_deleted)

        undo_url = reverse('my_news:undo_delete', args=[news.id])
        response = self.client.post(undo_url, {'saved_only': 'false'})
        self.assertEqual(response.json()['status'], 'success')
        news.refresh_from_db()
        self.assertFalse(news.is_deleted)

    def test_login_redirects_to_news_list(self):
        # Regresión: sin next_page, Django redirigía a /accounts/profile/ (404).
        self.client.logout()
        response = self.client.post(
            reverse('my_news:news_login'),
            {'username': 'admin', 'password': 'pass'},
        )
        self.assertRedirects(response, '/noticias/')

    def test_public_header_shows_login_button_for_anonymous(self):
        self.client.logout()
        response = self.client.get(reverse('my_news:news_list'))
        self.assertContains(response, 'Iniciar sesión')
        # Logueado como superuser no debe aparecer
        self.client.force_login(self.user)
        response = self.client.get(reverse('my_news:news_list'))
        self.assertNotContains(response, 'Iniciar sesión')

    def test_get_page_success(self):
        for i in range(3):
            make_news(self.source, f"pagina-{i}")
        response = self.client.get(reverse('my_news:get_page'), {'page': 1})
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['status'], 'success')
        self.assertEqual(len(data['cards']), 3)


class FeedKeysetPaginationTests(TestCase):
    """La paginación por cursor y por número de página dan las mismas tarjetas."""

    def setUp(self):
        # Las páginas se cachean unos segundos con una clave que no distingue
        # entre tests: sin limpiar, saldrían las del test anterior.
        cache.clear()
        self.addCleanup(cache.clear)
        self.user = User.objects.create_superuser('admin', 'a@a.com', 'pass')
        self.client.force_login(self.user)
        self.source = FeedSource.objects.create(name='Fuente', url='https://example.com/rss')
        base = timezone.now() - timedelta(hours=5)
        for i in range(60):
            news = make_news(self.source, f'n{i:02d}')
            # Empates de fecha de a tres: el id es el que desempata.
            News.objects.filter(pk=news.pk).update(published_date=base + timedelta(minutes=i // 3))

    def _page(self, **params):
        response = self.client.get(reverse('my_news:get_page'), params)
        self.assertEqual(response.status_code, 200)
        return response.json()

    def _walk(self, order):
        ids, cursor = [], None
        while True:
            params = {'order': order}
            if cursor:
                params['cursor'] = cursor
            data = self._page(**params)
            ids += [card['id'] for card in data['cards']]
            cursor = data['next_cursor']
            if not cursor:
                return ids

    def test_cursor_walk_matches_database_order(self):
        for order, ordering in (('desc', ('-published_date', '-id')), ('asc', ('published_date', 'id'))):
            with self.subTest(order=order):
                expected = list(News.objects.order_by(*ordering).values_list('id', flat=True))
                self.assertEqual(self._walk(order), expected)

    def test_page_number_matches_cursor(self):
        for order in ('desc', 'asc'):
            with self.subTest(order=order):
                first = self._page(order=order)
                by_cursor = self._page(order=order, cursor=first['next_cursor'])
                by_page = self._page(order=order, page=2)
                self.assertEqual(
                    [c['id'] for c in by_cursor['cards']],
                    [c['id'] for c in by_page['cards']],
                )
                self.assertEqual(by_cursor['next_cursor'], by_page['next_cursor'])

    def test_invalid_cursor_is_ignored(self):
        first = [c['id'] for c in self._page()['cards']]
        for cursor in ('basura', 'no-es-fecha|3', '2026-01-01T00:00:00|x', 'a|b|c'):
            with self.subTest(cursor=cursor):
                self.assertEqual([c['id'] for c in self._page(cursor=cursor)['cards']], first)

    def test_latest_deleted_respects_search(self):
        a = News.objects.get(title='n01')
        b = News.objects.get(title='n02')
        News.objects.filter(pk=a.pk).update(is_deleted=True, deleted_at=timezone.now() - timedelta(minutes=5))
        News.objects.filter(pk=b.pk).update(is_deleted=True, deleted_at=timezone.now())

        url = reverse('my_news:latest_deleted_news')
        self.assertEqual(self.client.get(url).json()['news_id'], b.id)
        self.assertEqual(self.client.get(url, {'q': 'desc n01'}).json()['news_id'], a.id)
        self.assertEqual(self.client.get(url, {'q': 'nada'}).json()['status'], 'empty')

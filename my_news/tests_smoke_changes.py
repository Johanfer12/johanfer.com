"""Tests de regresión para la migración SSE→polling de noticias.

Cubren la eliminación del endpoint news-stream, el chequeo por cursor que usa
el sondeo del frontend, y los endpoints de mutación (guardar/eliminar/deshacer).
"""
from django.contrib.auth.models import User
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

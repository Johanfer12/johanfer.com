from datetime import date
from types import SimpleNamespace
from unittest.mock import patch

from django.test import TestCase

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

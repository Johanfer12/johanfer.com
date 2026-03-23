from django.test import TestCase

from .models import VisitLog


class VisitLogMiddlewareTests(TestCase):
    def test_news_page_is_logged(self):
        response = self.client.get('/noticias/', HTTP_ACCEPT='text/html')

        self.assertEqual(response.status_code, 200)
        self.assertTrue(VisitLog.objects.filter(path='/noticias/').exists())

    def test_news_internal_endpoint_is_not_logged(self):
        response = self.client.get('/noticias/get-page/', HTTP_ACCEPT='text/html')

        self.assertEqual(response.status_code, 302)
        self.assertFalse(VisitLog.objects.filter(path='/noticias/get-page/').exists())

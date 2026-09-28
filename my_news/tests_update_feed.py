"""El botón de actualizar lanza la pasada aparte y el navegador pregunta por ella.

Antes la pasada corría dentro de la petición: tardaba minutos, nginx cortaba a
los 60 s con un 504 y el botón daba error aunque la pasada terminara bien.
"""
from datetime import timedelta
from unittest.mock import MagicMock, patch

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from . import views
from .ingestion_status import report_ok, report_paused


class UpdateFeedTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_superuser('admin', 'a@example.com', 'x')
        self.client.force_login(self.user)
        views._manual_update_process = None
        views._manual_update_started = None

    def tearDown(self):
        views._manual_update_process = None
        views._manual_update_started = None

    @patch('my_news.views.news_update_running', return_value=False)
    @patch('my_news.views.subprocess.Popen')
    def test_launches_the_pass_in_background_and_returns_at_once(self, popen, _running):
        popen.return_value.poll.return_value = None
        response = self.client.post(reverse('my_news:update_feed'))
        self.assertEqual(response.json()['status'], 'started')
        args = popen.call_args.args[0]
        self.assertEqual(args[-1], 'update_news')

    @patch('my_news.views.news_update_running', return_value=True)
    @patch('my_news.views.subprocess.Popen')
    def test_does_not_launch_while_the_cron_is_running(self, popen, _running):
        response = self.client.post(reverse('my_news:update_feed'))
        self.assertEqual(response.json()['status'], 'running')
        popen.assert_not_called()

    def test_get_is_rejected(self):
        response = self.client.get(reverse('my_news:update_feed'))
        self.assertEqual(response.status_code, 405)

    def _status(self, since):
        return self.client.get(
            reverse('my_news:update_feed_status'), {'since': since.isoformat()}
        ).json()

    def test_status_is_running_until_the_pass_writes_its_state(self):
        report_ok(new_count=1)
        since = timezone.now() + timedelta(seconds=1)
        self.assertEqual(self._status(since)['status'], 'running')

    def test_status_reports_the_result_of_the_pass(self):
        since = timezone.now() - timedelta(seconds=1)
        report_paused('Cuota agotada', new_count=3)
        data = self._status(since)
        self.assertEqual(data['status'], 'done')
        self.assertEqual(data['state'], 'paused')
        self.assertEqual(data['reason'], 'Cuota agotada')
        self.assertIn('total_news', data)

    def test_status_reports_a_process_that_died_without_writing(self):
        since = timezone.now()
        proc = MagicMock()
        proc.poll.return_value = 1
        proc.returncode = 1
        views._manual_update_process = proc
        views._manual_update_started = since
        data = self._status(since)
        self.assertEqual(data['status'], 'done')
        self.assertEqual(data['state'], 'error')

    def test_an_old_failed_launch_is_not_blamed_on_a_new_click(self):
        proc = MagicMock()
        proc.poll.return_value = 1
        proc.returncode = 1
        views._manual_update_process = proc
        views._manual_update_started = timezone.now() - timedelta(hours=1)
        self.assertEqual(self._status(timezone.now())['status'], 'running')

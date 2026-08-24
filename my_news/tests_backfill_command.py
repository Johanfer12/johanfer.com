from io import StringIO
from unittest.mock import patch
from django.core.management import call_command
from django.test import SimpleTestCase


class QdrantBackfillCommandTests(SimpleTestCase):
    """El comando solo repite tandas de tasks.retry_missing_embeddings."""

    def run_command(self, secuencia, **opciones):
        salida = StringIO()
        with patch('my_news.management.commands.qdrant_backfill.retry_missing_embeddings',
                   side_effect=secuencia) as fake:
            call_command('qdrant_backfill', stdout=salida, **opciones)
        return fake, salida.getvalue()

    def test_repeats_until_a_pass_recovers_nothing(self):
        fake, salida = self.run_command([25, 25, 3, 0])

        self.assertEqual(fake.call_count, 4)
        self.assertIn('Indexadas 53', salida)

    def test_passes_the_window_and_the_batch_size_through(self):
        fake, _ = self.run_command([0], days=30, limit=5)

        fake.assert_called_once_with(limit=5, days=30)

    def test_stops_at_the_pass_cap_and_says_so(self):
        fake, salida = self.run_command([1] * 3, passes=3)

        self.assertEqual(fake.call_count, 3)
        self.assertIn('tope de 3 tandas', salida)

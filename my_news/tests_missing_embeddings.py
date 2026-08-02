from types import SimpleNamespace
from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone
from datetime import timedelta

from .models import FeedSource, FilterWord, News
from .tasks import retry_missing_embeddings


class FakeVectorIndex:
    """Índice en memoria que imita lo que usa retry_missing_embeddings."""

    def __init__(self, indexed_news_ids=()):
        self.points = [
            SimpleNamespace(payload={"news_id": nid}) for nid in indexed_news_ids
        ]
        self.upserted = {}

    def scroll_points(self, limit=256):
        return iter(self.points)

    def ensure_collection(self, dim):
        pass

    def upsert(self, guid, vector, payload):
        self.upserted[guid] = payload


class RetryMissingEmbeddingsTests(TestCase):
    def setUp(self):
        self.source = FeedSource.objects.create(
            name="Fuente", url="https://example.com/rss", similarity_threshold=0.85
        )
        self.counter = 0

    def make_news(self, **kwargs):
        self.counter += 1
        defaults = {
            "guid": f"guid-{self.counter}",
            "title": f"Noticia {self.counter}",
            "description": "Cuerpo de la noticia",
            "link": f"https://example.com/{self.counter}",
            "published_date": timezone.now(),
            "source": self.source,
        }
        defaults.update(kwargs)
        return News.objects.create(**defaults)

    def run_retry(self, index, **kwargs):
        with patch("my_news.tasks.FeedService.initialize_vector_index", return_value=index), \
             patch("my_news.tasks.FeedService.initialize_gemini", return_value=object()), \
             patch(
                 "my_news.tasks.EmbeddingService.generate_embedding",
                 return_value=[0.1] * 8,
             ), \
             patch(
                 "my_news.tasks.EmbeddingService.check_redundancy",
                 return_value=(False, None, 0.0),
             ):
            return retry_missing_embeddings(**kwargs)

    def test_indexa_la_noticia_que_se_quedo_sin_vector(self):
        news = self.make_news()
        index = FakeVectorIndex()

        recuperadas = self.run_retry(index)

        self.assertEqual(recuperadas, 1)
        self.assertIn(news.guid, index.upserted)
        payload = index.upserted[news.guid]
        self.assertEqual(payload["news_id"], news.id)
        # search() exige estos flags en False; si cambian, la noticia quedaría
        # indexada pero invisible para la detección de duplicados.
        self.assertFalse(payload["is_filtered"])
        self.assertFalse(payload["is_redundant"])

    def test_no_reindexa_lo_que_ya_esta_en_qdrant(self):
        news = self.make_news()
        index = FakeVectorIndex(indexed_news_ids=[news.id])

        self.assertEqual(self.run_retry(index), 0)
        self.assertEqual(index.upserted, {})

    def test_ignora_las_que_no_se_indexan_por_diseno(self):
        palabra = FilterWord.objects.create(word="horóscopo")
        self.make_news(filtered_by=palabra, is_filtered=True)
        self.make_news(is_redundant=True)
        self.make_news(is_ai_filtered=True, is_filtered=True)

        index = FakeVectorIndex()
        self.assertEqual(self.run_retry(index), 0)
        self.assertEqual(index.upserted, {})

    def test_ignora_las_mas_viejas_que_la_ventana(self):
        self.make_news(published_date=timezone.now() - timedelta(days=20))

        index = FakeVectorIndex()
        self.assertEqual(self.run_retry(index, days=15), 0)
        self.assertEqual(index.upserted, {})

    def test_respeta_el_limite_de_llamadas(self):
        for _ in range(5):
            self.make_news()

        index = FakeVectorIndex()
        self.assertEqual(self.run_retry(index, limit=2), 2)
        self.assertEqual(len(index.upserted), 2)

    def test_no_marca_redundante_a_posteriori(self):
        """Una noticia ya publicada no debe desaparecer de la rejilla."""
        news = self.make_news()
        gemela = self.make_news(title="Casi la misma noticia")
        index = FakeVectorIndex(indexed_news_ids=[gemela.id])

        with patch("my_news.tasks.FeedService.initialize_vector_index", return_value=index), \
             patch("my_news.tasks.FeedService.initialize_gemini", return_value=object()), \
             patch(
                 "my_news.tasks.EmbeddingService.generate_embedding",
                 return_value=[0.1] * 8,
             ), \
             patch(
                 "my_news.tasks.EmbeddingService.check_redundancy",
                 return_value=(True, gemela, 0.97),
             ):
            retry_missing_embeddings()

        news.refresh_from_db()
        self.assertFalse(news.is_redundant)
        # Pero sí queda anotado el parecido, para poder revisarlo en el admin.
        self.assertEqual(news.similar_to_id, gemela.id)
        self.assertAlmostEqual(news.similarity_score, 0.97)

    def test_sin_qdrant_no_revienta(self):
        self.make_news()
        with patch("my_news.tasks.FeedService.initialize_vector_index", return_value=None):
            self.assertEqual(retry_missing_embeddings(), 0)

    def test_si_el_embedding_vuelve_a_fallar_no_cuenta_como_recuperada(self):
        self.make_news()
        index = FakeVectorIndex()

        with patch("my_news.tasks.FeedService.initialize_vector_index", return_value=index), \
             patch("my_news.tasks.FeedService.initialize_gemini", return_value=object()), \
             patch("my_news.tasks.EmbeddingService.generate_embedding", return_value=None):
            self.assertEqual(retry_missing_embeddings(), 0)

        self.assertEqual(index.upserted, {})

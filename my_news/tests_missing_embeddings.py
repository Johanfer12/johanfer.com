import numpy as np
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


class RescoreRecentNewsTests(TestCase):
    """El repuntuado de la ventana, que corre al final de cada cron."""

    def setUp(self):
        self.source = FeedSource.objects.create(
            name="Fuente", url="https://example.com/rss", similarity_threshold=0.85
        )
        self.counter = 0

    def make_news(self, **kwargs):
        self.counter += 1
        defaults = {
            "guid": f"guid-r{self.counter}",
            "title": f"Noticia {self.counter}",
            "description": "Cuerpo",
            "link": f"https://example.com/r{self.counter}",
            "published_date": timezone.now(),
            "source": self.source,
            "is_ai_processed": True,
        }
        defaults.update(kwargs)
        return News.objects.create(**defaults)

    def test_sin_votos_suficientes_no_toca_qdrant(self):
        """Es el caso de produccion recien desplegada: debe salir gratis."""
        from my_news.tasks import rescore_recent_news

        self.make_news()
        with patch("my_news.tasks.FeedService.initialize_vector_index") as init:
            self.assertEqual(rescore_recent_news(), 0)
            init.assert_not_called()

    def test_puntua_las_visibles_en_una_sola_pasada(self):
        from my_news.interest import InterestModel
        from my_news.tasks import rescore_recent_news

        noticias = [self.make_news() for _ in range(3)]
        vectores = {n.guid: np.array([1.0, 0.0], dtype=np.float32) for n in noticias}

        index = FakeVectorIndex()
        index.vectors_for_guids = lambda guids: vectores

        modelo = InterestModel(
            np.array([[1.0, 0.0]], dtype=np.float32) * np.ones((5, 2), dtype=np.float32),
            np.array([[0.0, 1.0]], dtype=np.float32) * np.ones((5, 2), dtype=np.float32),
        )
        with patch("my_news.tasks.InterestModel.load", return_value=modelo), \
             patch("my_news.tasks.FeedService.initialize_vector_index", return_value=index):
            puntuadas = rescore_recent_news()

        self.assertEqual(puntuadas, 3)
        for n in noticias:
            n.refresh_from_db()
            self.assertIsNotNone(n.interest_score)

    def test_puntua_tambien_las_ya_leidas(self):
        """Las leidas son parte de la referencia del percentil.

        Si solo se puntuara lo pendiente, la referencia encogeria segun se lee y
        el percentil de una noticia cambiaria por lo que se borro a su lado.
        """
        from my_news.interest import InterestModel
        from my_news.tasks import rescore_recent_news

        leida = self.make_news(is_deleted=True)
        sin_leer = self.make_news()
        index = FakeVectorIndex()
        pedidos = {}

        def fake_bulk(guids):
            pedidos["guids"] = list(guids)
            return {}

        index.vectors_for_guids = fake_bulk
        modelo = InterestModel(
            np.ones((5, 2), dtype=np.float32), np.ones((5, 2), dtype=np.float32)
        )
        with patch("my_news.tasks.InterestModel.load", return_value=modelo), \
             patch("my_news.tasks.FeedService.initialize_vector_index", return_value=index):
            rescore_recent_news()

        self.assertIn(leida.guid, pedidos.get("guids", []))
        self.assertIn(sin_leer.guid, pedidos.get("guids", []))

    def test_no_puntua_las_filtradas_ni_las_redundantes(self):
        from my_news.interest import InterestModel
        from my_news.tasks import rescore_recent_news

        redundante = self.make_news(is_redundant=True)
        filtrada = self.make_news(is_ai_filtered=True, is_filtered=True)
        buena = self.make_news()
        index = FakeVectorIndex()
        pedidos = {}

        def fake_bulk(guids):
            pedidos["guids"] = list(guids)
            return {}

        index.vectors_for_guids = fake_bulk
        modelo = InterestModel(
            np.ones((5, 2), dtype=np.float32), np.ones((5, 2), dtype=np.float32)
        )
        with patch("my_news.tasks.InterestModel.load", return_value=modelo), \
             patch("my_news.tasks.FeedService.initialize_vector_index", return_value=index):
            rescore_recent_news()

        pedidas = pedidos.get("guids", [])
        self.assertIn(buena.guid, pedidas)
        self.assertNotIn(redundante.guid, pedidas)
        self.assertNotIn(filtrada.guid, pedidas)

from types import SimpleNamespace
from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone
from datetime import timedelta

from .models import FeedSource, FilterWord, News, PendingEmbedding
from .services import FeedService
from .tasks import retry_missing_embeddings
from .tests import FeedEntry


class FakeVectorIndex:
    """Índice en memoria que imita lo que usa retry_missing_embeddings."""

    def __init__(self, indexed_news_ids=(), falla_upsert=False):
        self.points = [
            SimpleNamespace(payload={"news_id": nid}) for nid in indexed_news_ids
        ]
        self.upserted = {}
        self.vectores = {}
        self.falla_upsert = falla_upsert

    def scroll_points(self, limit=256):
        return iter(self.points)

    def known_guids(self, guids, batch_size=256):
        """Contrato nuevo: se pregunta por guids concretos, no se recorre todo."""
        indexados = {p.payload["news_id"] for p in self.points}
        pedidos = set(guids)
        return set(
            News.objects.filter(id__in=indexados, guid__in=pedidos)
            .values_list("guid", flat=True)
        )

    def ensure_collection(self, dim):
        pass

    def upsert(self, guid, vector, payload):
        if self.falla_upsert:
            raise ConnectionError("Qdrant caído")
        self.upserted[guid] = payload
        self.vectores[guid] = vector


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
            "description": "Resumen de la IA",
            "link": f"https://example.com/{self.counter}",
            "published_date": timezone.now(),
            "source": self.source,
        }
        defaults.update(kwargs)
        return News.objects.create(**defaults)

    def make_pending(self, text="Titular Artículo original completo", vector=None, **kwargs):
        news = self.make_news(**kwargs)
        PendingEmbedding.objects.create(news=news, text=text, vector=vector)
        return news

    def run_retry(self, index, embedding=(0.1,) * 8, **kwargs):
        """Ejercita el camino real: los embeddings se piden EN LOTE.

        Antes se mockeaba `generate_embedding`, y al pasar el reintento a
        lotes el test seguía pasando por el respaldo de uno en uno sin
        ejercitar lo que de verdad corre en producción.
        """
        self.lotes = []

        def lote_falso(textos, cliente, **_):
            self.lotes.append(list(textos))
            return [list(embedding) if embedding else None for _ in textos]

        with patch("my_news.tasks.FeedService.initialize_vector_index", return_value=index), \
             patch("my_news.tasks.FeedService.initialize_gemini", return_value=object()), \
             patch(
                 "my_news.tasks.EmbeddingService.generate_embeddings_batch",
                 side_effect=lote_falso,
             ), \
             patch(
                 "my_news.tasks.EmbeddingService.check_redundancy",
                 return_value=(False, None, 0.0),
             ):
            return retry_missing_embeddings(**kwargs)

    # --- Pendientes anotados por la ingesta -------------------------------

    def test_vectoriza_el_texto_original_y_no_el_resumen(self):
        """El resumen es otro texto: su vector no reconoce duplicados del artículo."""
        news = self.make_pending(text="Titular Cuerpo original del artículo")
        index = FakeVectorIndex()

        self.assertEqual(self.run_retry(index), 1)

        self.assertEqual(self.lotes, [["Titular Cuerpo original del artículo"]])
        self.assertIn(news.guid, index.upserted)
        self.assertFalse(PendingEmbedding.objects.exists())

    def test_con_vector_guardado_no_llama_a_gemini(self):
        news = self.make_pending(vector=[0.3] * 8)
        index = FakeVectorIndex()

        self.assertEqual(self.run_retry(index), 1)

        self.assertEqual(self.lotes, [])
        self.assertEqual(index.vectores[news.guid], [0.3] * 8)
        self.assertFalse(PendingEmbedding.objects.exists())

    def test_los_embeddings_se_piden_en_una_sola_llamada(self):
        """De uno en uno se acercaba al límite de 100 peticiones por minuto."""
        for _ in range(5):
            self.make_pending()

        self.assertEqual(self.run_retry(FakeVectorIndex()), 5)
        self.assertEqual(len(self.lotes), 1, "debería ser una sola llamada")
        self.assertEqual(len(self.lotes[0]), 5)

    def test_el_payload_deja_la_noticia_visible_para_duplicados(self):
        news = self.make_pending()
        index = FakeVectorIndex()

        self.run_retry(index)

        payload = index.upserted[news.guid]
        self.assertEqual(payload["news_id"], news.id)
        # search() exige estos flags en False; si cambian, la noticia quedaría
        # indexada pero invisible para la detección de duplicados.
        self.assertFalse(payload["is_filtered"])
        self.assertFalse(payload["is_redundant"])

    def test_sin_pendiente_no_se_toca_por_defecto(self):
        """El cron ya no vectoriza resúmenes: sin texto original no hay nada que hacer."""
        self.make_news()
        index = FakeVectorIndex()

        self.assertEqual(self.run_retry(index), 0)
        self.assertEqual(index.upserted, {})

    def test_si_qdrant_sigue_caido_guarda_el_vector_para_la_proxima(self):
        news = self.make_pending()

        self.assertEqual(self.run_retry(FakeVectorIndex(falla_upsert=True)), 0)

        pendiente = PendingEmbedding.objects.get(news=news)
        self.assertEqual(pendiente.vector, [0.1] * 8)

    def test_si_el_embedding_vuelve_a_fallar_sigue_pendiente(self):
        news = self.make_pending()
        index = FakeVectorIndex()

        self.assertEqual(self.run_retry(index, embedding=None), 0)

        self.assertEqual(index.upserted, {})
        self.assertTrue(PendingEmbedding.objects.filter(news=news).exists())

    def test_ignora_las_mas_viejas_que_la_ventana(self):
        self.make_pending(published_date=timezone.now() - timedelta(days=20))

        index = FakeVectorIndex()
        self.assertEqual(self.run_retry(index, days=15), 0)
        self.assertEqual(index.upserted, {})

    def test_respeta_el_limite(self):
        for _ in range(5):
            self.make_pending()

        index = FakeVectorIndex()
        self.assertEqual(self.run_retry(index, limit=2), 2)
        self.assertEqual(len(index.upserted), 2)
        self.assertEqual(PendingEmbedding.objects.count(), 3)

    def test_la_purga_se_lleva_el_pendiente(self):
        news = self.make_pending()
        news.delete()
        self.assertFalse(PendingEmbedding.objects.exists())

    def test_no_marca_redundante_a_posteriori(self):
        """Una noticia ya publicada no debe desaparecer de la rejilla."""
        news = self.make_pending(vector=[0.1] * 8)
        gemela = self.make_news(title="Casi la misma noticia")
        index = FakeVectorIndex(indexed_news_ids=[gemela.id])

        with patch("my_news.tasks.FeedService.initialize_vector_index", return_value=index), \
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
        self.make_pending()
        with patch("my_news.tasks.FeedService.initialize_vector_index", return_value=None):
            self.assertEqual(retry_missing_embeddings(), 0)

    # --- desde_resumen: solo para qdrant_backfill ---------------------------

    def test_desde_resumen_indexa_las_que_no_tienen_pendiente(self):
        news = self.make_news()
        index = FakeVectorIndex()

        self.assertEqual(self.run_retry(index, desde_resumen=True), 1)

        self.assertEqual(self.lotes, [[f"{news.title} Resumen de la IA"]])
        self.assertIn(news.guid, index.upserted)

    def test_desde_resumen_no_reindexa_lo_que_ya_esta_en_qdrant(self):
        news = self.make_news()
        index = FakeVectorIndex(indexed_news_ids=[news.id])

        self.assertEqual(self.run_retry(index, desde_resumen=True), 0)
        self.assertEqual(index.upserted, {})

    def test_desde_resumen_prefiere_el_pendiente_al_resumen(self):
        news = self.make_pending(text="Texto original")
        index = FakeVectorIndex()

        self.assertEqual(self.run_retry(index, desde_resumen=True), 1)
        self.assertEqual(self.lotes, [["Texto original"]])
        self.assertIn(news.guid, index.upserted)

    def test_desde_resumen_ignora_las_que_no_se_indexan_por_diseno(self):
        palabra = FilterWord.objects.create(word="horóscopo")
        self.make_news(filtered_by=palabra, is_filtered=True)
        self.make_news(is_redundant=True)
        self.make_news(is_ai_filtered=True, is_filtered=True)
        # Título largo: filtrada sin palabra. Antes se colaba y quedaba en
        # Qdrant como referencia visible para detectar duplicados.
        self.make_news(is_filtered=True)

        index = FakeVectorIndex()
        self.assertEqual(self.run_retry(index, desde_resumen=True), 0)
        self.assertEqual(index.upserted, {})


class IngestaAnotaPendientesTests(TestCase):
    """La ingesta deja el texto original (o el vector) cuando no llega a Qdrant."""

    def setUp(self):
        self.source = FeedSource.objects.create(
            name="Fuente", url="https://example.com/rss.xml"
        )

    def ingest(self, vector_index, embedding):
        class Response:
            content = b"<rss></rss>"

            def raise_for_status(self):
                return None

        entrada = FeedEntry(
            id="pend-1",
            title="Titular",
            link="https://example.com/pend-1",
            description="Cuerpo original del artículo",
            published_parsed=(timezone.now() - timedelta(minutes=1)).utctimetuple(),
        )
        with patch("my_news.services.requests.get", return_value=Response()), \
             patch("my_news.services.feedparser.parse") as parse, \
             patch("my_news.services.FeedService.initialize_gemini", return_value=object()), \
             patch("my_news.services.FeedService.initialize_vector_index", return_value=vector_index), \
             patch(
                 "my_news.services.EmbeddingService.generate_embeddings_batch",
                 side_effect=lambda textos, cliente, **_: [embedding for _ in textos],
             ), \
             patch(
                 "my_news.services.EmbeddingService.check_redundancy",
                 return_value=(False, None, 0.0),
             ), \
             patch(
                 "my_news.services.FeedService.process_news_content",
                 return_value=("Resumen IA", None, None),
             ):
            parse.return_value.entries = [entrada]
            FeedService.fetch_and_save_news(max_ai_items=5)
        return News.objects.get(guid="pend-1")

    def test_sin_embedding_guarda_el_texto_original(self):
        news = self.ingest(FakeVectorIndex(), None)

        pendiente = PendingEmbedding.objects.get(news=news)
        self.assertEqual(pendiente.text, "Titular Cuerpo original del artículo")
        self.assertIsNone(pendiente.vector)
        self.assertEqual(news.description, "Resumen IA")

    def test_si_falla_qdrant_guarda_el_vector(self):
        news = self.ingest(FakeVectorIndex(falla_upsert=True), [0.2] * 8)

        pendiente = PendingEmbedding.objects.get(news=news)
        self.assertEqual(pendiente.vector, [0.2] * 8)

    def test_si_se_indexa_no_queda_pendiente(self):
        index = FakeVectorIndex()
        news = self.ingest(index, [0.2] * 8)

        self.assertIn(news.guid, index.upserted)
        self.assertFalse(PendingEmbedding.objects.exists())

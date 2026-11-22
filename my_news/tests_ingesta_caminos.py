"""Una pasada de ingesta que recorre todas las salidas de `fetch_and_save_news`.

Cada entrada del feed acaba en una de cinco filas distintas (título largo,
palabra filtro, duplicada, filtrada por la IA, visible) o corta la pasada (la
IA no devuelve resumen). Este test las junta en una sola pasada para fijar qué
se guarda en cada caso, cuánto se cuenta y qué queda anotado.
"""
from datetime import timedelta
from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone

from .models import (
    AIFilterInstruction,
    FeedSource,
    FilterWord,
    IngestionStatus,
    News,
    PendingEmbedding,
)
from .services import FeedService
from .tests import FeedEntry

HOROSCOPO = "Noticias sobre horóscopos o astrología"
VECTOR = [0.1, 0.2, 0.3]


class _Response:
    content = b"<rss></rss>"

    def raise_for_status(self):
        return None


class _FakeIndex:
    def __init__(self):
        self.upserts = []

    def ensure_collection(self, size):
        return None

    def upsert(self, guid, embedding, payload):
        if guid == "t-6":
            raise RuntimeError("Qdrant caído")
        self.upserts.append((guid, list(embedding), payload["title"]))


def _check_redundancy(candidate, client, recent_cache, vector_index):
    if candidate.guid == "t-3":
        candidate._similar_ref = "Original de hace meses"
        return True, None, 0.95
    return False, None, 0.5


def _embeddings(textos, cliente, **_):
    return [None if texto.startswith("Sin vector") else list(VECTOR) for texto in textos]


def _process(title, original_description, filter_text, **kwargs):
    if title == "Horóscopo semanal":
        return "Resumen IA filtrada", None, HOROSCOPO, None
    if title == "Sin resumen":
        return None, None, None, None
    return f"Resumen de {title}", f"Respuesta de {title}", None, f"ES {title}"


class IngestaTodosLosCaminosTests(TestCase):
    def setUp(self):
        self.source = FeedSource.objects.create(name="Fuente", url="https://example.com/rss.xml")
        FilterWord.objects.create(word="lidl")
        AIFilterInstruction.objects.create(instruction=HOROSCOPO)

    def _entries(self):
        now = timezone.now()
        titulos = [
            "X" * 250,
            "Oferta del día en Lidl",
            "Duplicado",
            "Horóscopo semanal",
            "Normal",
            "Sin Qdrant",
            "Sin vector",
            "Sin resumen",
            "Después de la pausa",
        ]
        return [
            FeedEntry(
                id=f"t-{i}",
                title=titulo,
                link=f"https://example.com/t-{i}",
                description=f"Cuerpo de {titulo[:20]}",
                published_parsed=(now - timedelta(minutes=30 - i)).utctimetuple(),
            )
            for i, titulo in enumerate(titulos, start=1)
        ]

    def test_cada_salida_guarda_lo_suyo(self):
        index = _FakeIndex()
        with patch("my_news.services.requests.get", return_value=_Response()), \
                patch("my_news.services.feedparser.parse") as parse, \
                patch("my_news.services.FeedService.initialize_gemini", return_value=object()), \
                patch("my_news.services.FeedService.initialize_vector_index", return_value=index), \
                patch("my_news.services.FeedService.get_full_article_content",
                      return_value={"text": None, "image_url": None}), \
                patch("my_news.services.EmbeddingService.generate_embeddings_batch",
                      side_effect=_embeddings), \
                patch("my_news.services.EmbeddingService.check_redundancy",
                      side_effect=_check_redundancy), \
                patch("my_news.services.FeedService.process_news_content",
                      side_effect=_process) as process, \
                patch.object(FeedService, "_LAST_AI_FAILURE", None), \
                patch("my_news.templatetags.news_images.warm_news_images") as warm:
            parse.return_value.entries = self._entries()
            with self.assertLogs("my_news.services", level="INFO") as logs:
                creadas = FeedService.fetch_and_save_news(max_ai_items=10)

        # El título largo se guarda pero no cuenta; la pasada se corta en
        # «Sin resumen» y lo que viene detrás no se guarda.
        self.assertEqual(creadas, 6)
        self.assertEqual(
            sorted(News.objects.values_list("guid", flat=True)),
            ["t-1", "t-2", "t-3", "t-4", "t-5", "t-6", "t-7"],
        )
        self.assertEqual(process.call_count, 5)

        largo = News.objects.get(guid="t-1")
        self.assertTrue(largo.is_filtered)
        self.assertTrue(largo.is_ai_processed)
        self.assertEqual(len(largo.title), 250)

        clave = News.objects.get(guid="t-2")
        self.assertTrue(clave.is_filtered)
        self.assertEqual(clave.filtered_by.word, "lidl")
        self.assertIsNone(clave.short_answer)

        duplicada = News.objects.get(guid="t-3")
        self.assertTrue(duplicada.is_redundant)
        self.assertTrue(duplicada.is_filtered)
        self.assertEqual(duplicada.similar_ref, "Original de hace meses")
        self.assertEqual(duplicada.similarity_score, 0.95)

        ia = News.objects.get(guid="t-4")
        self.assertTrue(ia.is_ai_filtered)
        self.assertEqual(ia.ai_filter_reason, HOROSCOPO)
        self.assertEqual(ia.description, "Resumen IA filtrada")
        self.assertEqual(ia.title_es, "")

        normal = News.objects.get(guid="t-5")
        self.assertFalse(normal.is_filtered)
        self.assertTrue(normal.is_ai_processed)
        self.assertEqual(normal.description, "Resumen de Normal")
        self.assertEqual(normal.short_answer, "Respuesta de Normal")
        self.assertEqual(normal.title_es, "ES Normal")
        self.assertEqual(normal.similarity_score, 0.5)

        self.assertEqual(index.upserts, [("t-5", VECTOR, "Normal")])
        pendientes = {
            p.news.guid: p.vector for p in PendingEmbedding.objects.select_related("news")
        }
        self.assertEqual(pendientes, {"t-6": VECTOR, "t-7": None})

        estado = IngestionStatus.objects.get()
        self.assertEqual(estado.state, IngestionStatus.STATE_PAUSED)
        self.assertEqual(estado.new_count, 6)
        warm.assert_called_once_with([None, None, None])

        self.source.refresh_from_db()
        self.assertIsNotNone(self.source.last_fetch)
        self.assertTrue(any("Error indexando en Qdrant" in line for line in logs.output))

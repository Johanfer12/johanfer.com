from datetime import timedelta
from unittest.mock import patch

from django.test import SimpleTestCase, TestCase
from django.utils import timezone

from .models import AIFilterInstruction, FeedSource, News
from .services import FeedService
from .tasks import retry_summarize_pending
from .tests import FeedEntry


HOROSCOPO = "Noticias sobre horóscopos o astrología"
OFERTAS = "Artículos que solo anuncian ofertas o descuentos de tiendas"


class ResolveAIFilterTests(SimpleTestCase):
    """Solo filtra lo que se puede atribuir a una instrucción activa."""

    def resolver(self, motivo, instrucciones=(HOROSCOPO, OFERTAS)):
        with self.assertNoLogs('my_news.services', level='ERROR'):
            return FeedService.resolve_ai_filter(motivo, list(instrucciones))

    def test_el_texto_literal_devuelve_la_instruccion(self):
        self.assertEqual(self.resolver(HOROSCOPO), HOROSCOPO)

    def test_tolera_mayusculas_espacios_y_puntuacion(self):
        self.assertEqual(
            self.resolver('  - "noticias sobre  HORÓSCOPOS o astrología."  '), HOROSCOPO
        )

    def test_tolera_que_la_envuelva(self):
        self.assertEqual(
            self.resolver(f"Coincide con la instrucción: {OFERTAS}"), OFERTAS
        )

    def test_tolera_que_la_recorte(self):
        self.assertEqual(
            self.resolver("Artículos que solo anuncian ofertas o descuentos"), OFERTAS
        )

    def test_una_palabra_suelta_no_basta(self):
        self.assertIsNone(self.resolver("Noticias"))

    def test_las_negativas_en_texto_no_filtran(self):
        for motivo in ("null", "None", "Ninguna", "No aplica", "N/A", "false"):
            with self.subTest(motivo=motivo):
                self.assertIsNone(self.resolver(motivo))

    def test_un_motivo_inventado_no_filtra(self):
        self.assertIsNone(self.resolver("Contenido de baja calidad"))

    def test_sin_instrucciones_activas_nunca_filtra(self):
        self.assertIsNone(self.resolver(HOROSCOPO, instrucciones=()))

    def test_vacio_o_no_texto(self):
        for motivo in (None, "", "   ", 0, ["x"]):
            with self.subTest(motivo=motivo):
                self.assertIsNone(self.resolver(motivo))

    def test_acepta_objetos_del_modelo(self):
        instrucciones = [AIFilterInstruction(instruction=HOROSCOPO)]
        self.assertEqual(FeedService.resolve_ai_filter(HOROSCOPO, instrucciones), HOROSCOPO)

    def test_si_caben_varias_gana_la_mas_especifica(self):
        general = "Noticias sobre horóscopos"
        self.assertEqual(
            self.resolver(f"- {HOROSCOPO}", instrucciones=(general, HOROSCOPO)), HOROSCOPO
        )


class FiltroIAEnLaIngestaTests(TestCase):
    def setUp(self):
        self.source = FeedSource.objects.create(name="Fuente", url="https://example.com/rss.xml")
        AIFilterInstruction.objects.create(instruction=HOROSCOPO)

    def ingest(self, ai_filter):
        class Response:
            content = b"<rss></rss>"

            def raise_for_status(self):
                return None

        entrada = FeedEntry(
            id="ia-1",
            title="Titular",
            link="https://example.com/ia-1",
            description="Cuerpo",
            published_parsed=(timezone.now() - timedelta(minutes=1)).utctimetuple(),
        )
        with patch("my_news.services.requests.get", return_value=Response()), \
             patch("my_news.services.feedparser.parse") as parse, \
             patch("my_news.services.FeedService.initialize_gemini", return_value=object()), \
             patch("my_news.services.FeedService.initialize_vector_index", return_value=None), \
             patch(
                 "my_news.services.EmbeddingService.generate_embeddings_batch",
                 side_effect=lambda textos, cliente, **_: [None for _ in textos],
             ), \
             patch(
                 "my_news.services.EmbeddingService.check_redundancy",
                 return_value=(False, None, 0.0),
             ), \
             patch(
                 "my_news.services.FeedService.process_news_content",
                 return_value=("Resumen IA", None, ai_filter),
             ):
            parse.return_value.entries = [entrada]
            FeedService.fetch_and_save_news(max_ai_items=5)
        return News.objects.get(guid="ia-1")

    def test_una_instruccion_reconocida_filtra_con_su_texto_canonico(self):
        news = self.ingest("- noticias sobre horóscopos o astrología.")

        self.assertTrue(news.is_ai_filtered)
        self.assertEqual(news.ai_filter_reason, HOROSCOPO)

    def test_una_negativa_en_texto_deja_la_noticia_visible(self):
        news = self.ingest("Ninguna")

        self.assertFalse(news.is_ai_filtered)
        self.assertFalse(news.is_filtered)
        self.assertIsNone(news.ai_filter_reason)


class FiltroIAEnElReintentoTests(TestCase):
    def setUp(self):
        self.source = FeedSource.objects.create(name="Fuente", url="https://example.com/rss.xml")
        AIFilterInstruction.objects.create(instruction=HOROSCOPO)
        self.news = News.objects.create(
            guid="pend", title="Titular", description="Cuerpo",
            link="https://example.com/pend", published_date=timezone.now(),
            source=self.source, is_ai_processed=False,
        )

    def retry(self, ai_filter):
        with patch(
            "my_news.tasks.FeedService.process_news_content",
            return_value=("Resumen IA", None, ai_filter),
        ):
            retry_summarize_pending(limit=5)
        self.news.refresh_from_db()

    def test_filtra_si_la_reconoce(self):
        self.retry(HOROSCOPO.upper())
        self.assertTrue(self.news.is_ai_filtered)
        self.assertEqual(self.news.ai_filter_reason, HOROSCOPO)

    def test_no_filtra_un_motivo_inventado(self):
        self.retry("Contenido irrelevante")
        self.assertFalse(self.news.is_ai_filtered)
        self.assertTrue(self.news.is_ai_processed)
        self.assertEqual(self.news.description, "Resumen IA")

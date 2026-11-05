"""Titulares traducidos: solo en las fuentes marcadas, y sin tocar el original."""
from datetime import timedelta
from unittest.mock import patch

from django.test import SimpleTestCase, TestCase
from django.utils import timezone

from .ai_providers import (
    GEMINI_RESPONSE_SCHEMA,
    GEMINI_RESPONSE_SCHEMA_CON_TITULO,
    OPENAI_RESPONSE_FORMAT,
    OPENAI_RESPONSE_FORMAT_CON_TITULO,
)
from .models import FeedSource, News
from .services import FeedService
from .tasks import retry_summarize_pending
from .tests import FeedEntry, ProveedorFalso

TITULO = "Temporary Portals Replace Boats and Zeppelins Due to Bugs"
TRADUCIDO = "Portales temporales reemplazan barcos y zepelines debido a errores"


def _procesar(respuesta, translate_title, titulo=TITULO):
    proveedor = ProveedorFalso(respuesta=respuesta)
    with patch('my_news.services.cadena_de_proveedores', return_value=[proveedor]):
        resultado = FeedService.process_news_content(
            titulo, 'Cuerpo de la noticia.', FeedService._DEFAULT_FILTER_INSTRUCTIONS,
            translate_title=translate_title,
        )
    return resultado, proveedor


class PromptYEsquemaTests(SimpleTestCase):
    def setUp(self):
        FeedService._clear_ai_failure()

    def test_sin_traduccion_el_prompt_es_el_de_siempre(self):
        _, proveedor = _procesar(
            '{"summary": "Resumen.", "short_answer": null, "ai_filter": null}', False
        )
        prompt = proveedor.llamadas[0]
        self.assertNotIn('title_es', prompt)
        self.assertFalse(proveedor.traducir_titulo)

    def test_con_traduccion_pide_el_campo_y_el_esquema(self):
        _, proveedor = _procesar(
            '{"summary": "Resumen.", "short_answer": null, "ai_filter": null, '
            f'"title_es": "{TRADUCIDO}"}}', True
        )
        prompt = proveedor.llamadas[0]
        self.assertIn('**title_es**', prompt)
        self.assertIn('"title_es": null', prompt)
        self.assertTrue(proveedor.traducir_titulo)

    def test_la_plantilla_con_titulo_solo_anade_el_campo(self):
        base = FeedService._PROMPT_TEMPLATE
        con = FeedService._PROMPT_TEMPLATE_CON_TITULO
        self.assertEqual(
            con.replace(FeedService._PROMPT_TITLE_FIELD + '\n', '', 1)
               .replace(', "title_es": null', '', 1),
            base,
        )

    def test_los_esquemas_base_no_cambian(self):
        self.assertNotIn('title_es', GEMINI_RESPONSE_SCHEMA['properties'])
        self.assertNotIn('title_es', GEMINI_RESPONSE_SCHEMA['required'])
        schema = OPENAI_RESPONSE_FORMAT['json_schema']['schema']
        self.assertNotIn('title_es', schema['properties'])
        self.assertNotIn('title_es', schema['required'])

        self.assertIn('title_es', GEMINI_RESPONSE_SCHEMA_CON_TITULO['required'])
        self.assertIn('title_es', OPENAI_RESPONSE_FORMAT_CON_TITULO['json_schema']['schema']['required'])


class InterpretarTituloTests(SimpleTestCase):
    def setUp(self):
        FeedService._clear_ai_failure()

    def respuesta(self, title_es):
        valor = 'null' if title_es is None else f'"{title_es}"'
        return ('{"summary": "Resumen.", "short_answer": null, "ai_filter": null, '
                f'"title_es": {valor}}}')

    def test_devuelve_la_traduccion(self):
        (_, _, _, title_es), _ = _procesar(self.respuesta(TRADUCIDO), True)
        self.assertEqual(title_es, TRADUCIDO)

    def test_null_es_none(self):
        (_, _, _, title_es), _ = _procesar(self.respuesta(None), True)
        self.assertIsNone(title_es)

    def test_si_repite_el_original_se_descarta(self):
        (_, _, _, title_es), _ = _procesar(self.respuesta(TITULO.upper() + '  '), True)
        self.assertIsNone(title_es)

    def test_sin_pedirla_se_ignora_aunque_venga(self):
        (_, _, _, title_es), _ = _procesar(self.respuesta(TRADUCIDO), False)
        self.assertIsNone(title_es)


class _IngestaMixin:
    def ingest(self, source, title_es):
        class Response:
            content = b"<rss></rss>"

            def raise_for_status(self):
                return None

        entrada = FeedEntry(
            id="tr-1",
            title=TITULO,
            link="https://example.com/tr-1",
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
                 return_value=("Resumen IA", None, None, title_es),
             ) as proceso:
            parse.return_value.entries = [entrada]
            FeedService.fetch_and_save_news(max_ai_items=5)
        return News.objects.get(guid="tr-1"), proceso


class IngestaTests(_IngestaMixin, TestCase):
    def test_fuente_marcada_guarda_la_traduccion_y_conserva_el_original(self):
        source = FeedSource.objects.create(
            name="Wowhead", url="https://example.com/rss.xml", translate_titles=True
        )
        news, proceso = self.ingest(source, TRADUCIDO)

        self.assertTrue(proceso.call_args.kwargs['translate_title'])
        self.assertEqual(news.title, TITULO)
        self.assertEqual(news.title_es, TRADUCIDO)
        self.assertEqual(news.display_title, TRADUCIDO)

    def test_fuente_sin_marcar_no_la_pide(self):
        source = FeedSource.objects.create(name="Xataka", url="https://example.com/rss.xml")
        news, proceso = self.ingest(source, None)

        self.assertFalse(proceso.call_args.kwargs['translate_title'])
        self.assertEqual(news.title_es, '')
        self.assertEqual(news.display_title, TITULO)


class ReintentoTests(TestCase):
    def test_el_reintento_traduce_si_la_fuente_lo_pide(self):
        source = FeedSource.objects.create(
            name="Wowhead", url="https://example.com/rss.xml", translate_titles=True
        )
        news = News.objects.create(
            guid="pend", title=TITULO, description="Cuerpo",
            link="https://example.com/pend", published_date=timezone.now(),
            source=source, is_ai_processed=False,
        )
        with patch(
            "my_news.tasks.FeedService.process_news_content",
            return_value=("Resumen IA", None, None, TRADUCIDO),
        ) as proceso:
            retry_summarize_pending(limit=5)

        news.refresh_from_db()
        self.assertTrue(proceso.call_args.kwargs['translate_title'])
        self.assertEqual(news.title, TITULO)
        self.assertEqual(news.title_es, TRADUCIDO)


class MigracionTests(TestCase):
    def test_la_migracion_marca_wowhead(self):
        from importlib import import_module

        from django.apps import apps

        migracion = import_module('my_news.migrations.0045_titulares_traducidos')
        wowhead = FeedSource.objects.create(name="Wowhead", url="https://www.wowhead.com/news/rss/all")
        otra = FeedSource.objects.create(name="Xataka", url="https://www.xataka.com/feedburner.xml")

        migracion.activar_en_fuentes_en_ingles(apps, None)

        wowhead.refresh_from_db()
        otra.refresh_from_db()
        self.assertTrue(wowhead.translate_titles)
        self.assertFalse(otra.translate_titles)


class BusquedaTests(TestCase):
    def test_se_encuentra_por_el_titular_traducido_y_por_el_original(self):
        from .views import _apply_feed_filters

        source = FeedSource.objects.create(name="Wowhead", url="https://example.com/rss.xml")
        News.objects.create(
            guid="b1", title=TITULO, title_es=TRADUCIDO, description="Resumen",
            link="https://example.com/b1", published_date=timezone.now(), source=source,
        )
        for consulta in ("zepelines", "Zeppelins"):
            with self.subTest(consulta=consulta):
                qs = _apply_feed_filters(News.objects.all(), search_query=consulta)
                self.assertEqual(list(qs.values_list('guid', flat=True)), ["b1"])

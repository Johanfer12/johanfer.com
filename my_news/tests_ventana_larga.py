"""Ventana de duplicados de un año con umbral por tramo.

Lo que se comprueba aquí es la decisión medida en septiembre de 2026: los
duplicados reales de una republicación puntúan 0,93-0,95, así que en el tramo
largo se puede exigir 0,92 y dejar fuera el ruido, que a un año de distancia
marcaría como duplicada casi una de cada tres noticias con el 0,85 de siempre.
"""

import time
from types import SimpleNamespace
from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone

from .models import FeedSource, News
from .services import (
    EmbeddingService,
    FeedService,
    LONG_WINDOW_THRESHOLD,
    RECENT_WINDOW_DAYS,
    REDUNDANCY_WINDOW_DAYS,
)


class IndiceFalso:
    """Devuelve los aciertos que se le indiquen y anota cómo se le consultó."""

    def __init__(self, hits):
        self.hits = hits
        self.ultima_busqueda = None

    def ensure_collection(self, dim):
        pass

    def search(self, vector, top_k, min_published_ts=None, exclude_guid=None,
               extra_must=None):
        self.ultima_busqueda = {
            'top_k': top_k,
            'min_published_ts': min_published_ts,
            'exclude_guid': exclude_guid,
        }
        return self.hits


def acierto(score, published_ts, news_id=None, titulo='', enlace='', guid=''):
    return SimpleNamespace(
        score=score,
        payload={
            'news_id': news_id,
            'guid': guid,
            'published_ts': published_ts,
            'title': titulo,
            'link': enlace,
        },
    )


class VentanaLargaTests(TestCase):
    def setUp(self):
        self.source = FeedSource.objects.create(
            name='Fuente', url='https://example.com/rss', similarity_threshold=0.85
        )
        self.ahora = int(time.time())

    def candidata(self):
        noticia = News(
            guid='nueva',
            title='Titular nuevo',
            description='Cuerpo',
            source=self.source,
            published_date=timezone.now(),
        )
        noticia._embedding_vector = [0.1] * 8
        return noticia

    def comprobar(self, hits):
        indice = IndiceFalso(hits)
        resultado = EmbeddingService.check_redundancy(
            self.candidata(), object(), None, indice
        )
        return resultado, indice

    def test_la_busqueda_abarca_un_ano(self):
        (_, _, _), indice = self.comprobar([])
        margen = self.ahora - indice.ultima_busqueda['min_published_ts']
        self.assertAlmostEqual(margen, REDUNDANCY_WINDOW_DAYS * 86400, delta=60)

    def test_en_el_tramo_reciente_basta_el_umbral_de_la_fuente(self):
        gemela = News.objects.create(
            guid='vieja', title='Titular gemelo', description='x',
            link='https://example.com/1', published_date=timezone.now(),
            source=self.source,
        )
        hit = acierto(0.87, self.ahora - 2 * 86400, news_id=gemela.id)
        (es_redundante, similar, score), _ = self.comprobar([hit])
        self.assertTrue(es_redundante)
        self.assertEqual(similar, gemela)
        self.assertAlmostEqual(score, 0.87)

    def test_en_el_tramo_largo_el_0_87_ya_no_basta(self):
        """El ruido a un año llega a 0,87; exigir 0,92 es lo que lo deja fuera."""
        gemela = News.objects.create(
            guid='vieja', title='Titular gemelo', description='x',
            link='https://example.com/1', published_date=timezone.now(),
            source=self.source,
        )
        viejo = self.ahora - (RECENT_WINDOW_DAYS + 60) * 86400
        hit = acierto(0.87, viejo, news_id=gemela.id)
        (es_redundante, _, score), _ = self.comprobar([hit])
        self.assertFalse(es_redundante)
        self.assertAlmostEqual(score, 0.87)

    def test_en_el_tramo_largo_una_republicacion_real_si_se_caza(self):
        viejo = self.ahora - 300 * 86400
        hit = acierto(0.9348, viejo, titulo='Incendios de sexta generación',
                      enlace='https://example.com/viejo')
        (es_redundante, similar, score), _ = self.comprobar([hit])
        self.assertTrue(es_redundante)
        self.assertGreaterEqual(score, LONG_WINDOW_THRESHOLD)
        # El original ya se purgó: no hay fila, pero sí constancia de cuál era.
        self.assertIsNone(similar)

    def test_deja_constancia_del_original_purgado(self):
        viejo = self.ahora - 300 * 86400
        hit = acierto(0.95, viejo, titulo='Titular de hace meses',
                      enlace='https://example.com/viejo')
        candidata = self.candidata()
        EmbeddingService.check_redundancy(candidata, object(), None, IndiceFalso([hit]))
        referencia = getattr(candidata, '_similar_ref', '')
        self.assertIn('Titular de hace meses', referencia)
        self.assertIn('https://example.com/viejo', referencia)

    def test_cada_acierto_se_juzga_con_el_umbral_de_su_tramo(self):
        """El más parecido no siempre es el que cruza su listón.

        Un vecino antiguo a 0,90 no es duplicado (no llega a 0,92), pero uno
        reciente a 0,86 sí lo es. Mirar solo el primer acierto los confundiría.
        """
        gemela = News.objects.create(
            guid='reciente', title='Gemela reciente', description='x',
            link='https://example.com/2', published_date=timezone.now(),
            source=self.source,
        )
        hits = [
            acierto(0.90, self.ahora - 200 * 86400, titulo='Antigua'),
            acierto(0.86, self.ahora - 3 * 86400, news_id=gemela.id),
        ]
        (es_redundante, similar, score), _ = self.comprobar(hits)
        self.assertTrue(es_redundante)
        self.assertEqual(similar, gemela)
        self.assertAlmostEqual(score, 0.86)

    def test_sin_aciertos_no_hay_duplicado(self):
        (es_redundante, similar, score), _ = self.comprobar([])
        self.assertFalse(es_redundante)
        self.assertIsNone(similar)
        self.assertEqual(score, 0.0)

    def test_no_reintenta_el_embedding_si_el_lote_ya_fallo(self):
        """El lote es justo lo que evita las llamadas de una en una."""
        noticia = News(
            guid='sin-vector', title='T', description='C',
            source=self.source, published_date=timezone.now(),
        )
        noticia._embedding_vector = None
        noticia._embedding_attempted = True
        with patch.object(EmbeddingService, 'generate_embedding') as generar:
            resultado = EmbeddingService.check_redundancy(
                noticia, object(), None, IndiceFalso([])
            )
        generar.assert_not_called()
        self.assertEqual(resultado, (False, None, 0.0))


class PayloadDelVectorTests(TestCase):
    def setUp(self):
        self.source = FeedSource.objects.create(
            name='Fuente', url='https://example.com/rss'
        )

    def test_el_payload_lleva_titulo_y_enlace(self):
        """Sin esto, un duplicado antiguo no podría decir de qué es duplicado."""
        noticia = News.objects.create(
            guid='g1', title='Un titular', description='x',
            link='https://example.com/a', published_date=timezone.now(),
            source=self.source,
        )
        payload = FeedService.build_vector_payload(noticia)
        self.assertEqual(payload['title'], 'Un titular')
        self.assertEqual(payload['link'], 'https://example.com/a')

    def test_describe_vector_payload_es_legible(self):
        texto = FeedService.describe_vector_payload({
            'title': 'Titular', 'link': 'https://example.com/a',
            'published_ts': 1700000000,
        })
        self.assertIn('Titular', texto)
        self.assertIn('2023-11-14', texto)

    def test_describe_vector_payload_aguanta_un_payload_vacio(self):
        self.assertEqual(FeedService.describe_vector_payload({}), '')
        self.assertEqual(FeedService.describe_vector_payload(None), '')


class EmbeddingsEnLoteTests(TestCase):
    """El lote ahorra 9 s por pasada y 34 peticiones de cuota."""

    class ClienteFalso:
        def __init__(self, respuestas=None, error=None):
            self.error = error
            self.respuestas = respuestas
            self.llamadas = []
            self.models = self

        def embed_content(self, model, contents, config):
            self.llamadas.append(contents)
            if self.error:
                raise self.error
            if isinstance(contents, str):
                contents = [contents]
            # El vector depende del texto de forma que sobreviva a la
            # normalización L2 (uno constante se normalizaría siempre igual).
            devueltos = self.respuestas if self.respuestas is not None else [
                SimpleNamespace(values=[float(len(c)), 1.0, 0.0, 0.0])
                for c in contents
            ]
            return SimpleNamespace(embeddings=devueltos)

    def test_un_lote_es_una_sola_llamada(self):
        cliente = self.ClienteFalso()
        vectores = EmbeddingService.generate_embeddings_batch(
            ['uno', 'dos', 'tres'], cliente
        )
        self.assertEqual(len(cliente.llamadas), 1)
        self.assertEqual(len(vectores), 3)
        self.assertTrue(all(v for v in vectores))

    def test_los_vectores_salen_normalizados(self):
        cliente = self.ClienteFalso()
        (vector,) = EmbeddingService.generate_embeddings_batch(['texto'], cliente)
        norma = sum(x * x for x in vector) ** 0.5
        self.assertAlmostEqual(norma, 1.0, places=5)

    def test_respeta_el_orden_de_entrada(self):
        cliente = self.ClienteFalso()
        vectores = EmbeddingService.generate_embeddings_batch(['a', 'bbbb'], cliente)
        # El cliente falso codifica la longitud del texto en el vector.
        self.assertNotEqual(vectores[0], vectores[1])

    def test_si_el_lote_falla_se_cae_a_uno_a_uno(self):
        cliente = self.ClienteFalso(error=RuntimeError('boom'))
        with patch.object(
            EmbeddingService, 'generate_embedding', return_value=[1.0, 0.0]
        ) as unitario:
            vectores = EmbeddingService.generate_embeddings_batch(['a', 'b'], cliente)
        self.assertEqual(unitario.call_count, 2)
        self.assertEqual(vectores, [[1.0, 0.0], [1.0, 0.0]])

    def test_si_faltan_vectores_no_se_cruzan_con_otras_noticias(self):
        """Sin correspondencia posición a posición, rehacer es más seguro."""
        cliente = self.ClienteFalso(respuestas=[SimpleNamespace(values=[1.0] * 4)])
        with patch.object(
            EmbeddingService, 'generate_embedding', return_value=[0.5, 0.5]
        ) as unitario:
            EmbeddingService.generate_embeddings_batch(['a', 'b'], cliente)
        self.assertEqual(unitario.call_count, 2)

    def test_los_textos_vacios_no_gastan_llamada(self):
        cliente = self.ClienteFalso()
        vectores = EmbeddingService.generate_embeddings_batch(['', '   '], cliente)
        self.assertEqual(cliente.llamadas, [])
        self.assertEqual(vectores, [None, None])

    def test_lista_vacia(self):
        cliente = self.ClienteFalso()
        self.assertEqual(EmbeddingService.generate_embeddings_batch([], cliente), [])
        self.assertEqual(cliente.llamadas, [])

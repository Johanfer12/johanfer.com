import numpy as np
from django.test import TestCase
from django.utils import timezone

from .interest import (
    MIN_LABELS_PER_CLASS,
    InterestModel,
    pack_vector,
    unpack_vector,
)
from .models import FeedSource, News, NewsFeedback


def make_vector(seed, dim=32):
    rng = np.random.default_rng(seed)
    return rng.normal(size=dim).astype(np.float32)


class VectorPackingTests(TestCase):
    def test_pack_normaliza_y_conserva_direccion(self):
        original = np.array([3.0, 4.0], dtype=np.float32)
        restored = unpack_vector(pack_vector(original))

        self.assertAlmostEqual(float(np.linalg.norm(restored)), 1.0, places=5)
        np.testing.assert_allclose(restored, [0.6, 0.8], atol=1e-6)

    def test_pack_de_vacio_o_none_devuelve_none(self):
        self.assertIsNone(pack_vector(None))
        self.assertIsNone(pack_vector([]))
        self.assertIsNone(unpack_vector(None))
        self.assertIsNone(unpack_vector(b""))


class InterestModelTests(TestCase):
    def setUp(self):
        self.source = FeedSource.objects.create(name="Fuente", url="https://example.com/rss")
        self.counter = 0

    def add_label(self, vote, vector):
        self.counter += 1
        NewsFeedback.objects.create(
            guid=f"guid-{self.counter}",
            title=f"Titular {self.counter}",
            vote=vote,
            vector=pack_vector(vector),
        )

    def seed_two_clusters(self, n=MIN_LABELS_PER_CLASS):
        """Dos temas bien separados: uno votado a favor y otro en contra."""
        liked = make_vector(1)
        disliked = make_vector(2)
        for i in range(n):
            self.add_label(1, liked + 0.01 * make_vector(100 + i))
            self.add_label(-1, disliked + 0.01 * make_vector(200 + i))
        return liked, disliked

    def test_sin_etiquetas_suficientes_no_puntua(self):
        for i in range(MIN_LABELS_PER_CLASS - 1):
            self.add_label(1, make_vector(i))
            self.add_label(-1, make_vector(50 + i))

        model = InterestModel.load()
        self.assertFalse(model.is_trained)
        self.assertIsNone(model.score(make_vector(999)))

    def test_puntua_positivo_lo_parecido_a_lo_votado_arriba(self):
        liked, disliked = self.seed_two_clusters()
        model = InterestModel.load()

        self.assertTrue(model.is_trained)
        self.assertGreater(model.score(liked), 0)
        self.assertLess(model.score(disliked), 0)

    def test_score_acotado_en_menos_uno_uno(self):
        liked, _ = self.seed_two_clusters()
        score = InterestModel.load().score(liked)
        self.assertGreaterEqual(score, -1.0)
        self.assertLessEqual(score, 1.0)

    def test_vectores_de_otra_dimension_se_ignoran(self):
        self.seed_two_clusters()
        # Simula un cambio de modelo de embeddings: la etiqueta vieja no debe
        # tumbar la carga del resto.
        self.add_label(1, make_vector(7, dim=16))

        model = InterestModel.load()
        self.assertTrue(model.is_trained)
        self.assertIsNotNone(model.score(make_vector(1)))

    def test_score_ignora_vector_de_dimension_incorrecta(self):
        self.seed_two_clusters()
        model = InterestModel.load()
        self.assertIsNone(model.score(make_vector(3, dim=8)))


class RecordVoteTests(TestCase):
    def setUp(self):
        self.source = FeedSource.objects.create(name="Fuente", url="https://example.com/rss")
        self.news = News.objects.create(
            guid="guid-noticia",
            title="Una noticia",
            description="Cuerpo",
            link="https://example.com/1",
            published_date=timezone.now(),
            source=self.source,
        )
        self.news._embedding_vector = make_vector(42).tolist()

    def test_voto_crea_etiqueta_y_desnormaliza_en_la_noticia(self):
        from .interest import record_vote

        record_vote(self.news, 1)

        self.news.refresh_from_db()
        self.assertEqual(self.news.user_vote, 1)
        self.assertEqual(NewsFeedback.objects.filter(guid="guid-noticia", vote=1).count(), 1)

    def test_cambiar_de_voto_no_duplica_la_etiqueta(self):
        from .interest import record_vote

        record_vote(self.news, 1)
        record_vote(self.news, -1)

        self.news.refresh_from_db()
        self.assertEqual(self.news.user_vote, -1)
        self.assertEqual(NewsFeedback.objects.filter(guid="guid-noticia").count(), 1)
        self.assertEqual(NewsFeedback.objects.get(guid="guid-noticia").vote, -1)

    def test_voto_cero_retira_la_etiqueta(self):
        from .interest import record_vote

        record_vote(self.news, 1)
        record_vote(self.news, 0)

        self.news.refresh_from_db()
        self.assertEqual(self.news.user_vote, 0)
        self.assertFalse(NewsFeedback.objects.filter(guid="guid-noticia").exists())

    def test_la_etiqueta_sobrevive_al_borrado_de_la_noticia(self):
        from .interest import record_vote

        record_vote(self.news, -1)
        self.news.delete()

        feedback = NewsFeedback.objects.get(guid="guid-noticia")
        self.assertIsNone(feedback.news_id)
        self.assertEqual(feedback.vote, -1)
        self.assertEqual(feedback.title, "Una noticia")


class PercentileTests(TestCase):
    """El percentil es lo único estable: el score crudo mueve su origen."""

    def setUp(self):
        from django.core.cache import cache

        cache.clear()
        self.source = FeedSource.objects.create(name="Fuente", url="https://example.com/rss")

    def make_scored(self, scores):
        for i, score in enumerate(scores):
            News.objects.create(
                guid=f"guid-p{i}",
                title=f"Noticia {i}",
                description="Cuerpo",
                link=f"https://example.com/p{i}",
                published_date=timezone.now(),
                source=self.source,
                is_ai_processed=True,
                interest_score=score,
            )

    def test_sin_suficientes_noticias_no_hay_percentil(self):
        from .interest import percentile_of

        self.make_scored([0.01 * i for i in range(5)])
        self.assertIsNone(percentile_of(0.02))

    def test_situa_cada_noticia_en_su_posicion(self):
        from .interest import percentile_of

        scores = [i / 100 for i in range(20)]
        self.make_scored(scores)

        self.assertGreater(percentile_of(0.19), percentile_of(0.10))
        self.assertGreater(percentile_of(0.10), percentile_of(0.00))
        # Ni la mejor sale 100% ni la peor 0%: el modelo no da para esa certeza.
        self.assertLess(percentile_of(0.19), 100)
        self.assertGreater(percentile_of(0.00), 0)

    def test_el_percentil_no_depende_del_signo_del_score(self):
        """Mismo orden desplazado: los percentiles deben ser los mismos."""
        from django.core.cache import cache

        from .interest import percentile_of

        scores = [i / 100 for i in range(20)]
        self.make_scored(scores)
        antes = [percentile_of(s) for s in scores]

        # Se desplaza todo el rango a negativo, como pasa al acumular votos
        # en contra, sin cambiar el orden relativo.
        for news in News.objects.all():
            news.interest_score -= 0.5
            news.save(update_fields=["interest_score"])
        cache.clear()

        despues = [percentile_of(s - 0.5) for s in scores]
        self.assertEqual(antes, despues)

    def test_sin_score_no_hay_percentil(self):
        from .interest import percentile_of

        self.make_scored([i / 100 for i in range(20)])
        self.assertIsNone(percentile_of(None))


class ModelVersionTests(TestCase):
    def add_label(self, idx, vote, vector, model_version):
        NewsFeedback.objects.create(
            guid=f"guid-mv{idx}",
            title=f"Titular {idx}",
            vote=vote,
            vector=pack_vector(vector),
            model_version=model_version,
        )

    def test_ignora_etiquetas_de_otro_modelo(self):
        from .interest import current_model_version

        actual = current_model_version()
        for i in range(MIN_LABELS_PER_CLASS):
            self.add_label(i, 1, make_vector(i), actual)
            self.add_label(100 + i, -1, make_vector(100 + i), actual)
        # Etiquetas de un modelo distinto con la MISMA dimension: el guardarrail
        # de dimensiones no las vería, solo las caza el model_version.
        for i in range(20):
            self.add_label(200 + i, 1, make_vector(200 + i), "otro-modelo-v2")

        model = InterestModel.load()
        self.assertEqual(model.label_counts, (MIN_LABELS_PER_CLASS, MIN_LABELS_PER_CLASS))

    def test_las_etiquetas_sin_marcar_se_dan_por_buenas(self):
        for i in range(MIN_LABELS_PER_CLASS):
            self.add_label(i, 1, make_vector(i), "")
            self.add_label(100 + i, -1, make_vector(100 + i), "")

        model = InterestModel.load()
        self.assertEqual(model.label_counts, (MIN_LABELS_PER_CLASS, MIN_LABELS_PER_CLASS))

    def test_el_voto_guarda_el_modelo_usado(self):
        from .interest import current_model_version, record_vote

        source = FeedSource.objects.create(name="F", url="https://example.com/f")
        news = News.objects.create(
            guid="guid-voto-mv",
            title="Una noticia",
            description="Cuerpo",
            link="https://example.com/mv",
            published_date=timezone.now(),
            source=source,
        )
        news._embedding_vector = make_vector(7).tolist()
        record_vote(news, 1)

        self.assertEqual(
            NewsFeedback.objects.get(guid="guid-voto-mv").model_version,
            current_model_version(),
        )


class DistributionWindowTests(TestCase):
    """La referencia del percentil no puede depender de lo que ya has leído."""

    def setUp(self):
        from django.core.cache import cache

        cache.clear()
        self.source = FeedSource.objects.create(name="Fuente", url="https://example.com/rss")

    def make(self, idx, score, **kwargs):
        defaults = {
            "guid": f"guid-w{idx}",
            "title": f"Noticia {idx}",
            "description": "Cuerpo",
            "link": f"https://example.com/w{idx}",
            "published_date": timezone.now(),
            "source": self.source,
            "is_ai_processed": True,
            "interest_score": score,
        }
        defaults.update(kwargs)
        return News.objects.create(**defaults)

    def test_las_leidas_siguen_contando_en_la_distribucion(self):
        from django.core.cache import cache

        from .interest import interest_distribution, percentile_of

        for i in range(20):
            self.make(i, i / 100)
        antes = [percentile_of(i / 100) for i in range(20)]
        self.assertEqual(len(interest_distribution()), 20)

        # Se leen (borran) casi todas: el percentil de las que quedan no debe
        # moverse, porque la referencia es la ventana, no lo pendiente.
        News.objects.filter(interest_score__lt=0.15).update(is_deleted=True)
        cache.clear()

        self.assertEqual(len(interest_distribution()), 20)
        self.assertEqual(antes, [percentile_of(i / 100) for i in range(20)])

    def test_fuera_de_la_ventana_no_cuenta(self):
        from datetime import timedelta

        from .interest import INTEREST_WINDOW_DAYS, interest_distribution

        for i in range(12):
            self.make(i, i / 100)
        for i in range(12, 20):
            self.make(
                i,
                i / 100,
                published_date=timezone.now() - timedelta(days=INTEREST_WINDOW_DAYS + 1),
            )

        self.assertEqual(len(interest_distribution()), 12)

    def test_las_filtradas_no_entran_en_la_referencia(self):
        from .interest import interest_distribution

        for i in range(12):
            self.make(i, i / 100)
        self.make(90, 0.9, is_redundant=True)
        self.make(91, 0.9, is_ai_filtered=True)
        self.make(92, 0.9, is_filtered=True)

        self.assertEqual(len(interest_distribution()), 12)

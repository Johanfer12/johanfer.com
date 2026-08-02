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

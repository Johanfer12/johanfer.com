"""Modelo de interés personal sobre los embeddings que ya genera el pipeline.

La idea: cada noticia ya tiene un vector de 768 dimensiones en Qdrant. Los
pulgares etiquetan algunos de esos vectores y, para una noticia nueva, basta
comparar su vector con los etiquetados para estimar si va a interesar.

Se usa kNN por clase (no una red neuronal ni una regresión entrenada) por tres
razones prácticas:

* No añade dependencias: numpy ya está instalado para la detección de
  redundancia.
* No hay paso de entrenamiento que mantener ni artefacto que versionar; cada
  voto cambia el resultado en la siguiente puntuación.
* Con pocos cientos de etiquetas un kNN sobre buenos embeddings rinde igual o
  mejor que un modelo con parámetros, y es trivial de explicar cuando da un
  resultado raro.

Coste en la Raspberry: la matriz de etiquetas son ``n × 768`` float32 (3 MB por
cada mil votos) y puntuar es un producto matriz-vector. Con 2.000 etiquetas son
~1,5 millones de multiplicaciones, del orden de milisegundos.

Qué cuenta como etiqueta y qué no
---------------------------------
Solo los pulgares. Nada más se usa como señal, y las dos alternativas que se
descartaron conviene dejarlas escritas para no volver sobre ellas:

* ``is_deleted`` NO es negativo. Aquí borrar significa "ya la leí", y es la forma
  de saber qué queda pendiente. Tomarlo por rechazo enseñaría al modelo justo lo
  contrario de lo que pasa, porque se borra precisamente lo que sí se ha leído.

* Vectorizar las palabras filtro tampoco aporta. Se midió: el vector de una
  palabra suelta sí distingue bien (las noticias sobre el tema suben a ~0.82 de
  similitud frente a ~0.73 de media), pero las noticias que penalizaría no llegan
  nunca al feed, porque la palabra filtro ya las bloqueó antes. Como negativos
  sumarían casi una constante a todo, no capacidad de discriminar.
"""

import logging

import numpy as np

logger = logging.getLogger(__name__)

# Vecinos considerados por clase. Bajo para que un tema muy concreto pese, pero
# no tanto como para que un único voto atípico domine la puntuación.
NEIGHBORS = 10

# Por debajo de esto el modelo se declara no entrenado y no puntúa nada: con
# tres votos por clase cualquier score sería ruido con apariencia de dato.
MIN_LABELS_PER_CLASS = 5

VECTOR_DTYPE = np.float32


class VectorUnavailable(Exception):
    """No hay embedding disponible para etiquetar la noticia."""


def current_model_version():
    from django.conf import settings

    return getattr(settings, "GEMINI_EMBEDDING_MODEL", "gemini-embedding-001")


def pack_vector(vector):
    """Serializa un embedding a bytes float32 normalizados L2."""
    if vector is None:
        return None
    arr = np.asarray(vector, dtype=VECTOR_DTYPE).ravel()
    if arr.size == 0:
        return None
    norm = np.linalg.norm(arr)
    if norm > 0:
        arr = arr / norm
    return arr.astype(VECTOR_DTYPE).tobytes()


def unpack_vector(blob):
    """Deserializa bytes float32 a un array numpy, o None si no es utilizable."""
    if not blob:
        return None
    # SQLite devuelve memoryview según el backend; np.frombuffer acepta ambos.
    arr = np.frombuffer(bytes(blob), dtype=VECTOR_DTYPE)
    return arr if arr.size else None


class InterestModel:
    """Puntuador kNN sobre las etiquetas de NewsFeedback."""

    def __init__(self, positives, negatives):
        self.positives = positives
        self.negatives = negatives

    @property
    def is_trained(self):
        return (
            self.positives is not None
            and self.negatives is not None
            and len(self.positives) >= MIN_LABELS_PER_CLASS
            and len(self.negatives) >= MIN_LABELS_PER_CLASS
        )

    @property
    def label_counts(self):
        return (
            0 if self.positives is None else len(self.positives),
            0 if self.negatives is None else len(self.negatives),
        )

    @classmethod
    def load(cls):
        """Construye el modelo desde la base de datos. Nunca lanza excepción."""
        from .models import NewsFeedback

        actual = current_model_version()
        try:
            rows = NewsFeedback.objects.values_list("vote", "vector", "model_version")
        except Exception:
            logger.exception("No se pudieron leer las etiquetas de interés")
            return cls(None, None)

        labelled = []
        dim_counts = {}
        descartadas_por_modelo = 0
        for vote, blob, model_version in rows.iterator(chunk_size=500):
            # Un vector de otro modelo de embeddings no es comparable con los
            # actuales aunque tenga el mismo número de dimensiones. Las etiquetas
            # antiguas sin marcar se dan por buenas: son de antes de que existiera
            # el campo, y por tanto del modelo de entonces, que es el de ahora.
            if model_version and model_version != actual:
                descartadas_por_modelo += 1
                continue
            arr = unpack_vector(blob)
            if arr is None:
                continue
            labelled.append((vote, arr))
            dim_counts[arr.size] = dim_counts.get(arr.size, 0) + 1

        if descartadas_por_modelo:
            logger.warning(
                "Ignoradas %s etiquetas de interés generadas con otro modelo de "
                "embeddings (el actual es %s). Recupéralas con reembed_interest_labels.",
                descartadas_por_modelo,
                actual,
            )

        if not labelled:
            return cls(None, None)

        # Un cambio de modelo de embeddings deja etiquetas de otra dimensión
        # conviviendo con las nuevas. Se conserva la dimensión mayoritaria: fijar
        # la de la primera fila dejaría que un único vector viejo invalidase todo
        # el histórico.
        expected_dim = max(dim_counts.items(), key=lambda item: item[1])[0]
        discarded = len(labelled) - dim_counts[expected_dim]
        if discarded:
            logger.warning(
                "Ignoradas %s etiquetas de interés con dimensión distinta de %s",
                discarded,
                expected_dim,
            )

        positives, negatives = [], []
        for vote, arr in labelled:
            if arr.size != expected_dim:
                continue
            (positives if vote > 0 else negatives).append(arr)

        return cls(
            np.vstack(positives) if positives else None,
            np.vstack(negatives) if negatives else None,
        )

    @staticmethod
    def _class_affinity(matrix, vector):
        """Media de similitud con los ``NEIGHBORS`` vecinos más próximos."""
        sims = matrix @ vector
        k = min(NEIGHBORS, sims.size)
        if k < sims.size:
            # argpartition evita ordenar el vector entero.
            sims = sims[np.argpartition(-sims, k - 1)[:k]]
        return float(np.mean(sims))

    def score(self, vector):
        """Devuelve un score en [-1, 1], o None si el modelo aún no da para tanto.

        Positivo = se parece más a lo que te gustó que a lo que descartaste.
        """
        if not self.is_trained:
            return None

        arr = np.asarray(vector, dtype=VECTOR_DTYPE).ravel()
        if arr.size != self.positives.shape[1]:
            return None
        norm = np.linalg.norm(arr)
        if norm == 0:
            return None
        arr = arr / norm

        score = self._class_affinity(self.positives, arr) - self._class_affinity(
            self.negatives, arr
        )
        return float(np.clip(score, -1.0, 1.0))


# El score crudo no es comparable en el tiempo: es una resta de similitudes cuyo
# origen se desplaza según cuántas etiquetas haya de cada clase (medido: con 4
# positivos y 4 negativos todo sale por encima de cero; con 4 y 21, por debajo).
# Lo único estable es la posición relativa dentro del feed, que es lo que se
# enseña. Por eso tampoco puede haber un umbral fijo que oculte noticias.
INTEREST_DISTRIBUTION_CACHE_KEY = "news:interest:distribution"
INTEREST_DISTRIBUTION_TTL = 30


def interest_distribution():
    """Scores del feed visible, ordenados, para situar cada noticia."""
    from django.core.cache import cache

    from .models import News

    cached = cache.get(INTEREST_DISTRIBUTION_CACHE_KEY)
    if cached is not None:
        return cached

    scores = sorted(
        News.visible.exclude(interest_score=None).values_list("interest_score", flat=True)
    )
    cache.set(INTEREST_DISTRIBUTION_CACHE_KEY, scores, INTEREST_DISTRIBUTION_TTL)
    return scores


def percentile_of(score, distribution=None):
    """Porcentaje del feed que queda por debajo de ``score``.

    Devuelve None si no hay score o si hay tan pocas noticias puntuadas que el
    percentil no significaría nada.
    """
    import bisect

    if score is None:
        return None

    if distribution is None:
        distribution = interest_distribution()

    total = len(distribution)
    if total < 10:
        return None

    # El punto medio del rango de empates evita que la mejor noticia salga 100%
    # y la peor 0%, que se leerían como certezas que el modelo no tiene.
    izquierda = bisect.bisect_left(distribution, score)
    derecha = bisect.bisect_right(distribution, score)
    posicion = (izquierda + derecha) / 2
    return int(round(100 * posicion / total))


def resolve_vector(news, *, allow_generation=True):
    """Obtiene el embedding de una noticia sin recalcularlo si ya existe.

    Prioridad: vector ya cargado en memoria > Qdrant > generarlo con Gemini.
    Devuelve None si no hay forma de conseguirlo.
    """
    cached = getattr(news, "_embedding_vector", None)
    if cached:
        return cached

    from .services import EmbeddingService, FeedService

    vector_index = FeedService.initialize_vector_index()
    if vector_index is not None and news.guid:
        try:
            vector = vector_index.get_vector(news.guid)
            if vector:
                news._embedding_vector = vector
                return vector
        except Exception:
            logger.exception("Error recuperando vector de Qdrant para %s", news.guid[:80])

    if not allow_generation:
        return None

    try:
        client = FeedService.initialize_gemini()
    except Exception:
        logger.exception("Sin cliente Gemini para generar el embedding del voto")
        return None

    text = f"{news.title} {news.description or ''}"
    vector = EmbeddingService.generate_embedding(text, client)
    if vector:
        news._embedding_vector = vector
    return vector


def record_vote(news, vote):
    """Registra (o retira) el voto de una noticia y persiste su etiqueta.

    ``vote`` es 1, -1 o 0 para deshacer. Devuelve el voto efectivo aplicado.
    """
    from .models import NewsFeedback

    vote = int(vote)
    if vote not in (1, -1, 0):
        raise ValueError(f"Voto no válido: {vote}")

    if vote == 0:
        NewsFeedback.objects.filter(guid=news.guid).delete()
    else:
        vector = resolve_vector(news)
        packed = pack_vector(vector)
        if packed is None:
            raise VectorUnavailable(
                "No se pudo obtener el embedding de la noticia; el voto no se guardaría."
            )
        NewsFeedback.objects.update_or_create(
            guid=news.guid,
            defaults={
                "news": news,
                # Copia del titular para poder auditar el voto en el admin
                # cuando la purga ya se haya llevado la noticia por delante, y
                # para regenerar el vector si se cambia de modelo.
                "title": news.title[:500],
                "vote": vote,
                "vector": packed,
                "model_version": current_model_version(),
            },
        )

    news.user_vote = vote
    news.save(update_fields=["user_vote"])
    return vote


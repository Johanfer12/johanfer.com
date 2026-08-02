"""Recalcula ``interest_score`` para las noticias que ya están en la base.

El pipeline puntúa cada noticia al ingerirla, así que esto solo hace falta tras
una tanda grande de votos, o si se quiere ver el efecto de un cambio en el
scoring sin esperar al siguiente cron.
"""

from django.core.cache import cache
from django.core.management.base import BaseCommand

from my_news.interest import INTEREST_DISTRIBUTION_CACHE_KEY, InterestModel
from my_news.models import News
from my_news.services import FeedService


class Command(BaseCommand):
    help = "Recalcula la puntuación de interés de las noticias existentes."

    def add_arguments(self, parser):
        parser.add_argument(
            "--limit",
            type=int,
            default=0,
            help="Máximo de noticias a procesar (0 = todas las visibles).",
        )

    def handle(self, *args, **options):
        model = InterestModel.load()
        positives, negatives = model.label_counts
        if not model.is_trained:
            self.stderr.write(
                self.style.WARNING(
                    f"Modelo sin datos suficientes ({positives} a favor / {negatives} en contra). "
                    "Hacen falta al menos 5 votos de cada signo; vota en el feed."
                )
            )
            return

        vector_index = FeedService.initialize_vector_index()
        if vector_index is None:
            self.stderr.write(self.style.ERROR("Qdrant no está disponible; no hay vectores que leer."))
            return

        self.stdout.write(f"Modelo cargado: {positives} a favor / {negatives} en contra")

        queryset = News.visible.all().order_by("-published_date")
        limit = options["limit"]
        if limit > 0:
            queryset = queryset[:limit]

        scored = 0
        missing_vector = 0
        # Se acumulan las filas y se escriben en lotes: en SQLite un UPDATE por
        # noticia sería el cuello de botella, no el cálculo.
        pending = []
        for news in queryset.iterator(chunk_size=200):
            try:
                vector = vector_index.get_vector(news.guid)
            except Exception:
                vector = None

            if not vector:
                missing_vector += 1
                continue

            news.interest_score = model.score(vector)
            pending.append(news)
            scored += 1

            if len(pending) >= 200:
                News.objects.bulk_update(pending, ["interest_score"])
                pending = []

        if pending:
            News.objects.bulk_update(pending, ["interest_score"])

        # Los percentiles se calculan sobre una distribución cacheada; sin esto
        # el feed seguiría situando las noticias con los scores viejos.
        cache.delete(INTEREST_DISTRIBUTION_CACHE_KEY)

        self.stdout.write(self.style.SUCCESS(f"Noticias puntuadas: {scored}"))
        if missing_vector:
            self.stdout.write(f"Sin vector en Qdrant (omitidas): {missing_vector}")

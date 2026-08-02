"""Regenera los vectores de las etiquetas tras cambiar de modelo de embeddings.

Sin esto, cambiar ``GEMINI_EMBEDDING_MODEL`` tira por la borda todo lo aprendido:
los vectores viejos dejan de ser comparables con los nuevos y ``InterestModel``
los ignora. Como ``NewsFeedback`` guarda el titular, se pueden volver a generar
aunque la noticia original ya la haya barrido la purga quincenal.

El titular solo no es exactamente el texto que se vectorizó al votar (aquel
incluía la descripción), así que el vector regenerado no es idéntico al que
había. Para el kNN es suficiente: el tema, que es lo que importa, se conserva.
"""

from django.core.management.base import BaseCommand

from my_news.interest import current_model_version, pack_vector
from my_news.models import NewsFeedback
from my_news.services import EmbeddingService, FeedService


class Command(BaseCommand):
    help = "Regenera los embeddings de las etiquetas de interés desactualizadas."

    def add_arguments(self, parser):
        parser.add_argument(
            "--limit",
            type=int,
            default=100,
            help="Máximo de etiquetas a regenerar (1 llamada a Gemini cada una).",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Solo informa de cuántas están desactualizadas.",
        )

    def handle(self, *args, **options):
        actual = current_model_version()
        # Las vacías son anteriores al campo: se dan por buenas y solo se marcan.
        legacy = NewsFeedback.objects.filter(model_version="")
        desfasadas = NewsFeedback.objects.exclude(model_version=actual).exclude(
            model_version=""
        )

        self.stdout.write(f"Modelo actual: {actual}")
        self.stdout.write(f"  etiquetas sin marcar (se asumen del modelo actual): {legacy.count()}")
        self.stdout.write(f"  etiquetas de otro modelo (hay que regenerar): {desfasadas.count()}")

        if options["dry_run"]:
            return

        marcadas = legacy.update(model_version=actual)
        if marcadas:
            self.stdout.write(f"Marcadas como {actual}: {marcadas}")

        pendientes = list(desfasadas[: options["limit"]])
        if not pendientes:
            self.stdout.write(self.style.SUCCESS("No hay nada que regenerar."))
            return

        client = FeedService.initialize_gemini()
        regeneradas = 0
        fallidas = 0
        for etiqueta in pendientes:
            vector = EmbeddingService.generate_embedding(etiqueta.title, client)
            packed = pack_vector(vector)
            if packed is None:
                fallidas += 1
                self.stderr.write(f"  sin embedding: {etiqueta.title[:60]}")
                continue
            etiqueta.vector = packed
            etiqueta.model_version = actual
            etiqueta.save(update_fields=["vector", "model_version"])
            regeneradas += 1

        self.stdout.write(self.style.SUCCESS(f"Regeneradas: {regeneradas}"))
        if fallidas:
            self.stdout.write(self.style.WARNING(f"Fallidas (reintenta): {fallidas}"))
        restantes = (
            NewsFeedback.objects.exclude(model_version=actual).exclude(model_version="").count()
        )
        if restantes:
            self.stdout.write(f"Quedan pendientes: {restantes}. Vuelve a ejecutar el comando.")

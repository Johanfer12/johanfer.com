"""Siembra el modelo de interés con las señales implícitas que ya hay en la BD.

Guardar una noticia equivale a un pulgar arriba y eliminarla a uno abajo, así que
el arranque en frío se resuelve solo: no hace falta votar cientos de noticias a
mano antes de que el score sirva para algo.

Solo se siembran las noticias cuyo vector siga en Qdrant (las de los últimos ~15
días más todas las guardadas). No se regeneran embeddings: sería una llamada a
Gemini por noticia y el objetivo es que esto salga gratis.
"""

from django.core.management.base import BaseCommand

from my_news.interest import pack_vector
from my_news.models import News, NewsFeedback
from my_news.services import FeedService


class Command(BaseCommand):
    help = "Crea etiquetas de interés a partir de las noticias guardadas (a favor) y eliminadas (en contra)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Muestra lo que se haría sin escribir nada.",
        )
        parser.add_argument(
            "--overwrite",
            action="store_true",
            help="Reescribe también las etiquetas que ya existan.",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        overwrite = options["overwrite"]

        vector_index = FeedService.initialize_vector_index()
        if vector_index is None:
            self.stderr.write(self.style.ERROR("Qdrant no está disponible; no hay vectores que leer."))
            return

        existing_guids = set() if overwrite else set(
            NewsFeedback.objects.values_list("guid", flat=True)
        )

        created = 0
        skipped_existing = 0
        missing_vector = 0

        for vote, queryset in (
            (1, News.objects.filter(is_saved=True)),
            # Una noticia guardada y luego eliminada cuenta como positiva: el
            # guardado es una señal más deliberada que el descarte.
            (-1, News.objects.filter(is_deleted=True, is_saved=False)),
        ):
            for news in queryset.iterator(chunk_size=200):
                if news.guid in existing_guids:
                    skipped_existing += 1
                    continue

                try:
                    vector = vector_index.get_vector(news.guid)
                except Exception:
                    vector = None

                packed = pack_vector(vector)
                if packed is None:
                    missing_vector += 1
                    continue

                if not dry_run:
                    NewsFeedback.objects.update_or_create(
                        guid=news.guid,
                        defaults={
                            "news": news,
                            "title": news.title[:500],
                            "vote": vote,
                            "vector": packed,
                        },
                    )
                    News.objects.filter(pk=news.pk).update(user_vote=vote)
                created += 1

        prefix = "[dry-run] " if dry_run else ""
        self.stdout.write(self.style.SUCCESS(f"{prefix}Etiquetas creadas: {created}"))
        self.stdout.write(f"{prefix}Ya existían (sin tocar): {skipped_existing}")
        self.stdout.write(f"{prefix}Sin vector en Qdrant (omitidas): {missing_vector}")

        positives = NewsFeedback.objects.filter(vote=1).count()
        negatives = NewsFeedback.objects.filter(vote=-1).count()
        self.stdout.write(f"{prefix}Total en el modelo: {positives} a favor / {negatives} en contra")

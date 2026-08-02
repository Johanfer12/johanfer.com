"""Siembra el modelo de interés con negativos sacados de las palabras filtro.

Por qué NO se usan las noticias eliminadas: borrar una noticia aquí significa
"ya la leí", no "no me interesa". Es la forma de saber qué queda por leer, así
que tomarlo como voto en contra enseñaría al modelo justo lo contrario de lo que
pasa (se borra precisamente lo que sí se ha leído).

Lo que sí es una señal deliberada de rechazo son las palabras filtro: cada una
la escribió el usuario para no volver a ver ese tema. Convertir las noticias que
cazaron en etiquetas negativas le enseña al modelo el *vecindario semántico* de
esos temas, que es más de lo que puede hacer la palabra literal: la regla dura
solo caza la cadena exacta, el vector caza el tema aunque no aparezca la palabra.

Coste: el filtro por palabra corta el pipeline antes de generar el embedding, así
que estas noticias no tienen vector en Qdrant y hay que pedirlo a Gemini, una
llamada por noticia. De ahí que exista ``--limit``.

Los positivos no se pueden sembrar: no hay ninguna señal existente que signifique
"esto me interesa" sin ambigüedad. Salen de los pulgares arriba, votando.
"""

from django.core.management.base import BaseCommand

from my_news.interest import MIN_LABELS_PER_CLASS, pack_vector, resolve_vector
from my_news.models import News, NewsFeedback


class Command(BaseCommand):
    help = (
        "Crea etiquetas negativas a partir de las noticias que cazaron las palabras filtro. "
        "Los positivos salen de votar con el pulgar arriba."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Muestra lo que se haría sin escribir nada ni pedir embeddings.",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=150,
            help="Máximo de embeddings a generar en esta pasada (1 llamada a Gemini cada uno).",
        )
        parser.add_argument(
            "--include-ai-filtered",
            action="store_true",
            help=(
                "Incluye también las filtradas por las instrucciones de IA. Son gratis "
                "(ya tienen vector en Qdrant) pero el criterio es de la IA, no tuyo."
            ),
        )
        parser.add_argument(
            "--include-saved",
            action="store_true",
            help="Trata las noticias guardadas como pulgar arriba, para arrancar con positivos.",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        limit = options["limit"]

        existing_guids = set(NewsFeedback.objects.values_list("guid", flat=True))

        sources = [("palabra filtro", -1, News.objects.filter(filtered_by__isnull=False))]
        if options["include_ai_filtered"]:
            sources.append(("filtro IA", -1, News.objects.filter(is_ai_filtered=True)))
        if options["include_saved"]:
            sources.append(("guardadas", 1, News.objects.filter(is_saved=True)))

        created = 0
        skipped_existing = 0
        no_vector = 0
        budget_left = limit

        for label, vote, queryset in sources:
            batch_created = 0
            for news in queryset.iterator(chunk_size=200):
                if news.guid in existing_guids:
                    skipped_existing += 1
                    continue

                if budget_left <= 0:
                    break

                if dry_run:
                    batch_created += 1
                    budget_left -= 1
                    continue

                try:
                    # Las filtradas por palabra no pasaron por el indexador, así
                    # que casi siempre habrá que generar el embedding.
                    packed = pack_vector(resolve_vector(news))
                except Exception:
                    packed = None

                if packed is None:
                    no_vector += 1
                    continue

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
                existing_guids.add(news.guid)
                batch_created += 1
                budget_left -= 1

            created += batch_created
            self.stdout.write(f"  {label}: {batch_created} etiquetas")

        prefix = "[dry-run] " if dry_run else ""
        self.stdout.write(self.style.SUCCESS(f"{prefix}Etiquetas creadas: {created}"))
        if skipped_existing:
            self.stdout.write(f"{prefix}Ya existían (sin tocar): {skipped_existing}")
        if no_vector:
            self.stdout.write(f"{prefix}Sin embedding disponible (omitidas): {no_vector}")
        if budget_left <= 0:
            self.stdout.write(
                self.style.WARNING(
                    f"{prefix}Se agotó el presupuesto de {limit} embeddings; quedan noticias "
                    "sin etiquetar. Vuelve a ejecutar el comando para continuar."
                )
            )

        positives = NewsFeedback.objects.filter(vote=1).count()
        negatives = NewsFeedback.objects.filter(vote=-1).count()
        self.stdout.write(f"{prefix}Total en el modelo: {positives} a favor / {negatives} en contra")
        if positives < MIN_LABELS_PER_CLASS:
            self.stdout.write(
                self.style.WARNING(
                    f"{prefix}Faltan positivos: el modelo no puntúa hasta tener "
                    f"{MIN_LABELS_PER_CLASS} de cada clase. Vota con el pulgar arriba en el feed."
                )
            )

"""Recalcula ``interest_score`` para las noticias visibles.

El cron ya lo hace al final de cada pasada, así que esto solo hace falta para
forzarlo en el momento: tras una tanda de votos, o para ver el efecto de un
cambio en el scoring sin esperar a la media hora.

La lógica vive en ``tasks.rescore_visible_news`` para que el comando y el cron
no puedan divergir.
"""

from django.core.management.base import BaseCommand

from my_news.interest import InterestModel
from my_news.tasks import rescore_visible_news


class Command(BaseCommand):
    help = "Recalcula la puntuación de interés de las noticias visibles."

    def add_arguments(self, parser):
        parser.add_argument(
            "--limit",
            type=int,
            default=0,
            help="Máximo de noticias a procesar (0 = todas las visibles).",
        )

    def handle(self, *args, **options):
        modelo = InterestModel.load()
        positivos, negativos = modelo.label_counts
        if not modelo.is_trained:
            self.stderr.write(
                self.style.WARNING(
                    f"Modelo sin datos suficientes ({positivos} a favor / {negativos} en contra). "
                    "Hacen falta al menos 5 votos de cada signo; vota en el feed."
                )
            )
            return

        self.stdout.write(f"Modelo cargado: {positivos} a favor / {negativos} en contra")
        puntuadas = rescore_visible_news(limit=options["limit"])
        self.stdout.write(self.style.SUCCESS(f"Noticias puntuadas: {puntuadas}"))

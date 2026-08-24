"""Indexa en Qdrant las noticias recientes que no tengan vector.

    python manage.py qdrant_backfill                  # tandas de 25 hasta agotar
    python manage.py qdrant_backfill --days 30
    python manage.py qdrant_backfill --limit 50 --passes 4

Hace falta sobre todo si se pierde el storage de Qdrant: los vectores se pueden
regenerar desde las noticias, a costa de una llamada a Gemini por cada una.

La lógica es la de ``tasks.retry_missing_embeddings``, que es la misma que corre
el cron al cerrar cada pasada. Este comando solo la repite por tandas. Antes
tenía su propia copia, y era peor: reindexaba también lo que ya estaba en
Qdrant —gastando una llamada a Gemini por noticia— y armaba el payload a mano en
vez de usar ``FeedService.build_vector_payload``, así que podía quedar
desalineado con lo que escribe la ingesta.

``--limit`` es el tamaño de tanda, no el total: acota las llamadas a Gemini de
cada pasada. Se para cuando una tanda no recupera nada.
"""

from django.core.management.base import BaseCommand

from my_news.tasks import retry_missing_embeddings


class Command(BaseCommand):
    help = "Genera e indexa en Qdrant los embeddings que falten de los últimos N días."

    def add_arguments(self, parser):
        parser.add_argument(
            "--days",
            type=int,
            default=15,
            help="Ventana de noticias a revisar (por defecto 15, los que conserva la purga).",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=25,
            help="Noticias por tanda (por defecto 25).",
        )
        parser.add_argument(
            "--passes",
            type=int,
            default=20,
            help="Tope de tandas, por si algo falla siempre (por defecto 20).",
        )

    def handle(self, *args, **options):
        days = options["days"]
        limit = options["limit"]
        passes = options["passes"]

        total = 0
        for numero in range(1, passes + 1):
            recuperadas = retry_missing_embeddings(limit=limit, days=days)
            total += recuperadas
            self.stdout.write(f"Tanda {numero}: {recuperadas} indexadas (acumulado {total})")
            if recuperadas == 0:
                break
        else:
            self.stdout.write(self.style.WARNING(
                f"Se alcanzó el tope de {passes} tandas; puede quedar trabajo pendiente."
            ))

        self.stdout.write(self.style.SUCCESS(f"Indexadas {total} noticias que no tenían vector."))

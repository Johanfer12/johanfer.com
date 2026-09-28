"""Lanza una pasada de ingesta de noticias, la misma que hace el cron.

La usa el botón de actualizar del feed, que la arranca en segundo plano en vez
de esperarla dentro de la petición: una pasada tarda de uno a cinco minutos y
nginx corta a los 60 s. Toma el mismo cerrojo que el cron, así que las dos no
se solapan.

    python manage.py update_news
"""

from django.core.management.base import BaseCommand

from my_news.tasks import update_news_cron


class Command(BaseCommand):
    help = "Ejecuta una pasada de ingesta de noticias (la misma que el cron)."

    def handle(self, *args, **options):
        update_news_cron()

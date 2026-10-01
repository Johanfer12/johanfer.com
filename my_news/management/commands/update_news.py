"""Lanza una pasada de ingesta de noticias.

La ejecutan el temporizador johanfer-news.timer (deploy/systemd/) y el botón de
actualizar del feed, que la arranca en segundo plano en vez de esperarla dentro
de la petición: una pasada tarda de uno a cinco minutos y nginx corta a los
60 s. Las dos toman el mismo cerrojo, así que no se solapan.

Si la pasada falla termina con código 1, para que systemd la marque como
fallida (`systemctl --failed`).

    python manage.py update_news
"""

from django.core.management.base import BaseCommand, CommandError

from my_news.tasks import update_news_cron


class Command(BaseCommand):
    help = "Ejecuta una pasada de ingesta de noticias."

    def handle(self, *args, **options):
        if not update_news_cron():
            raise CommandError("La pasada de noticias falló; el detalle está en el log.")

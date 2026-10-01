"""Sincroniza series y películas con Simkl.

La ejecuta el temporizador johanfer-watching.timer (deploy/systemd/) a las
00:30. Si falla termina con código 1, para que systemd la marque como fallida.
Los cortes de red ya los reintenta la propia tarea (NETWORK_RETRY_DELAYS), así
que la unidad no debe reintentar por su cuenta: repetiría peticiones a Simkl.

    python manage.py update_watching
"""

from django.core.management.base import BaseCommand, CommandError

from watching.tasks import update_watching_cron


class Command(BaseCommand):
    help = "Sincroniza series y películas con Simkl."

    def handle(self, *args, **options):
        if not update_watching_cron():
            raise CommandError("La sincronización con Simkl falló; el detalle está en el log.")

"""Sincroniza los libros con el RSS de Goodreads y borra las sesiones caducadas.

Lo segundo va aquí porque es la pasada diaria de esta app y no merece un
temporizador propio.

La ejecuta el temporizador johanfer-books.timer (deploy/systemd/) a medianoche.
Si falla termina con código 1, para que systemd la marque como fallida.

    python manage.py update_books
"""

from django.core.management.base import BaseCommand, CommandError

from home_page.tasks import clear_expired_sessions, update_books_cron


class Command(BaseCommand):
    help = "Sincroniza los libros con el RSS de Goodreads."

    def handle(self, *args, **options):
        clear_expired_sessions()
        if not update_books_cron():
            raise CommandError("La sincronización de libros falló; el detalle está en el log.")

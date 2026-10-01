"""Sincroniza los libros con el RSS de Goodreads.

La ejecuta el temporizador johanfer-books.timer (deploy/systemd/) a medianoche.
Si falla termina con código 1, para que systemd la marque como fallida.

    python manage.py update_books
"""

from django.core.management.base import BaseCommand, CommandError

from home_page.tasks import update_books_cron


class Command(BaseCommand):
    help = "Sincroniza los libros con el RSS de Goodreads."

    def handle(self, *args, **options):
        if not update_books_cron():
            raise CommandError("La sincronización de libros falló; el detalle está en el log.")

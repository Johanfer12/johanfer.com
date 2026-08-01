"""Renombra las carátulas de <trakt_id> a <tmdb_id>.

Los pósters se guardaban como show_<trakt_id>.webp / movie_<trakt_id>.webp. Al pasar la
fuente a Simkl la clave de agrupación es tmdb_id, así que hay que renombrarlos —
renombrar y no re-descargar, para no gastar ancho de banda ni pegarle a TMDB una vez
por obra.

    python manage.py rename_posters_to_tmdb            # simula
    python manage.py rename_posters_to_tmdb --apply    # ejecuta

Se renombra en dos fases (a un nombre temporal y de ahí al definitivo) porque los
espacios de ids se cruzan: una obra puede tener `trakt_id` 110492 mientras otra tiene
`tmdb_id` 110492, así que en una sola pasada el destino aparecería ocupado por un
póster que también está por renombrarse.

Idempotente: lo que ya está en su nombre final se deja quieto. Después de correrlo en
producción hay que purgar Cloudflare (o esperar el TTL de 30 días), porque cambian las
URLs.
"""

import os

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from watching.models import WatchedItem


class Command(BaseCommand):
    help = "Renombra los pósters de show_<trakt_id>.webp a show_<tmdb_id>.webp."

    def add_arguments(self, parser):
        parser.add_argument('--apply', action='store_true', help="Ejecuta de verdad.")

    def handle(self, *args, **options):
        folder = os.path.join(settings.MEDIA_ROOT, 'Posters')
        if not os.path.isdir(folder):
            raise CommandError(f"No existe {folder}")

        # Una fila por obra basta: todos los episodios de una serie comparten el póster.
        works = (
            WatchedItem.objects
            .exclude(trakt_id__isnull=True)
            .exclude(tmdb_id__isnull=True)
            .values_list('media_type', 'trakt_id', 'tmdb_id')
            .order_by()  # sin esto el Meta.ordering se cuela en el SELECT y distinct() no deduplica
            .distinct()
        )

        apply = options['apply']
        renamed = missing = already = shared = 0
        staged = {}  # nombre final -> nombre temporal ya ocupado

        # Fase 1: cada póster sale de su nombre viejo a un temporal derivado del destino.
        for media_type, trakt_id, tmdb_id in works:
            kind = 'show' if media_type == 'episode' else 'movie'
            old_name = f"{kind}_{trakt_id}.webp"
            new_name = f"{kind}_{tmdb_id}.webp"
            old_path = os.path.join(folder, old_name)
            new_path = os.path.join(folder, new_name)

            if old_name == new_name:
                already += 1
                continue
            if new_name in staged:
                # Dos obras distintas apuntando al mismo TMDB: se queda la primera.
                shared += 1
                self.stdout.write(f"  = {new_name} ya reclamado; {old_name} queda sin usar")
                continue
            if not os.path.exists(old_path):
                if os.path.exists(new_path):
                    already += 1
                else:
                    missing += 1
                    self.stdout.write(f"  ! falta {old_name} (tmdb {tmdb_id})")
                continue

            temp_path = f"{new_path}.rename-tmp"
            self.stdout.write(f"  {old_name}  ->  {new_name}")
            if apply:
                os.replace(old_path, temp_path)
            staged[new_name] = temp_path
            renamed += 1

        # Fase 2: del temporal al nombre definitivo, ya libre de ocupantes.
        if apply:
            for new_name, temp_path in staged.items():
                os.replace(temp_path, os.path.join(folder, new_name))

        self.stdout.write("")
        self.stdout.write(
            f"renombrados: {renamed} | ya estaban: {already} | "
            f"sin archivo: {missing} | tmdb compartido: {shared}"
        )
        if not options['apply']:
            self.stdout.write(self.style.WARNING("\n[simulación] repetí con --apply para ejecutar."))

"""Renombra las carátulas de <trakt_id> a <tmdb_id>.

Los pósters se guardaban como show_<trakt_id>.webp / movie_<trakt_id>.webp. Al pasar la
fuente a Simkl la clave de agrupación es tmdb_id, así que hay que renombrarlos —
renombrar y no re-descargar, para no gastar ancho de banda ni pegarle a TMDB una vez
por obra.

    python manage.py rename_posters_to_tmdb            # simula
    python manage.py rename_posters_to_tmdb --apply    # ejecuta

Idempotente: si el destino ya existe, no hace nada. Después de correrlo en producción
hay que purgar Cloudflare (o esperar el TTL de 30 días), porque cambian las URLs.
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

        renamed = missing = already = collision = 0
        for media_type, trakt_id, tmdb_id in works:
            kind = 'show' if media_type == 'episode' else 'movie'
            old_path = os.path.join(folder, f"{kind}_{trakt_id}.webp")
            new_path = os.path.join(folder, f"{kind}_{tmdb_id}.webp")

            if os.path.exists(new_path):
                if os.path.exists(old_path) and old_path != new_path:
                    collision += 1
                    self.stdout.write(f"  = {kind}_{tmdb_id}.webp ya existe; sobra {kind}_{trakt_id}.webp")
                else:
                    already += 1
                continue
            if not os.path.exists(old_path):
                missing += 1
                self.stdout.write(f"  ! falta {kind}_{trakt_id}.webp (tmdb {tmdb_id})")
                continue

            self.stdout.write(f"  {kind}_{trakt_id}.webp  ->  {kind}_{tmdb_id}.webp")
            if options['apply']:
                os.rename(old_path, new_path)
            renamed += 1

        self.stdout.write("")
        self.stdout.write(
            f"renombrados: {renamed} | ya estaban: {already} | "
            f"sin archivo: {missing} | duplicados: {collision}"
        )
        if not options['apply']:
            self.stdout.write(self.style.WARNING("\n[simulación] repetí con --apply para ejecutar."))

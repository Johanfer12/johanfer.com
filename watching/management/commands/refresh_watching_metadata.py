"""Vuelve a pedir a TMDB la sinopsis, la nota y la carátula de cada obra.

    python manage.py refresh_watching_metadata                  # simula
    python manage.py refresh_watching_metadata --apply          # ejecuta
    python manage.py refresh_watching_metadata --apply --only 329809

Hace falta porque la sincronización solo escribe `overview` y `public_rating` al crear
la fila: si la consulta a TMDB falló ese día, o si el id venía mal de la fuente y luego
se corrigió con TMDB_METADATA_OVERRIDES, la obra se queda con la tarjeta vacía para
siempre. Este comando es la vía para rellenarla sin tocar el historial.

Solo escribe lo que TMDB devuelve: si la consulta falla, se deja lo que ya había en vez
de vaciarlo. No toca `available_episodes`, que se alimenta de los contadores de Simkl y
es lo que decide el listón "Viendo".

Idempotente. Las carátulas solo se descargan si faltan, salvo con --force-posters. Si se
reemplaza una que ya estaba, hay que purgar esa URL en Cloudflare (TTL de 30 días).
"""

import os

from django.conf import settings
from django.core.management.base import BaseCommand

from watching.models import WatchedItem
from watching.utils import download_poster, metadata_for_work


class Command(BaseCommand):
    help = "Re-descarga sinopsis, nota y carátula de cada obra desde TMDB."

    def add_arguments(self, parser):
        parser.add_argument('--apply', action='store_true', help="Ejecuta de verdad.")
        parser.add_argument('--only', type=int, metavar='TMDB_ID',
                            help="Limita la pasada a una sola obra.")
        parser.add_argument('--force-posters', action='store_true',
                            help="Re-descarga la carátula aunque ya exista.")

    def handle(self, *args, **options):
        apply = options['apply']
        rows = WatchedItem.objects.exclude(tmdb_id__isnull=True)
        if options['only']:
            rows = rows.filter(tmdb_id=options['only'])

        # Una fila por obra: los episodios de una serie comparten sinopsis y carátula.
        works = {}
        for item in rows.only('media_type', 'tmdb_id', 'title', 'overview', 'public_rating'):
            works.setdefault((item.media_type, item.tmdb_id), item)

        cache = {}
        texts = ratings = posters = unresolved = 0

        for (media_type, tmdb_id), sample in sorted(works.items(), key=lambda kv: kv[0][1]):
            metadata = metadata_for_work(cache, media_type, tmdb_id, sample.title)
            if not metadata:
                # metadata_for_work ya avisó por log de cuál es y por qué.
                unresolved += 1
                self.stdout.write(self.style.WARNING(
                    f"  ! sin metadatos: {sample.title} (tmdb {tmdb_id})"
                ))
                continue

            siblings = WatchedItem.objects.filter(media_type=media_type, tmdb_id=tmdb_id)
            overview = metadata.get('overview') or ''
            rating = metadata.get('public_rating')

            if overview and overview != sample.overview:
                self.stdout.write(f"  sinopsis: {sample.title} ({len(overview)} caracteres)")
                texts += 1
                if apply:
                    siblings.update(overview=overview)
            if rating is not None and rating != sample.public_rating:
                self.stdout.write(f"  nota: {sample.title} -> {rating}")
                ratings += 1
                if apply:
                    siblings.update(public_rating=rating)

            poster_name = sample.poster_name
            poster_path = os.path.join(settings.MEDIA_ROOT, 'Posters', poster_name)
            needs_poster = options['force_posters'] or not os.path.exists(poster_path)
            if needs_poster and metadata.get('poster_url'):
                self.stdout.write(f"  carátula: {poster_name}")
                posters += 1
                if apply:
                    download_poster(metadata['poster_url'], poster_name,
                                    force=options['force_posters'])

        self.stdout.write("")
        self.stdout.write(
            f"obras: {len(works)} | sinopsis: {texts} | notas: {ratings} | "
            f"carátulas: {posters} | sin resolver: {unresolved}"
        )
        if not apply:
            self.stdout.write(self.style.WARNING("\n[simulación] repetí con --apply para ejecutar."))

"""Sube el historial de la base de datos a Simkl, con sus fechas reales.

Simkl arrancó vacío: el importador desde Trakt está cerrado a cuentas gratis y la app
de móvil no trae transferencia. Pero la BD del sitio sí tiene el historial completo que
Trakt alcanzó a sincronizar, con las fechas correctas, así que se empuja desde acá.

    python manage.py simkl_push_history                  # simula
    python manage.py simkl_push_history --apply
    python manage.py simkl_push_history --apply --limit 2  # prueba con 2 obras

Es idempotente en la práctica: volver a marcar lo ya visto no duplica en Simkl. Respeta
el límite de 1 POST/s de la API.
"""

import time
from collections import defaultdict

from django.core.management.base import BaseCommand

from watching import simkl
from watching.models import WatchedItem

CHUNK = 10          # obras por request; una serie larga carga cientos de episodios
SLEEP_SECONDS = 1.3  # el límite es 1 POST/s


class Command(BaseCommand):
    help = "Escribe el historial de la BD en Simkl con las fechas reales."

    def add_arguments(self, parser):
        parser.add_argument('--apply', action='store_true', help="Ejecuta de verdad.")
        parser.add_argument('--limit', type=int, help="Sube solo las primeras N obras (prueba).")
        parser.add_argument('--skip-ratings', action='store_true', help="No subir mis calificaciones.")

    def handle(self, *args, **options):
        shows, movies, ratings = self._build_payloads(options.get('limit'))

        total_episodes = sum(
            len(season['episodes']) for show in shows for season in show['seasons']
        )
        self.stdout.write(
            f"A subir: {len(shows)} series ({total_episodes} episodios), "
            f"{len(movies)} películas, {len(ratings['shows']) + len(ratings['movies'])} calificaciones"
        )

        if not options['apply']:
            self.stdout.write(self.style.WARNING("\n[simulación] repetí con --apply para ejecutar."))
            if shows:
                self.stdout.write(f"\nEjemplo de serie: {shows[0]['ids']} "
                                  f"temporadas={[s['number'] for s in shows[0]['seasons']]}")
            if movies:
                self.stdout.write(f"Ejemplo de película: {movies[0]}")
            return

        added_shows = self._push('shows', shows)
        added_movies = self._push('movies', movies)

        self.stdout.write(self.style.SUCCESS(
            f"\nEpisodios agregados: {added_shows} | películas agregadas: {added_movies}"
        ))

        if not options['skip_ratings'] and (ratings['shows'] or ratings['movies']):
            self._push_ratings(ratings)

    def _build_payloads(self, limit):
        """Agrupa las filas por obra. Un evento por episodio, con su propia fecha."""
        episodes_by_work = defaultdict(lambda: defaultdict(list))  # tmdb -> temporada -> episodios
        movies = []
        ratings = {'shows': [], 'movies': []}
        seen_rating = set()

        rows = WatchedItem.objects.exclude(tmdb_id__isnull=True).order_by('watched_at')
        for row in rows.iterator():
            stamp = row.watched_at.strftime('%Y-%m-%dT%H:%M:%SZ')
            if row.media_type == 'movie':
                movies.append({'ids': {'tmdb': row.tmdb_id}, 'watched_at': stamp})
            elif row.season is not None and row.episode is not None:
                episodes_by_work[row.tmdb_id][row.season].append(
                    {'number': row.episode, 'watched_at': stamp}
                )

            key = (row.media_type, row.tmdb_id)
            if row.user_rating and key not in seen_rating:
                seen_rating.add(key)
                bucket = 'movies' if row.media_type == 'movie' else 'shows'
                ratings[bucket].append({'ids': {'tmdb': row.tmdb_id}, 'rating': row.user_rating})

        shows = [
            {
                'ids': {'tmdb': tmdb_id},
                'seasons': [
                    {'number': number, 'episodes': episodes}
                    for number, episodes in sorted(seasons.items())
                ],
            }
            for tmdb_id, seasons in episodes_by_work.items()
        ]

        if limit:
            shows = shows[:limit]
            movies = movies[:limit]
            ratings = {'shows': ratings['shows'][:limit], 'movies': ratings['movies'][:limit]}
        return shows, movies, ratings

    def _push(self, key, items):
        added = 0
        for start in range(0, len(items), CHUNK):
            chunk = items[start:start + CHUNK]
            result = simkl.add_to_history({key: chunk}) or {}
            counts = result.get('added') or {}
            added += counts.get('episodes', 0) if key == 'shows' else counts.get('movies', 0)
            not_found = (result.get('not_found') or {}).get(key) or []
            if not_found:
                self.stdout.write(self.style.WARNING(
                    f"  no encontrados en Simkl: {[item.get('ids') for item in not_found][:5]}"
                ))
            self.stdout.write(f"  {key}: {start + len(chunk)}/{len(items)} enviadas")
            time.sleep(SLEEP_SECONDS)
        return added

    def _push_ratings(self, ratings):
        payload = {key: value for key, value in ratings.items() if value}
        result = simkl._post('/sync/ratings', payload) or {}
        self.stdout.write(self.style.SUCCESS(f"Calificaciones: {result.get('added') or result}"))

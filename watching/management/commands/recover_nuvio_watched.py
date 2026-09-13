import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.utils.dateparse import parse_datetime

from watching import simkl
from watching.nuvio import read_watched, recovery_candidates


class Command(BaseCommand):
    help = 'Traducir marcas Nuvio a anime Simkl. Simula por defecto; --apply escribe y verifica.'

    def add_arguments(self, parser):
        parser.add_argument('path', type=Path)
        parser.add_argument('--profile', default='1')
        parser.add_argument('--content-id', required=True)
        parser.add_argument('--since', required=True, help='ISO 8601 con zona horaria')
        parser.add_argument('--apply', action='store_true')

    def handle(self, *args, **options):
        since = parse_datetime(options['since'])
        if since is None or since.tzinfo is None:
            raise CommandError('--since debe incluir fecha, hora y zona horaria')
        cache = {}
        def catalog(sid, is_anime=True):
            if sid not in cache:
                cache[sid] = simkl.fetch_episodes(sid, is_anime=is_anime)
            return cache[sid]
        try:
            candidates, unresolved = recovery_candidates(
                read_watched(options['path'], options['profile']), options['content_id'], since, catalog,
            )
        except (ValueError, OSError) as exc:
            raise CommandError(str(exc)) from exc
        def watched_keys():
            payload = simkl.fetch_all_items()
            return {(item['show']['ids']['simkl'], episode['number'])
                    for item in payload.get('anime', [])
                    for season in item.get('seasons', []) if season.get('number') == 1
                    for episode in season.get('episodes', []) if episode.get('watched_at')}
        already = watched_keys() if candidates else set()
        missing = [(target, when) for target, when in candidates if (target.simkl_id, target.number) not in already]
        self.stdout.write(json.dumps({'pending': [
            {'simkl_id': t.simkl_id, 'episode': t.number, 'tvdb': [t.season, t.episode], 'watched_at': w.isoformat()}
            for t, w in missing], 'already_watched': len(candidates) - len(missing), 'unresolved': unresolved}, ensure_ascii=False))
        if not options['apply']:
            return
        if unresolved:
            raise CommandError('Hay equivalencias sin resolver; no se ha escrito ninguna marca')
        for target, when in missing:
            simkl.add_anime_history(target.simkl_id, target.number, when)
        if missing:
            verified = watched_keys()
            if any((t.simkl_id, t.number) not in verified for t, _ in missing):
                raise CommandError('Escritura enviada pero todavía no confirmada por lectura; revisar antes de reintentar')
        self.stdout.write(self.style.SUCCESS(f'{len(missing)} marcas recuperadas y verificadas en Simkl'))

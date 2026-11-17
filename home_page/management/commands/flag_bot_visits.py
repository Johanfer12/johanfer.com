"""Marca como «robot probable» las visitas guardadas antes del detector.

Solo puede usar lo guardado (el user agent y la ruta): las señales de
cabeceras (Accept-Language, Sec-CH-UA) no se pueden recuperar.
Cada visita se juzga con la fecha en que llegó, para que «navegador viejo»
signifique viejo entonces y no ahora. No toca las ya marcadas.

    python manage.py flag_bot_visits            # cuenta
    python manage.py flag_bot_visits --apply
"""

from collections import Counter

from django.core.management.base import BaseCommand
from django.utils import timezone as dj_timezone

from home_page.bot_detection import isp_reasons, path_reasons, user_agent_reasons
from home_page.models import VisitLog
from home_page.visit_stats import invalidate_badge


class Command(BaseCommand):
    help = 'Marca como robot probable las visitas antiguas, por su user agent.'

    def add_arguments(self, parser):
        parser.add_argument('--apply', action='store_true', help='Escribe; sin él solo cuenta.')

    def handle(self, *args, **options):
        to_flag = {}
        by_reason = Counter()
        rows = VisitLog.objects.filter(bot_reason='').values_list(
            'id', 'user_agent', 'visited_at', 'path', 'isp',
        )
        for visit_id, user_agent, visited_at, path, isp in rows.iterator():
            reasons = user_agent_reasons(user_agent, dj_timezone.localdate(visited_at))
            reasons += path_reasons(path)
            reasons += isp_reasons(isp)
            if reasons:
                to_flag.setdefault(','.join(reasons)[:120], []).append(visit_id)
                by_reason.update(reasons)

        total = sum(len(ids) for ids in to_flag.values())
        self.stdout.write(f'{total} visitas parecen de robot.')
        for reason, count in by_reason.most_common():
            self.stdout.write(f'  {reason}: {count}')
        if not options['apply']:
            self.stdout.write('Simulación: añade --apply para marcarlas.')
            return

        for reason, ids in to_flag.items():
            for start in range(0, len(ids), 500):
                VisitLog.objects.filter(id__in=ids[start:start + 500]).update(bot_reason=reason)
        invalidate_badge()
        self.stdout.write(self.style.SUCCESS(f'{total} visitas marcadas.'))

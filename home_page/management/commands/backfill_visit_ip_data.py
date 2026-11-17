"""Rellena operador y ciudad de visitas guardadas antes de que se anotaran.

Son los dos datos que salen de la IP y por tanto se pueden pedir después
(ipwho.is). El modelo, el sistema y el idioma no: solo los manda el navegador
en el momento de la visita.

Por defecto solo Colombia, que es lo que se mira. Una consulta por IP, no por
visita, y solo rellena lo que está vacío: no pisa la ciudad que dio Cloudflare.

    python manage.py backfill_visit_ip_data            # dice qué haría
    python manage.py backfill_visit_ip_data --apply
    python manage.py backfill_visit_ip_data --pais US --apply
"""

import time

from django.core.management.base import BaseCommand
from django.db.models import Max, Q

from home_page.middleware import VisitLogMiddleware
from home_page.models import VisitLog


class Command(BaseCommand):
    help = 'Rellena operador y ciudad de las visitas antiguas a partir de su IP.'

    # Varias seguidas sin respuesta suelen ser el límite de ipwho.is, no IPs
    # raras: seguir solo gastaría peticiones.
    MAX_CONSECUTIVE_FAILURES = 5

    def add_arguments(self, parser):
        parser.add_argument('--pais', default='CO', help='Código ISO del país (CO por defecto).')
        parser.add_argument('--apply', action='store_true', help='Escribe; sin él solo cuenta.')
        parser.add_argument('--pausa', type=float, default=1.0, help='Segundos entre consultas.')

    def handle(self, *args, **options):
        code = options['pais'].upper()
        pending = (
            VisitLog.objects
            .filter(country_code=code)
            .filter(Q(isp='') | Q(city=''))
        )
        ips = [
            row['ip_address'] for row in
            pending.values('ip_address').annotate(last=Max('visited_at')).order_by('-last')
            if VisitLogMiddleware._is_public_ip(row['ip_address'])
        ]
        self.stdout.write(f'{code}: {pending.count()} visitas sin operador o ciudad, {len(ips)} IPs.')
        if not options['apply']:
            self.stdout.write('Simulación: añade --apply para consultar y escribir.')
            return

        filled = failures = 0
        for index, ip in enumerate(ips):
            if index:
                time.sleep(options['pausa'])
            details = VisitLogMiddleware.lookup_ip_details(ip)
            if not details['isp'] and not details['city']:
                failures += 1
                self.stdout.write(f'  {ip}: sin respuesta')
                if failures >= self.MAX_CONSECUTIVE_FAILURES:
                    self.stderr.write('Demasiados fallos seguidos (¿límite de ipwho.is?). Parado.')
                    break
                continue
            failures = 0
            rows = VisitLog.objects.filter(ip_address=ip, country_code=code)
            if details['isp']:
                rows.filter(isp='').update(isp=details['isp'])
            if details['city']:
                rows.filter(city='').update(city=details['city'])
            filled += 1
            self.stdout.write(f'  {ip}: {details["isp"] or "-"} · {details["city"] or "-"}')

        self.stdout.write(self.style.SUCCESS(f'{filled} de {len(ips)} IPs rellenadas.'))

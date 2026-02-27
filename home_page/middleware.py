import ipaddress
import json
import secrets
from urllib.request import urlopen, Request

from django.core.cache import cache

from .models import VisitLog


class VisitLogMiddleware:
    SESSION_VISITOR_KEY = 'visit_visitor_id'
    SKIP_PREFIXES = (
        '/static/',
        '/media/',
        '/j_admin/',
        '/noticias/',
    )
    SKIP_PATHS = (
        '/favicon.ico',
        '/robots.txt',
        '/sitemap.xml',
        '/visitas/',
    )

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)

        try:
            self._log_visit(request)
        except Exception:
            # Nunca bloquear respuesta al usuario por fallos de logging.
            pass

        return response

    def _log_visit(self, request):
        if request.method != 'GET':
            return
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return
        if request.path in self.SKIP_PATHS:
            return
        if any(request.path.startswith(prefix) for prefix in self.SKIP_PREFIXES):
            return

        accept = (request.headers.get('Accept') or '').lower()
        if 'text/html' not in accept and '*/*' not in accept:
            return

        ip = self._get_client_ip(request)
        if not ip:
            return

        visitor_id = self._get_or_create_visitor_id(request)
        country = self._resolve_country(ip) if self._is_public_ip(ip) else 'Local'

        VisitLog.objects.create(
            ip_address=ip,
            visitor_id=visitor_id,
            country=country or '',
            path=request.path[:255],
            user_agent=(request.headers.get('User-Agent') or '')[:1500],
            referrer=(request.headers.get('Referer') or '')[:1500],
        )

    @staticmethod
    def _get_client_ip(request):
        forwarded = request.headers.get('X-Forwarded-For')
        if forwarded:
            return forwarded.split(',')[0].strip()
        return (request.META.get('REMOTE_ADDR') or '').strip()

    @staticmethod
    def _is_public_ip(value):
        try:
            ip = ipaddress.ip_address(value)
            return not (
                ip.is_private
                or ip.is_loopback
                or ip.is_link_local
                or ip.is_multicast
                or ip.is_reserved
            )
        except ValueError:
            return False

    @staticmethod
    def _resolve_country(ip):
        cache_key = f'visit-country:{ip}'
        cached = cache.get(cache_key)
        if cached is not None:
            return cached

        country = ''
        try:
            req = Request(
                f'https://ipwho.is/{ip}',
                headers={'User-Agent': 'johanfer-visit-logger/1.0'},
            )
            with urlopen(req, timeout=2) as resp:
                data = json.loads(resp.read().decode('utf-8', errors='ignore'))
                if data.get('success'):
                    country = data.get('country', '') or ''
        except Exception:
            country = ''

        cache.set(cache_key, country, 60 * 60 * 24 * 7)
        return country

    def _get_or_create_visitor_id(self, request):
        visitor_id = request.session.get(self.SESSION_VISITOR_KEY, '').strip()
        if visitor_id:
            return visitor_id

        visitor_id = secrets.token_hex(16)
        request.session[self.SESSION_VISITOR_KEY] = visitor_id
        return visitor_id

import ipaddress
import json
import secrets
from datetime import timedelta
from urllib.request import urlopen, Request

from django.core.cache import cache
from django.utils import timezone as dj_timezone

from .models import VisitLog
from .visit_stats import invalidate_badge


def get_client_ip(request):
    real_ip = (request.headers.get('X-Real-IP') or '').strip()
    if real_ip:
        return real_ip

    forwarded = request.headers.get('X-Forwarded-For')
    if forwarded:
        # Tomar el ultimo hop evita spoofing comun en el primer valor.
        return forwarded.split(',')[-1].strip()
    return (request.META.get('REMOTE_ADDR') or '').strip()


class VisitLogMiddleware:
    SESSION_VISITOR_KEY = 'visit_visitor_id'
    SKIP_PREFIXES = (
        '/static/',
        '/media/',
        '/j_admin/',
    )
    SKIP_NEWS_PREFIXES = (
        '/noticias/save/',
        '/noticias/delete/',
        '/noticias/undo/',
        '/noticias/latest-deleted/',
        '/noticias/update-feed/',
        '/noticias/check-new-news/',
        '/noticias/get-page/',
        '/noticias/image-proxy/',
    )
    SKIP_PATHS = (
        '/favicon.ico',
        '/robots.txt',
        '/sitemap.xml',
        '/visitas/',
        # Peticiones de la PWA, no visitas de nadie.
        '/manifest.webmanifest',
        '/sw.js',
        '/offline/',
    )

    # Client Hints de alta entropía que se piden a Chromium. Su user agent está
    # congelado: en Android dice siempre «Android 10; K» y la versión llega
    # como 154.0.0.0, así que sin esto no hay forma de saber qué teléfono es.
    #
    # Accept-CH solo vale a partir de la SIGUIENTE petición, y la mayoría de
    # visitas ajenas son de una página. Critical-CH hace que el navegador, si
    # le faltaban, repita la misma navegación ya con ellas. Pasa una vez por
    # navegador: después recuerda lo que pide el sitio. La petición repetida
    # no se apunta como visita nueva, completa la anterior (_log_visit).
    CLIENT_HINTS = 'Sec-CH-UA-Model, Sec-CH-UA-Platform-Version'
    # Margen para reconocer la repetición: llega en milisegundos, pero la Pi
    # puede tardar en servir la primera.
    HINTS_RETRY_WINDOW = timedelta(seconds=15)

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)

        if (response.get('Content-Type') or '').startswith('text/html'):
            response['Accept-CH'] = self.CLIENT_HINTS
            response['Critical-CH'] = self.CLIENT_HINTS

        try:
            self._log_visit(request)
        except Exception:
            # Nunca bloquear respuesta al usuario por fallos de logging.
            pass

        return response

    @staticmethod
    def _hint(request, name):
        """Valor de un Client Hint sin las comillas de su sintaxis ("SM-A256E")."""
        return (request.headers.get(name) or '').strip().strip('"').strip()

    @classmethod
    def _client_hints(cls, request):
        """(modelo, sistema y versión) o None si el navegador no las mandó.

        None y ('', '') no son lo mismo: un escritorio manda el modelo vacío
        (`""`), y eso ya es la respuesta; lo que falta es la cabecera.
        """
        if 'Sec-CH-UA-Platform-Version' not in request.headers:
            return None
        model = cls._hint(request, 'Sec-CH-UA-Model')[:120]
        platform = cls._hint(request, 'Sec-CH-UA-Platform')
        version = cls._hint(request, 'Sec-CH-UA-Platform-Version')
        os_version = ' '.join(part for part in (platform, version) if part)[:60]
        return model, os_version

    def _log_visit(self, request):
        if request.method != 'GET':
            return
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return
        if request.path in self.SKIP_PATHS:
            return
        if any(request.path.startswith(prefix) for prefix in self.SKIP_PREFIXES):
            return
        if any(request.path.startswith(prefix) for prefix in self.SKIP_NEWS_PREFIXES):
            return

        accept = (request.headers.get('Accept') or '').lower()
        if 'text/html' not in accept and '*/*' not in accept:
            return

        ip = get_client_ip(request)
        if not ip:
            return

        visitor_id = self._get_or_create_visitor_id(request)
        user_agent = (request.headers.get('User-Agent') or '')[:1500]
        hints = self._client_hints(request)

        if hints is not None and self._complete_previous_visit(
            ip, request.path[:255], user_agent, visitor_id, hints,
        ):
            return

        if self._is_public_ip(ip):
            country, country_code = self._resolve_country(
                ip, self._cloudflare_country_code(request, ip),
            )
        else:
            country, country_code = 'Local', ''

        VisitLog.objects.create(
            ip_address=ip,
            visitor_id=visitor_id,
            country_code=country_code or '',
            country=country or '',
            path=request.path[:255],
            user_agent=user_agent,
            referrer=(request.headers.get('Referer') or '')[:1500],
            device_model=hints[0] if hints else '',
            os_version=hints[1] if hints else '',
        )

        # El contador de la cabecera se recalcula en la siguiente página.
        invalidate_badge()

    @classmethod
    def _complete_previous_visit(cls, ip, path, user_agent, visitor_id, hints):
        """Rellena la visita que dejó la petición sin Client Hints, si la hay.

        Es la repetición que pide Critical-CH: misma IP, misma ruta y mismo
        navegador, segundos después y ya con las cabeceras. Apuntarla aparte
        contaría dos visitas por una. Se le pone el visitor_id de ahora porque
        la sesión que sigue usando el navegador es la de esta respuesta.

        Lo que no case (un navegador que no repite, o que ya las mandaba)
        se apunta como siempre, así que no se pierde ninguna visita.
        """
        since = dj_timezone.now() - cls.HINTS_RETRY_WINDOW
        previous = (
            VisitLog.objects
            .filter(
                ip_address=ip, path=path, user_agent=user_agent,
                device_model='', os_version='', visited_at__gte=since,
            )
            .order_by('-id')
            .first()
        )
        if previous is None:
            return False
        previous.device_model, previous.os_version = hints
        previous.visitor_id = visitor_id
        previous.save(update_fields=['device_model', 'os_version', 'visitor_id'])
        return True

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

    # Códigos que Cloudflare manda cuando NO sabe el país: XX es "desconocido"
    # y T1 es la red Tor. Ninguno es un país, así que no se guardan.
    CLOUDFLARE_NO_COUNTRY = frozenset({'XX', 'T1'})
    COUNTRY_CACHE_TTL = 60 * 60 * 24 * 7

    @classmethod
    def _cloudflare_country_code(cls, request, ip):
        """País que Cloudflare calculó para ESTA ip, o '' si no se puede fiar.

        Cloudflare geolocaliza la IP que se conectó a su borde y manda el
        resultado en CF-IPCountry, junto con esa misma IP en CF-Connecting-IP.
        Solo se acepta el país si esa IP es la que se va a guardar en la
        visita: así el país y la IP salen de la misma conexión, y no puede
        colarse el de un salto intermedio ni el de una cabecera suelta.

        Lo que queda fuera cae en la consulta a ipwho.is, como antes:
        peticiones que no pasaron por Cloudflare (no traen las cabeceras), un
        nginx que no esté resolviendo la IP real (no coincidirían) y los
        códigos que no son un país.
        """
        code = (request.headers.get('CF-IPCountry') or '').strip().upper()
        if len(code) != 2 or not code.isalpha() or code in cls.CLOUDFLARE_NO_COUNTRY:
            return ''
        try:
            connecting = ipaddress.ip_address(
                (request.headers.get('CF-Connecting-IP') or '').strip()
            )
            logged = ipaddress.ip_address(ip)
        except ValueError:
            return ''
        # Se comparan como direcciones y no como texto: una IPv6 se puede
        # escribir de varias formas.
        return code if connecting == logged else ''

    @classmethod
    def _country_name(cls, country_code):
        """Nombre con el que ya está guardado ese país, o '' si es nuevo.

        Cloudflare solo da el código. El nombre se toma de las visitas
        anteriores para que un mismo país no acabe con dos nombres distintos.
        """
        cache_key = f'visit-country-name:{country_code}'
        cached = cache.get(cache_key)
        if cached:
            return cached
        name = (
            VisitLog.objects
            .filter(country_code=country_code)
            .exclude(country='')
            .order_by('-id')
            .values_list('country', flat=True)
            .first()
        ) or ''
        if name:
            cache.set(cache_key, name, cls.COUNTRY_CACHE_TTL)
        return name

    @classmethod
    def _resolve_country(cls, ip, cloudflare_code=''):
        cache_key = f'visit-country:{ip}'
        cached = cache.get(cache_key)
        if cached is not None:
            return cached

        if cloudflare_code:
            name = cls._country_name(cloudflare_code)
            if name:
                result = (name, cloudflare_code)
                cache.set(cache_key, result, cls.COUNTRY_CACHE_TTL)
                return result

        country, country_code = cls._lookup_ipwho(ip)
        if cloudflare_code and not country_code:
            # ipwho.is no respondió: el código de Cloudflare vale igual; la
            # página de visitas enseña el código hasta que haya un nombre.
            country_code = cloudflare_code

        result = (country, country_code)
        cache.set(cache_key, result, cls.COUNTRY_CACHE_TTL)
        return result

    @staticmethod
    def _lookup_ipwho(ip):
        """Consulta externa: bloquea hasta 2 s, por eso es el último recurso."""
        country = ''
        country_code = ''
        try:
            req = Request(
                f'https://ipwho.is/{ip}',
                headers={'User-Agent': 'johanfer-visit-logger/1.0'},
            )
            with urlopen(req, timeout=2) as resp:
                data = json.loads(resp.read().decode('utf-8', errors='ignore'))
                if data.get('success'):
                    country = data.get('country', '') or ''
                    country_code = (data.get('country_code', '') or '').upper()
        except Exception:
            country = ''
            country_code = ''
        return country, country_code

    def _get_or_create_visitor_id(self, request):
        visitor_id = request.session.get(self.SESSION_VISITOR_KEY, '').strip()
        if visitor_id:
            return visitor_id

        visitor_id = secrets.token_hex(16)
        request.session[self.SESSION_VISITOR_KEY] = visitor_id
        return visitor_id

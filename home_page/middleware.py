import hashlib
import ipaddress
import json
import logging
import secrets
import threading
from datetime import timedelta
from urllib.request import urlopen, Request

from django.core.cache import cache
from django.db import close_old_connections
from django.db.models import Q
from django.middleware.common import CommonMiddleware
from django.utils import timezone as dj_timezone

from Bookshelf.http_utils import is_ajax

from . import bot_detection
from .models import VisitLog
from .visit_stats import invalidate_badge

logger = logging.getLogger(__name__)

# Un fallo al registrar visitas no debe tumbar la respuesta, pero tampoco puede
# pasar en silencio: si falta una columna tras una migración a medias, el
# registro se para entero. Se avisa una vez cada tanto por tipo de fallo para no
# llenar el journal con una traza por petición.
ERROR_LOG_INTERVAL = 10 * 60


def log_swallowed_error(where):
    if cache.add(f'visit-log-error:{where}', 1, ERROR_LOG_INTERVAL):
        logger.exception('Fallo en %s (se omiten repeticiones durante %d min)',
                         where, ERROR_LOG_INTERVAL // 60)


# Solo para preguntarle si una ruta acabará redirigida a la misma con «/».
_APPEND_SLASH = CommonMiddleware(lambda request: None)


def os_label(platform, version):
    """Nombre del sistema a partir de Sec-CH-UA-Platform(-Version).

    En Windows el número no es la versión comercial sino la de la plataforma
    UWP: 13 o más es Windows 11, de 1 a 10 es Windows 10 y 0 es 7, 8 u 8.1
    (https://learn.microsoft.com/microsoft-edge/web-platform/how-to-detect-win11).
    El resto (Android 16.0.0, macOS 15.1.0) ya es la versión que se conoce.
    """
    if platform == 'Windows' and version:
        try:
            major = int(version.split('.')[0])
        except ValueError:
            major = None
        if major is not None:
            if major >= 13:
                return 'Windows 11'
            if major >= 1:
                return 'Windows 10'
            return 'Windows 7/8'
    return ' '.join(part for part in (platform, version) if part)


# Razón social que da ipwho.is → marca con la que se conoce el operador. Solo
# los de Colombia, que es donde se mira. Se compara en minúsculas y por
# fragmento porque el mismo operador sale con variantes («UNE EPM
# Telecomunicaciones S.A.», «EPM Telecomunicaciones S.A. E.S.P.»).
ISP_BRANDS = (
    ('telmex colombia', 'Claro'),
    ('comunicacion celular', 'Claro'),
    ('colombia movil', 'Tigo'),
    ('epm telecomunicaciones', 'Tigo'),
    ('colombia telecomunicaciones', 'Movistar'),
    ('empresa de telecomunicaciones de bogota', 'ETB'),
    ('etb - ', 'ETB'),
    ('partners telecom colombia', 'WOM'),
    ('avantel', 'WOM'),
    ('hv television', 'HV Multiplay'),
)


def isp_label(isp):
    """«Claro (Telmex Colombia S.A.)» si se conoce la marca; si no, tal cual.

    Si el nombre ya empieza por la marca («ETB - Colombia») no se repite.
    """
    lowered = isp.lower()
    for fragment, brand in ISP_BRANDS:
        if fragment in lowered:
            if lowered.startswith(brand.lower()):
                return isp
            return f'{brand} ({isp})'
    return isp


def short_region(region):
    """«Departamento del Valle del Cauca» → «Valle del Cauca».

    ipwho.is da el nombre oficial y Cloudflare el corto; se guarda el corto
    para que la misma región no salga de dos formas.
    """
    for prefix in ('Departamento del ', 'Departamento de ', 'Departamento '):
        if region.startswith(prefix):
            return region[len(prefix):]
    return region


JS_SEEN_TTL = 60 * 30
# Hasta dónde se miran hacia atrás las visitas que una prueba de JavaScript
# confirma.
JS_CONFIRM_WINDOW = timedelta(minutes=10)

# Peticiones que solo hace un navegador ejecutando la página: el aviso de
# pwa.js, el registro del service worker y el manifiesto que lee el
# navegador. Más cualquier llamada AJAX (X-Requested-With), que es el feed y
# las tablas pidiendo datos. Edge en Android no manda el aviso (no se sabe
# por qué; noviembre 2026) pero sí todo lo demás, y por eso no basta con él.
JS_PROOF_PATHS = ('/visitas/js/', '/sw.js', '/manifest.webmanifest')


def get_visitor_id(request):
    """El visitor_id de la sesión, o '' si aún no tiene."""
    return (request.session.get(VisitLogMiddleware.SESSION_VISITOR_KEY) or '').strip()


def _ip_ua_key(request):
    user_agent = (request.headers.get('User-Agent') or '')[:200]
    digest = hashlib.sha1(user_agent.encode('utf-8', 'ignore')).hexdigest()[:12]
    return f'visit-js:ip:{get_client_ip(request)}:{digest}'


def _js_seen_keys(request):
    """Las dos señas del navegador. Hacen falta las dos porque no todas las
    pruebas llevan la cookie de sesión: el manifiesto se pide sin ella."""
    keys = [_ip_ua_key(request)]
    visitor_id = get_visitor_id(request)
    if visitor_id:
        keys.append(f'visit-js:v:{visitor_id}')
    return keys


def is_js_proof(request):
    return (
        request.path in JS_PROOF_PATHS
        or is_ajax(request)
    )


def js_already_seen(request):
    return any(cache.get(key) for key in _js_seen_keys(request))


def confirm_js(request):
    """Este navegador ejecutó la página: quita «sin-javascript» de sus
    visitas recientes y lo recuerda un rato.

    Se recuerda porque la prueba puede llegar ANTES que la visita que
    confirma: la portada de la PWA se pinta desde la caché y la petición a la
    red que la apunta sale por detrás, y una página recargada pide el
    manifiesto antes de que el servidor apunte la visita.
    """
    keys = _js_seen_keys(request)
    if all(cache.get(key) for key in keys):
        # Ya confirmado hace poco: lo nuevo lo cubre js_already_seen al
        # apuntarse, así que no hace falta tocar la base en cada AJAX.
        return 0
    for key in keys:
        cache.set(key, True, JS_SEEN_TTL)

    since = dj_timezone.now() - JS_CONFIRM_WINDOW
    same_browser = Q(
        ip_address=get_client_ip(request),
        user_agent=(request.headers.get('User-Agent') or '')[:1500],
    )
    visitor_id = get_visitor_id(request)
    if visitor_id:
        same_browser |= Q(visitor_id=visitor_id)
    changed = 0
    recent = VisitLog.objects.filter(
        same_browser, visited_at__gte=since, bot_reason__contains=bot_detection.NO_JS,
    )
    for visit_id, bot_reason in recent.values_list('id', 'bot_reason'):
        VisitLog.objects.filter(pk=visit_id).update(
            bot_reason=bot_detection.remove_reason(bot_reason, bot_detection.NO_JS),
        )
        changed += 1
    if changed:
        invalidate_badge()
    return changed


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
    # Hasta dónde se rellenan hacia atrás las visitas del mismo visitante que
    # llegaron sin hints (_backfill_visitor).
    HINTS_BACKFILL_WINDOW = timedelta(minutes=30)
    # El operador de una IP no cambia de un día para otro: se reutiliza el de
    # una visita anterior de esa IP antes de volver a preguntar a ipwho.is.
    ISP_REUSE_WINDOW = timedelta(days=30)
    # En segundo plano para no hacer esperar al visitante (ipwho.is puede
    # tardar segundos). Los tests lo ponen a False para verlo en el momento.
    ISP_LOOKUP_IN_THREAD = True

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)

        if (response.get('Content-Type') or '').startswith('text/html'):
            response['Accept-CH'] = self.CLIENT_HINTS
            response['Critical-CH'] = self.CLIENT_HINTS

        try:
            if is_js_proof(request) and request.path != '/visitas/js/':
                confirm_js(request)
            self._log_visit(request, response)
        except Exception:
            # Nunca bloquear respuesta al usuario por fallos de logging.
            log_swallowed_error('el registro de visitas')

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
        return model, os_label(platform, version)[:60]

    @classmethod
    def _bot_reason(cls, request, ip, user_agent):
        when = dj_timezone.localdate()
        if cls._is_cloudflare_ip(request, ip):
            reasons = bot_detection.request_reasons(request, user_agent, when)
        else:
            # Por la LAN (http) Chrome no manda Client Hints: solo el UA.
            reasons = bot_detection.user_agent_reasons(user_agent, when)
        reasons += bot_detection.path_reasons(request.path)
        if not js_already_seen(request):
            reasons.append(bot_detection.NO_JS)
        return ','.join(reasons)[:120]

    @staticmethod
    def _language(request):
        """Primer idioma de Accept-Language ("es-CO"), sin el peso q=.

        No es un Client Hint: lo manda cualquier navegador desde la primera
        petición. Distingue un teléfono configurado en Colombia de uno en
        España o de un robot (que suele no mandarlo o mandar "en-US").
        """
        first = (request.headers.get('Accept-Language') or '').split(',')[0]
        return first.split(';')[0].strip()[:35]

    @staticmethod
    def _cloudflare_text(request, name):
        """Cabecera de Cloudflare con texto libre, como CF-IPCity.

        Cloudflare manda los nombres con tilde en UTF-8 y el servidor WSGI los
        lee como latin-1, así que «Bogotá» llegaría como «BogotÃ¡».
        """
        value = (request.headers.get(name) or '').strip()
        try:
            return value.encode('latin-1').decode('utf-8')
        except (UnicodeEncodeError, UnicodeDecodeError):
            return value

    @classmethod
    def _cloudflare_city(cls, request, ip):
        """"Ciudad, región" que Cloudflare calculó para ESTA ip, o ''.

        Llega solo con el Managed Transform «Add visitor location headers»
        activado en el panel. Se exige lo mismo que al país: que
        CF-Connecting-IP sea la IP que se guarda.
        """
        if not cls._is_cloudflare_ip(request, ip):
            return ''
        city = cls._cloudflare_text(request, 'CF-IPCity')
        region = cls._cloudflare_text(request, 'CF-Region')
        parts = [city] if city else []
        if region and region != city:
            parts.append(region)
        return ', '.join(parts)[:120]

    def _log_visit(self, request, response):
        if request.method != 'GET':
            return
        # Una redirección no es ver una página: «/bookshelf» → «/bookshelf/»
        # contaba dos visitas por una. Los robots piden mucho sin la barra.
        if 300 <= response.status_code < 400:
            return
        # La de la barra final no llega aquí como 301 sino como 404:
        # CommonMiddleware va por fuera y la convierte en redirección después.
        if response.status_code == 404 and _APPEND_SLASH.should_redirect_with_slash(request):
            return
        if is_ajax(request):
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

        if hints is not None:
            # Primero la repetición de Critical-CH: si el relleno fuera antes,
            # completaría esa fila y la repetición se apuntaría como otra visita.
            completed = self._complete_previous_visit(
                ip, request.path[:255], user_agent, visitor_id, hints,
            )
            self._backfill_visitor(visitor_id, user_agent, hints)
            if completed:
                return

        if self._is_public_ip(ip):
            country, country_code = self._resolve_country(
                ip, self._cloudflare_country_code(request, ip),
            )
        else:
            country, country_code = 'Local', ''

        visit = VisitLog.objects.create(
            ip_address=ip,
            visitor_id=visitor_id,
            country_code=country_code or '',
            country=country or '',
            path=request.path[:255],
            user_agent=user_agent,
            referrer=(request.headers.get('Referer') or '')[:1500],
            device_model=hints[0] if hints else '',
            os_version=hints[1] if hints else '',
            language=self._language(request),
            city=self._cloudflare_city(request, ip) if self._is_public_ip(ip) else '',
            bot_reason=self._bot_reason(request, ip, user_agent),
        )

        # El contador de la cabecera se recalcula en la siguiente página.
        invalidate_badge()

        if self._is_public_ip(ip):
            self._fill_isp(visit.pk, ip)

    @classmethod
    def _known_isp(cls, ip):
        """Operador ya conocido de esta IP (caché o visita reciente), o ''.

        Si el país acaba de preguntarse a ipwho.is, el operador vino en la
        misma respuesta y está en su caché: no hace falta otra consulta.
        """
        cached = cache.get(cls._ipwho_cache_key(ip))
        if cached and cached.get('isp'):
            return cached['isp']
        since = dj_timezone.now() - cls.ISP_REUSE_WINDOW
        return (
            VisitLog.objects
            .filter(ip_address=ip, visited_at__gte=since)
            .exclude(isp='')
            .order_by('-id')
            .values_list('isp', flat=True)
            .first()
        ) or ''

    @classmethod
    def _fill_isp(cls, visit_id, ip):
        """Anota el operador de la visita: al momento si ya se conoce, si no
        en un hilo aparte que pregunta a ipwho.is."""
        known = cls._known_isp(ip)
        if known:
            cls._store_isp(visit_id, known)
            return
        if cls.ISP_LOOKUP_IN_THREAD:
            threading.Thread(
                target=cls._lookup_and_store_isp, args=(visit_id, ip), daemon=True,
            ).start()
        else:
            cls._lookup_and_store_isp(visit_id, ip)

    @staticmethod
    def _store_isp(visit_id, isp):
        """Guarda el operador y, si es un centro de datos, lo suma a los
        motivos de robot. Va aparte porque el operador llega después de
        crear la visita (en el hilo de ipwho.is)."""
        update = {'isp': isp}
        extra = bot_detection.isp_reasons(isp)
        if extra:
            current = VisitLog.objects.filter(pk=visit_id).values_list('bot_reason', flat=True).first()
            if current is not None:
                update['bot_reason'] = bot_detection.add_reasons(current, extra)
        VisitLog.objects.filter(pk=visit_id).update(**update)
        if extra:
            invalidate_badge()

    @classmethod
    def _lookup_and_store_isp(cls, visit_id, ip):
        try:
            isp = cls._lookup_isp(ip)
            if isp:
                cls._store_isp(visit_id, isp)
        except Exception:
            log_swallowed_error('la consulta del operador')
        finally:
            if cls.ISP_LOOKUP_IN_THREAD:
                # El hilo abrió su propia conexión a la base: cerrarla.
                close_old_connections()

    @classmethod
    def _lookup_isp(cls, ip):
        """Operador según ipwho.is ('connection.isp', o 'org' si no hay)."""
        return cls.lookup_ip_details(ip)['isp']

    # Lo que tarda como mucho ipwho.is en contestar. El país se pregunta
    # mientras el visitante espera la página, así que va más corto; el
    # operador va en un hilo (o en un comando) y puede esperar más.
    IPWHO_TIMEOUT = 4
    IPWHO_COUNTRY_TIMEOUT = 2
    IPWHO_EMPTY = {'country': '', 'country_code': '', 'isp': '', 'city': ''}

    @staticmethod
    def _ipwho_cache_key(ip):
        return f'visit-ipwho:{ip}'

    @classmethod
    def lookup_ip_details(cls, ip, timeout=None):
        """País, código, operador y «ciudad, región» de una IP según ipwho.is.

        Es la única consulta a ipwho.is. Una misma respuesta trae el país y el
        operador, así que se guarda entera en caché: cuando el país se pregunta
        en el momento, el operador ya no necesita una segunda petición. Solo se
        guardan las respuestas buenas; un fallo se vuelve a intentar.

        Vacíos si no responde. La ciudad solo la usa el relleno de visitas
        viejas (backfill_visit_ip_data): en las nuevas la da Cloudflare.
        """
        cache_key = cls._ipwho_cache_key(ip)
        cached = cache.get(cache_key)
        if cached is not None:
            return cached
        details = cls._fetch_ipwho(ip, timeout or cls.IPWHO_TIMEOUT)
        if details is None:
            return dict(cls.IPWHO_EMPTY)
        cache.set(cache_key, details, cls.COUNTRY_CACHE_TTL)
        return details

    @staticmethod
    def _fetch_ipwho(ip, timeout):
        """La petición HTTP, o None si no hay respuesta válida."""
        try:
            req = Request(
                f'https://ipwho.is/{ip}',
                headers={'User-Agent': 'johanfer-visit-logger/1.0'},
            )
            with urlopen(req, timeout=timeout) as resp:
                data = json.loads(resp.read().decode('utf-8', errors='ignore'))
        except Exception:
            return None
        if not data.get('success'):
            return None
        connection = data.get('connection') or {}
        city = (data.get('city') or '').strip()
        region = short_region((data.get('region') or '').strip())
        parts = [city] if city else []
        if region and region != city:
            parts.append(region)
        return {
            'country': data.get('country', '') or '',
            'country_code': (data.get('country_code', '') or '').upper(),
            'isp': (connection.get('isp') or connection.get('org') or '').strip()[:120],
            'city': ', '.join(parts)[:120],
        }

    @classmethod
    def _backfill_visitor(cls, visitor_id, user_agent, hints):
        """Pone los hints a las páginas anteriores del mismo visitante.

        Un navegador que ya tenía el service worker no repite la primera
        navegación con Critical-CH: la hace el worker con fetch(), y eso no se
        repite. Esa página queda sin modelo, pero la siguiente ya lo trae, y
        es el mismo navegador (mismo visitor_id de sesión y mismo UA).
        """
        if not visitor_id:
            return
        since = dj_timezone.now() - cls.HINTS_BACKFILL_WINDOW
        VisitLog.objects.filter(
            visitor_id=visitor_id, user_agent=user_agent,
            device_model='', os_version='', visited_at__gte=since,
        ).update(device_model=hints[0], os_version=hints[1])

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
        return code if cls._is_cloudflare_ip(request, ip) else ''

    @staticmethod
    def _is_cloudflare_ip(request, ip):
        """¿La IP que Cloudflare geolocalizó es la que se va a guardar?"""
        try:
            connecting = ipaddress.ip_address(
                (request.headers.get('CF-Connecting-IP') or '').strip()
            )
            logged = ipaddress.ip_address(ip)
        except ValueError:
            return False
        # Se comparan como direcciones y no como texto: una IPv6 se puede
        # escribir de varias formas.
        return connecting == logged

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

    @classmethod
    def _lookup_ipwho(cls, ip):
        """País según ipwho.is: bloquea hasta 2 s, por eso es el último recurso.

        La respuesta queda en caché con el operador, que es lo que luego
        reutiliza _known_isp sin volver a preguntar."""
        details = cls.lookup_ip_details(ip, timeout=cls.IPWHO_COUNTRY_TIMEOUT)
        return details['country'], details['country_code']

    def _get_or_create_visitor_id(self, request):
        visitor_id = get_visitor_id(request)
        if visitor_id:
            return visitor_id

        visitor_id = secrets.token_hex(16)
        request.session[self.SESSION_VISITOR_KEY] = visitor_id
        return visitor_id

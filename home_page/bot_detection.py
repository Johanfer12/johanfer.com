"""Señales de que una visita la hizo un programa y no una persona.

Ninguna es una prueba; juntas, o una de las fuertes sola, bastan para marcar
la visita como «robot probable». No se descarta nada: la visita se guarda
igual, con el motivo en VisitLog.bot_reason, y solo deja de contar en la
insignia de la cabecera.

Hay dos familias:

- Las que salen del user agent, que está guardado y se pueden aplicar a
  visitas viejas (flag_bot_visits).
- Las que salen de cabeceras que no se guardan (Accept-Language, Sec-CH-UA):
  solo valen en el momento de la visita.
"""
import re
from datetime import date

from django.urls import Resolver404, resolve

# Un robot que se presenta como tal: buscadores, librerías HTTP, navegadores
# sin ventana y las vistas previas de enlaces (WhatsApp/, TelegramBot,
# Slackbot...), que no son una persona mirando la página sino una app leyendo
# su título. Ojo con lo que NO va aquí: «Telegram-Android» o «Instagram» son
# navegadores dentro de una app, con una persona detrás. El (?<!cu) es por los
# teléfonos CUBOT, cuyo modelo sale en el user agent de los WebView.
DECLARED = re.compile(
    r'(?<!cu)bot\b|bot/|crawl|spider|slurp|scrap|curl/|wget|python|httpx|'
    r'aiohttp|go-http-client|java/|okhttp|headless|phantomjs|libwww|axios|'
    r'node-fetch|postman|facebookexternalhit|whatsapp/|lighthouse|pagespeed',
    re.IGNORECASE,
)

CHROME = re.compile(r'Chrome/(\d+)\.(\d+)\.(\d+)\.(\d+)')
FIREFOX = re.compile(r'Firefox/(\d+)\.')
# Safari pone su versión en «Version/17.5». No sigue un calendario fijo, así
# que va con un mínimo: iOS 15 llega hasta el iPhone 6s (2015), de modo que un
# Safari anterior en un dispositivo real hoy es rarísimo, y «iPhone OS 13_2_3 /
# Version/13.0.3» es un user agent de 2019 que repiten muchos robots.
SAFARI = re.compile(r'Version/(\d+)\.[\d.]* (?:Mobile/\S+ )?Safari/')
SAFARI_MIN = 15

# Navegadores basados en Chromium que van con una versión de Chromium más
# vieja que la de Chrome, o que mandan la versión completa por su cuenta. A
# estos no se les aplican las reglas de versión.
CHROMIUM_FORKS = (
    '; wv)',            # WebView de Android (navegadores dentro de apps).
    'SamsungBrowser/', 'UCBrowser/', 'YaBrowser/', 'MiuiBrowser/',
    'HuaweiBrowser/', 'HeyTapBrowser/', 'OPR/', 'Electron/',
)

# Fechas de referencia para estimar la versión actual sin consultar nada:
# Chrome y Firefox sacan una versión cada cuatro semanas.
CHROME_ANCHOR = (date(2023, 12, 5), 120)
FIREFOX_ANCHOR = (date(2023, 12, 19), 121)
RELEASE_DAYS = 28
# Unas 15 versiones son algo más de un año. Un navegador de escritorio se
# actualiza solo; uno tan atrasado suele ser un user agent copiado. Holgado
# para no marcar el Firefox ESR, que va hasta un año por detrás.
OLD_VERSIONS = 15

LABELS = {
    'declarado': 'Se presenta como robot',
    'version-completa': 'Chrome con la versión completa (los reales la recortan)',
    'navegador-viejo': 'Navegador de hace más de un año',
    'sin-client-hints': 'Dice ser Chrome pero no manda Sec-CH-UA',
    'sin-idioma': 'No manda Accept-Language',
    'sin-user-agent': 'Sin user agent',
    'ua-incompleto': 'User agent cortado: no nombra ningún navegador',
    'ruta-inexistente': 'Pidió una página que no existe en el sitio',
}

# Todo navegador real termina su user agent nombrándose: Chrome y derivados
# con «Safari/537.36», Safari con «Safari/», Firefox con «Gecko/… Firefox/»,
# y los navegadores dentro de apps de iOS con «like Gecko». Uno que empieza
# como navegador («Mozilla/5.0 (Windows…) AppleWebKit/537.36») y se corta
# antes es un user agent fabricado a medias.
BROWSER_TOKENS = ('Safari/', 'Firefox/', 'Gecko')


def _expected_major(anchor, when):
    anchor_date, anchor_version = anchor
    return anchor_version + (when - anchor_date).days // RELEASE_DAYS


def _is_fork(user_agent):
    return any(token in user_agent for token in CHROMIUM_FORKS)


def user_agent_reasons(user_agent, when):
    """Motivos que salen solo del user agent. `when` es la fecha de la visita."""
    if not user_agent.strip():
        return ['sin-user-agent']
    if DECLARED.search(user_agent):
        return ['declarado']

    reasons = []
    if user_agent.startswith('Mozilla/') and not any(
        token in user_agent for token in BROWSER_TOKENS
    ):
        reasons.append('ua-incompleto')

    chrome = CHROME.search(user_agent)
    if chrome and not _is_fork(user_agent):
        major, minor, build, patch = (int(part) for part in chrome.groups())
        # Desde 2023 Chrome manda «124.0.0.0»; un número de compilación real
        # («124.0.6367.207») es de un user agent fabricado o muy viejo.
        if build or patch:
            reasons.append('version-completa')
        if major < _expected_major(CHROME_ANCHOR, when) - OLD_VERSIONS:
            reasons.append('navegador-viejo')

    safari = SAFARI.search(user_agent)
    if safari and 'Chrome/' not in user_agent and int(safari.group(1)) < SAFARI_MIN:
        reasons.append('navegador-viejo')

    firefox = FIREFOX.search(user_agent)
    if firefox and int(firefox.group(1)) < _expected_major(FIREFOX_ANCHOR, when) - OLD_VERSIONS:
        reasons.append('navegador-viejo')
    return reasons


def path_reasons(path):
    """'ruta-inexistente' si la ruta no es ninguna página del sitio.

    Los escáneres prueban direcciones de otras aplicaciones
    («/api/session/properties», «/wp-login.php») por si hay una abierta. Se
    mira contra las URLs de Django, no contra el código de respuesta, para
    poder aplicarlo también a visitas viejas: una noticia borrada da 404 pero
    su ruta existe, y quien la pidió puede ser una persona con un enlace viejo.
    """
    # «/bookshelf» sin barra existe: Django lo redirige a «/bookshelf/». Son
    # las mitades de las parejas que se apuntaban antes de ignorar las
    # redirecciones, no rutas inventadas.
    candidates = (path, path + '/') if not path.endswith('/') else (path,)
    for candidate in candidates:
        try:
            resolve(candidate)
            return []
        except Resolver404:
            continue
    return ['ruta-inexistente']


def request_reasons(request, user_agent, when):
    """Todas las señales, incluidas las de cabeceras que no se guardan.

    Solo para peticiones que llegaron por HTTPS a través de Cloudflare: por
    la LAN el sitio va en http y ahí Chrome no manda Client Hints.
    """
    reasons = user_agent_reasons(user_agent, when)
    if reasons[:1] in (['declarado'], ['sin-user-agent']):
        return reasons
    is_chrome = 'Chrome/' in user_agent and not _is_fork(user_agent)
    if is_chrome and 'Sec-CH-UA' not in request.headers:
        reasons.append('sin-client-hints')
    if not (request.headers.get('Accept-Language') or '').strip():
        reasons.append('sin-idioma')
    return reasons


def labels(bot_reason):
    """'version-completa,sin-idioma' → lista de frases para el tooltip."""
    return [LABELS.get(code, code) for code in bot_reason.split(',') if code]

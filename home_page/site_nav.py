"""Qué sección es cada página, cómo se titula y adónde vuelve.

Antes todo esto vivía en `header.html` como una cadena de `if request.path`,
con el mismo icono de la casa para ir a la portada y para volver a la sección
(desde las estadísticas de Libros, la casa llevaba a Libros). Aquí se decide una
vez, y la plantilla solo pinta.
"""
from urllib.parse import parse_qs, urlparse

from . import retos

# Películas no tiene ruta propia: es /viendo/ con ?tipo=peliculas, la misma
# vista que las series. Para la navegación es una sección aparte (en la
# portada no: allí TV cubre las dos). Ver section_for.
SECTIONS = (
    ('libros', 'Libros', '/bookshelf/'),
    ('musica', 'Música', '/spotify/'),
    ('tv', 'TV', '/viendo/'),
    ('peliculas', 'Películas', '/viendo/?tipo=peliculas'),
    ('noticias', 'Noticias', '/noticias/'),
)

_SECTION_BY_KEY = {key: (label, url) for key, label, url in SECTIONS}

# Páginas que cuelgan de una sección: (título, subtítulo, sección a la que vuelven).
_SUBPAGES = {
    '/bookshelf/stats/': ('Libros', 'Estadísticas', 'libros'),
    '/viendo/stats/': ('TV', 'Estadísticas', 'tv'),
    '/spotify/stats/': ('Música', 'Estadísticas', 'musica'),
    '/noticias/estadisticas/': ('Estadísticas del feed', None, 'noticias'),
    '/noticias/system-stats/': ('Estadísticas del sistema', None, 'noticias'),
    '/noticias/redundancy-test/': ('Redundancia', None, 'noticias'),
}

# Páginas a las que se llega desde cualquier sección: vuelven a la de origen.
_ORIGIN_PAGES = {
    '/about/': 'Acerca de',
    '/visitas/': 'Visitas',
}


def section_for(path, tipo=None):
    """Clave de la sección a la que pertenece `path`, o None.

    `tipo` es el ?tipo= de la petición: separa Películas de TV en /viendo/.
    """
    if path == '/viendo/' and tipo == 'peliculas':
        return 'peliculas'
    for key, _label, url in SECTIONS:
        if '?' not in url and path.startswith(url):
            return key
    return None


def _origin_section(request):
    """Sección desde la que se llegó a una página común (About, Visitas).

    Se guarda en sesión porque al recargar o al volver de un enlace externo el
    Referer ya no la dice. Se sobrescribe en cada llegada desde otra página del
    sitio: antes solo se anotaban tres secciones y desde TV o la portada se
    quedaba el origen de la visita anterior.
    """
    session_key = f'nav_origin:{request.path}'
    referer = urlparse(request.META.get('HTTP_REFERER', ''))
    if referer.path and referer.path != request.path:
        tipo = parse_qs(referer.query).get('tipo', [None])[0]
        request.session[session_key] = section_for(referer.path, tipo) or 'home'
    origin = request.session.get(session_key)
    return origin if origin in _SECTION_BY_KEY else None


def _back_to(section_key):
    label, url = _SECTION_BY_KEY[section_key]
    return {'url': url, 'label': f'Volver a {label}'}


def build(request):
    path = request.path
    section = section_for(path, request.GET.get('tipo'))
    title = subtitle = back = None
    is_subpage = False

    if path in _SUBPAGES:
        title, subtitle, parent = _SUBPAGES[path]
        back = _back_to(parent)
        is_subpage = True
    elif path.startswith('/noticias/configuracion/'):
        title = 'Configuración del feed'
        back = _back_to('noticias')
        is_subpage = True
    elif path in _ORIGIN_PAGES:
        title = _ORIGIN_PAGES[path]
        origin = _origin_section(request)
        if origin:
            back = _back_to(origin)
        is_subpage = True
    elif path == '/retos/':
        # El tema que se está viendo (el flotante cambia ?tema=) va de subtítulo.
        title = 'Retos futuros'
        temas = dict(retos.TEMAS)
        subtitle = temas.get(request.GET.get('tema'), temas[retos.TEMA_POR_DEFECTO])
    elif section:
        title = _SECTION_BY_KEY[section][0]

    return {
        'title': title or 'Rincón de Johan',
        'subtitle': subtitle,
        'back': back,
        'is_subpage': is_subpage,
        # El botón de información va en las portadas de sección; en las
        # subpáginas su sitio lo ocupa la flecha de retorno.
        'show_info': bool(section) and not is_subpage,
        'sections': [
            {
                'key': key, 'label': label, 'url': url, 'current': key == section,
                # «page» en la portada de la sección, «true» en sus subpáginas.
                'aria_current': ('true' if is_subpage else 'page') if key == section else None,
            }
            for key, label, url in SECTIONS
        ],
    }

"""Comprobaciones HTTP que comparten las apps del sitio."""
from django.contrib.auth.decorators import user_passes_test

# Todas las vistas privadas mandan al mismo login: el del feed de noticias.
LOGIN_URL = '/noticias/login/'


def is_ajax(request):
    """¿La pidió el JavaScript de la página (fetch o XHR) y no el navegador?"""
    return request.headers.get('X-Requested-With') == 'XMLHttpRequest'


def superuser_required(view_func):
    """Solo para el superusuario; el resto va al login."""
    return user_passes_test(lambda u: u.is_superuser, login_url=LOGIN_URL)(view_func)


# Tandas de las rejillas de portadas (Libros y TV). El navegador pide cuántas
# tarjetas quiere según las columnas que le caben, para que cada tanda acabe
# en una fila completa: con un tamaño fijo de 20, una pantalla de 8 columnas
# dejaba la última fila a medias. La primera carga no sabe el ancho y manda
# TANDA_INICIAL, que se divide entre 2, 3, 4, 6 y 8; el script la completa.
TANDA_INICIAL = 24
TANDA_MAXIMA = 96


def _entero(valor, defecto):
    try:
        return int(valor)
    except (TypeError, ValueError):
        return defecto


def tanda(request, items, total):
    """Corta `items` (queryset o lista) según ?offset= y ?limit=.

    Devuelve (tarjetas, hay_mas). `?page=` sigue valiendo para enlaces viejos:
    se traduce a offset con el límite de la petición.
    """
    limite = min(max(_entero(request.GET.get('limit'), TANDA_INICIAL), 1), TANDA_MAXIMA)
    if 'offset' in request.GET:
        inicio = max(_entero(request.GET.get('offset'), 0), 0)
    else:
        pagina = max(_entero(request.GET.get('page'), 1), 1)
        inicio = (pagina - 1) * limite
    tarjetas = list(items[inicio:inicio + limite])
    return tarjetas, inicio + len(tarjetas) < total

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

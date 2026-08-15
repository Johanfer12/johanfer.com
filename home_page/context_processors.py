from .visit_stats import badge_count


def visits_badge(request):
    """Visitas ajenas desde Colombia, para el botón de la cabecera.

    Solo se calcula para el superusuario, que es el único que ve el botón.
    """
    user = getattr(request, 'user', None)
    if not (user and user.is_authenticated and user.is_superuser):
        return {}

    try:
        return {'visits_badge_count': badge_count()}
    except Exception:
        # Que un fallo contando no tire la página entera.
        return {}

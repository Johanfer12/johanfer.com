from django import template
from django.utils.safestring import mark_safe

from Bookshelf.html_sanitizer import sanitize_html

register = template.Library()


@register.filter(name='sanitize')
def sanitize(value):
    """Renderiza HTML externo permitiendo solo etiquetas de formato seguras."""
    return mark_safe(sanitize_html(value))


@register.filter(name='rating_stars')
def rating_stars(value):
    """Renderiza una nota 0-10 como 5 estrellas, redondeada a media estrella."""
    if value in (None, ''):
        return ''
    try:
        five_star_rating = round((float(value) / 2) * 2) / 2
    except (TypeError, ValueError):
        return ''

    full_stars = int(five_star_rating)
    has_half_star = (five_star_rating - full_stars) >= 0.5
    empty_stars = 5 - full_stars - (1 if has_half_star else 0)
    label = f"{five_star_rating:g} de 5"
    stars = ['<span class="rating-star rating-star-full">★</span>' for _ in range(full_stars)]
    if has_half_star:
        stars.append('<span class="rating-star rating-star-half">★</span>')
    stars.extend('<span class="rating-star rating-star-empty">★</span>' for _ in range(empty_stars))
    return mark_safe(f'<span class="rating-stars" aria-label="{label}" title="{label}">{"".join(stars)}</span>')

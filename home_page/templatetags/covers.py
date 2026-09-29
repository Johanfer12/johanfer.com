from django import template
from django.utils.html import format_html

from home_page.cover_colors import color_for

register = template.Library()


@register.simple_tag
def cover_style(subfolder, *name_parts):
    """` style="--cover-color: #rrggbb"` para la imagen, o nada si no hay color.

    Uso: {% cover_style "Covers" book.id ".webp" %} · {% cover_style "Posters" card.poster_name %}
    """
    color = color_for(subfolder, ''.join(str(part) for part in name_parts))
    if not color:
        return ''
    return format_html(' style="--cover-color: {}"', color)

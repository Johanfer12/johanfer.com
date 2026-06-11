from django import template
from django.utils.safestring import mark_safe

from Bookshelf.html_sanitizer import sanitize_html

register = template.Library()


@register.filter(name='sanitize')
def sanitize(value):
    """Renderiza HTML externo permitiendo solo etiquetas de formato seguras."""
    return mark_safe(sanitize_html(value))

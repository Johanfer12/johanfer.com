"""Sanitización de HTML proveniente de fuentes externas (feeds RSS, Goodreads).

Lista blanca de etiquetas de formato inofensivas; todo lo demás (scripts,
event handlers, iframes, estilos) se elimina antes de renderizar o guardar.
"""
import bleach

ALLOWED_TAGS = {
    'a', 'b', 'strong', 'i', 'em', 'u', 's',
    'p', 'br', 'span',
    'ul', 'ol', 'li', 'blockquote',
}

ALLOWED_ATTRIBUTES = {
    'a': ['href', 'title'],
}

ALLOWED_PROTOCOLS = ['http', 'https', 'mailto']


def sanitize_html(value):
    if not value:
        return ''
    return bleach.clean(
        str(value),
        tags=ALLOWED_TAGS,
        attributes=ALLOWED_ATTRIBUTES,
        protocols=ALLOWED_PROTOCOLS,
        strip=True,
        strip_comments=True,
    )

"""Sanitización de HTML proveniente de fuentes externas (feeds RSS, Goodreads).

Lista blanca de etiquetas de formato inofensivas; todo lo demás (scripts,
event handlers, iframes, estilos) se elimina antes de renderizar o guardar.
"""
from functools import lru_cache

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


# El filtro `sanitize` de las plantillas vuelve a sanear en cada render lo que
# ya se guardó saneado (defensa en profundidad: una fila vieja o escrita a mano
# no puede colar HTML). Medido en la Pi, eso era la mitad del render de
# /bookshelf/ (160 de 370 ms con 24 sinopsis) y ~80 ms de /noticias/. Como la
# salida depende solo del texto, se guarda en memoria: la protección es la
# misma y el coste se paga una vez por texto y proceso. El tope cubre los ~285
# libros más una página de noticias y de TV; los textos enormes no se guardan.
_CACHE_MAX_CHARS = 20_000


@lru_cache(maxsize=600)
def _clean_cached(text):
    return _clean(text)


def _clean(text):
    return bleach.clean(
        text,
        tags=ALLOWED_TAGS,
        attributes=ALLOWED_ATTRIBUTES,
        protocols=ALLOWED_PROTOCOLS,
        strip=True,
        strip_comments=True,
    )


def sanitize_html(value):
    if not value:
        return ''
    text = str(value)
    if len(text) > _CACHE_MAX_CHARS:
        return _clean(text)
    return _clean_cached(text)

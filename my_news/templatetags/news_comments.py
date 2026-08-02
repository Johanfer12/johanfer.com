from django import template

from my_news.comment_extractors import supports_comment_extraction
from my_news.interest import percentile_of


register = template.Library()


@register.filter
def has_comment_extractor(url):
    return supports_comment_extraction(url)


@register.filter
def interest_percentile(score):
    """Posición de la noticia dentro del feed, en percentil.

    No se muestra el score crudo porque su origen se mueve con el número de
    votos de cada clase; el percentil sí es estable.
    """
    return percentile_of(score)

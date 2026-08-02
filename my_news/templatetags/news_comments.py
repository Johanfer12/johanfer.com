from django import template

from my_news.comment_extractors import supports_comment_extraction


register = template.Library()


@register.filter
def has_comment_extractor(url):
    return supports_comment_extraction(url)


@register.filter
def interest_percent(score):
    """Formatea el score de interés ([-1, 1]) como porcentaje con signo."""
    if score is None:
        return ''
    try:
        return f"{float(score) * 100:+.0f}%"
    except (TypeError, ValueError):
        return ''

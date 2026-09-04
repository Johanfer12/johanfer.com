from django import template

from my_news.comment_extractors import supports_comment_extraction


register = template.Library()


@register.filter
def has_comment_extractor(url):
    return supports_comment_extraction(url)

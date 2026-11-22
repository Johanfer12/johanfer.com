"""Vistas de noticias, repartidas por tema.

Este módulo solo reexporta lo que usan `my_news/urls.py` y los tests, para
que `from my_news import views` siga funcionando. Ojo al parchear en un test:
hay que apuntar al submódulo donde vive el nombre
(`my_news.views.update.news_update_running`), no a este paquete; un parche
aquí no lo ve la función que lo usa.

Ningún submódulo importa `services` ni `tasks` a nivel de módulo: arrastran
los clientes de IA y Qdrant, que el proceso web no debe cargar.
"""
from .comments import news_comments
from .common import PAGE_SIZE
from .feed import (
    NEWS_NOTIFICATION_SETTLE_DELAY,
    NewsListView,
    NewsLoginView,
    SavedNewsListView,
    check_new_news,
    delete_news,
    get_page,
    image_proxy,
    latest_deleted_news,
    toggle_save_news,
    undo_delete,
)
from .management import (
    WORD_FILTERS_PAGE_SIZE,
    ai_filter_create,
    ai_filter_delete,
    ai_filter_edit,
    ai_filter_toggle,
    feed_management,
    source_create,
    source_delete,
    source_edit,
    source_toggle,
    word_filter_create,
    word_filter_delete,
    word_filter_edit,
    word_filter_rows,
    word_filter_toggle,
)
from .redundancy import REDUNDANCY_PAGE_SIZE, redundancy_rows, test_redundancy
from .stats import news_stats, system_stats
from .update import update_feed, update_feed_status

__all__ = [
    'NEWS_NOTIFICATION_SETTLE_DELAY',
    'PAGE_SIZE',
    'REDUNDANCY_PAGE_SIZE',
    'WORD_FILTERS_PAGE_SIZE',
    'NewsListView',
    'NewsLoginView',
    'SavedNewsListView',
    'ai_filter_create',
    'ai_filter_delete',
    'ai_filter_edit',
    'ai_filter_toggle',
    'check_new_news',
    'delete_news',
    'feed_management',
    'get_page',
    'image_proxy',
    'latest_deleted_news',
    'news_comments',
    'news_stats',
    'redundancy_rows',
    'source_create',
    'source_delete',
    'source_edit',
    'source_toggle',
    'system_stats',
    'test_redundancy',
    'toggle_save_news',
    'undo_delete',
    'update_feed',
    'update_feed_status',
    'word_filter_create',
    'word_filter_delete',
    'word_filter_edit',
    'word_filter_rows',
    'word_filter_toggle',
]

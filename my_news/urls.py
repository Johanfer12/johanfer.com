from django.urls import path
from . import views

app_name = 'my_news'

urlpatterns = [
    path('', views.NewsListView.as_view(), name='news_list'),
    path('guardadas/', views.SavedNewsListView.as_view(), name='saved_news_list'),
    path('login/', views.NewsLoginView.as_view(), name='news_login'),
    path('save/<int:pk>/', views.toggle_save_news, name='toggle_save_news'),
    path('delete/<int:pk>/', views.delete_news, name='delete_news'),
    path('undo/<int:pk>/', views.undo_delete, name='undo_delete'),
    path('latest-deleted/', views.latest_deleted_news, name='latest_deleted_news'),
    path('update-feed/', views.update_feed, name='update_feed'),
    path('check-new-news/', views.check_new_news, name='check_new_news'),
    path('get-page/', views.get_page, name='get_page'),
    path('comments/<int:pk>/', views.news_comments, name='news_comments'),
    path('configuracion/', views.feed_management, name='feed_management'),
    path('configuracion/fuentes/nueva/', views.source_create, name='source_create'),
    path('configuracion/fuentes/<int:pk>/editar/', views.source_edit, name='source_edit'),
    path('configuracion/fuentes/<int:pk>/estado/', views.source_toggle, name='source_toggle'),
    path('configuracion/fuentes/<int:pk>/eliminar/', views.source_delete, name='source_delete'),
    path('configuracion/filtros/nuevo/', views.word_filter_create, name='word_filter_create'),
    path('configuracion/filtros/<int:pk>/editar/', views.word_filter_edit, name='word_filter_edit'),
    path('configuracion/filtros/<int:pk>/estado/', views.word_filter_toggle, name='word_filter_toggle'),
    path('configuracion/filtros/<int:pk>/eliminar/', views.word_filter_delete, name='word_filter_delete'),
    path('configuracion/filtros-ia/nuevo/', views.ai_filter_create, name='ai_filter_create'),
    path('configuracion/filtros-ia/<int:pk>/editar/', views.ai_filter_edit, name='ai_filter_edit'),
    path('configuracion/filtros-ia/<int:pk>/estado/', views.ai_filter_toggle, name='ai_filter_toggle'),
    path('configuracion/filtros-ia/<int:pk>/eliminar/', views.ai_filter_delete, name='ai_filter_delete'),
    path('redundancy-test/', views.test_redundancy, name='redundancy_test'),
    path('system-stats/', views.system_stats, name='system_stats'),
    path('image-proxy/', views.image_proxy, name='image_proxy'),
] 

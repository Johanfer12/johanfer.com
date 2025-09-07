from django.urls import path
from . import views

app_name = 'my_news'

urlpatterns = [
    path('', views.NewsListView.as_view(), name='news_list'),
    path('login/', views.NewsLoginView.as_view(), name='news_login'),
    path('delete/<int:pk>/', views.delete_news, name='delete_news'),
    path('undo/<int:pk>/', views.undo_delete, name='undo_delete'),
    path('update-feed/', views.update_feed, name='update_feed'),
    path('cleanup-old/', views.cleanup_old_news, name='cleanup_old_news'),
    path('retry-summaries/', views.retry_summaries, name='retry_summaries'),
    path('check-new-news/', views.check_new_news, name='check_new_news'),
    path('get-news-count/', views.get_news_count, name='get_news_count'),
    path('get-page/', views.get_page, name='get_page'),
    path('redundancy-test/', views.test_redundancy, name='redundancy_test'),
    path('generate-embeddings/', views.generate_embeddings, name='generate_embeddings'),
    path('check-redundancy/', views.check_all_redundancy, name='check_redundancy'),
] 
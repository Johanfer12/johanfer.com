from django.urls import path
from . import views

app_name = 'my_news'

urlpatterns = [
    path('', views.NewsListView.as_view(), name='news_list'),
    path('guardadas/', views.SavedNewsListView.as_view(), name='saved_news_list'),
    path('login/', views.NewsLoginView.as_view(), name='news_login'),
    path('save/<int:pk>/', views.toggle_save_news, name='toggle_save_news'),
    path('vote/<int:pk>/', views.vote_news, name='vote_news'),
    path('delete/<int:pk>/', views.delete_news, name='delete_news'),
    path('undo/<int:pk>/', views.undo_delete, name='undo_delete'),
    path('latest-deleted/', views.latest_deleted_news, name='latest_deleted_news'),
    path('update-feed/', views.update_feed, name='update_feed'),
    path('check-new-news/', views.check_new_news, name='check_new_news'),
    path('get-page/', views.get_page, name='get_page'),
    path('comments/<int:pk>/', views.news_comments, name='news_comments'),
    path('redundancy-test/', views.test_redundancy, name='redundancy_test'),
    path('system-stats/', views.system_stats, name='system_stats'),
    path('image-proxy/', views.image_proxy, name='image_proxy'),
] 

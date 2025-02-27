from django.urls import path
from . import views

app_name = 'my_news'

urlpatterns = [
    path('', views.NewsListView.as_view(), name='news_list'),
    path('delete/<int:pk>/', views.delete_news, name='delete_news'),
    path('update-feed/', views.update_feed, name='update_feed'),
    path('check-new-news/', views.check_new_news, name='check_new_news'),
    path('get-news-count/', views.get_news_count, name='get_news_count'),
] 
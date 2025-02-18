from django.urls import path
from . import views

app_name = 'my_news'

urlpatterns = [
    path('', views.NewsListView.as_view(), name='news_list'),
    path('delete/<int:pk>/', views.delete_news, name='delete_news'),
    path('update-feed/', views.update_feed, name='update_feed'),
] 
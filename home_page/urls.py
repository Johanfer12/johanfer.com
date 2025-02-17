from django.urls import path
from . import views

app_name = 'home_page'

urlpatterns = [
    path('', views.home, name='index'),
    path('bookshelf/', views.bookshelf, name='bookshelf'),
    path('bookshelf/stats/', views.stats, name='stats'),
    path('about/', views.about, name='about'),
]

handler404 = views.custom_404_view
from django.urls import path
from . import views

urlpatterns = [
    path('', views.home, name='home'),
    path('bookshelf/', views.bookshelf, name='bookshelf'),
    path('about/', views.about, name='about'),
    path('stats/', views.stats, name='stats'),
]

handler404 = views.custom_404_view
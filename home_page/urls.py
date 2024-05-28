from django.urls import path
from . import views

urlpatterns = [
    path('', views.book_list, name='book_list'),
    path('about/', views.about, name='about'),
    path('stats/', views.stats, name='stats'),
]

handler404 = views.custom_404_view
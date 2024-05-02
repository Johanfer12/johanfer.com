from django.urls import path
from . import views

urlpatterns = [
    path('', views.book_list, name='book_list'),
    path('about/', views.about, name='about'),
]

from django.urls import path
from . import views

app_name = 'watching'

urlpatterns = [
    path('', views.watching, name='index'),
    path('stats/', views.watching_stats, name='stats'),
]

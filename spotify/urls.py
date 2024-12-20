from django.urls import path
from . import views

app_name = 'spotify'

urlpatterns = [
    path('', views.spotify_dashboard, name='dashboard'),
] 
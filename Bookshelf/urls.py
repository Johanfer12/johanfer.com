from django.contrib import admin
from django.urls import path, include 
from django.shortcuts import redirect

urlpatterns = [
    path('favicon.ico', lambda _ : redirect('static/favicon.ico', permanent=True)),
    path('j_admin/', admin.site.urls),  
    path('', include('home_page.urls')),  #Urls de home_page
    path('spotify/', include('spotify.urls')),  #Urls de spotify
    path('noticias/', include('my_news.urls')),  # Nueva ruta para las noticias
]

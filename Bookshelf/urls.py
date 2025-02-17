from django.contrib import admin
from django.urls import path, include 

urlpatterns = [
    path('j_admin/', admin.site.urls),  
    path('', include('home_page.urls')),  #Urls de home_page
    path('spotify/', include('spotify.urls')),  #Urls de spotify
    path('noticias/', include('my_news.urls')),  # Nueva ruta para las noticias
]

from django.contrib import admin
from django.urls import path, include  # Importa la función include

urlpatterns = [
    #path('admin/', admin.site.urls),
    path('', include('home_page.urls')),  #Urls de home_page
    path('spotify/', include('spotify.urls')),  #Urls de spotify
]

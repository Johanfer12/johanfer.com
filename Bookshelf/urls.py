from django.contrib import admin
from django.urls import path, include
from django.shortcuts import redirect
from django.conf import settings
from django.conf.urls.static import static
from home_page.views import custom_404_view

urlpatterns = [
    path('favicon.ico', lambda _ : redirect('static/favicon.ico', permanent=True)),
    path('j_admin/', admin.site.urls),
    path('', include('home_page.urls')),  #Urls de home_page
    path('spotify/', include('spotify.urls')),  #Urls de spotify
    path('noticias/', include('my_news.urls')),  # Nueva ruta para las noticias
]

# Servir archivos media en desarrollo
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

handler404 = custom_404_view

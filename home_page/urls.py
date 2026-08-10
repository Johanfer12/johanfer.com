from django.urls import path
from . import views

app_name = 'home_page'

urlpatterns = [
    path('', views.home, name='index'),
    path('robots.txt', views.robots_txt, name='robots_txt'),
    # El manifiesto y el service worker cuelgan de la raíz: el ámbito de un
    # service worker no puede subir por encima de la ruta desde la que se sirve.
    path('manifest.webmanifest', views.manifest_webmanifest, name='manifest'),
    path('sw.js', views.service_worker, name='service_worker'),
    path('offline/', views.offline, name='offline'),
    path('sitemap.xml', views.sitemap_xml, name='sitemap_xml'),
    path('bookshelf/', views.bookshelf, name='bookshelf'),
    path('visitas/', views.visits, name='visits'),
    path('bookshelf/stats/', views.stats, name='stats'),
    path('about/', views.about, name='about'),
]

handler404 = views.custom_404_view

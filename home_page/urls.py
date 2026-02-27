from django.urls import path
from . import views

app_name = 'home_page'

urlpatterns = [
    path('', views.home, name='index'),
    path('robots.txt', views.robots_txt, name='robots_txt'),
    path('sitemap.xml', views.sitemap_xml, name='sitemap_xml'),
    path('bookshelf/', views.bookshelf, name='bookshelf'),
    path('bookshelf/stats/', views.stats, name='stats'),
    path('about/', views.about, name='about'),
]

handler404 = views.custom_404_view

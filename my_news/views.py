from django.shortcuts import render
from django.views.generic import ListView, DetailView
from .models import News, FeedSource
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.shortcuts import get_object_or_404
from django.template.loader import render_to_string
from .services import FeedService
from django.contrib import messages
from django.contrib.auth.decorators import user_passes_test
from django.utils.decorators import method_decorator
from django.shortcuts import redirect
import json
from django.utils import timezone
from datetime import datetime

# Create your views here.

@require_POST
def delete_news(request, pk):
    news = get_object_or_404(News, pk=pk)
    news.is_deleted = True
    news.save()
    
    # Obtener la siguiente noticia que no está en la página actual
    page_size = 25
    current_page = int(request.POST.get('current_page', 1))
    offset = (current_page - 1) * page_size + page_size  # Calculamos el offset basado en la página actual
    
    # Calcular el total de noticias después de la eliminación
    total_news = News.objects.filter(is_deleted=False).count()
    
    # Calcular el total de páginas
    total_pages = (total_news + page_size - 1) // page_size  # Redondear hacia arriba
    
    next_news = News.objects.filter(is_deleted=False).order_by('-published_date')[offset-1:offset].first()
    
    if next_news:
        # Renderizar la nueva tarjeta de noticia
        html = render_to_string('news_card.html', {'article': next_news}, request=request)
        # Renderizar el modal de la nueva noticia
        modal_html = render_to_string('news_modal.html', {'article': next_news}, request=request)
        
        return JsonResponse({
            'status': 'success',
            'html': html,
            'modal': modal_html,
            'newsId': next_news.pk,
            'total_news': total_news,
            'total_pages': total_pages
        })
    
    return JsonResponse({
        'status': 'success', 
        'html': None,
        'total_news': total_news,
        'total_pages': total_pages
    })

def superuser_required(view_func):
    decorated_view = user_passes_test(lambda u: u.is_superuser, login_url='/')(view_func)
    return decorated_view

@method_decorator(superuser_required, name='dispatch')
class NewsListView(ListView):
    model = News
    template_name = 'news_list.html'
    context_object_name = 'news'
    paginate_by = 25

    def get_queryset(self):
        return News.objects.filter(is_deleted=False)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['sources'] = FeedSource.objects.filter(active=True)
        context['total_news'] = News.objects.filter(is_deleted=False).count()
        return context

def update_feed(request):
    try:
        new_articles = FeedService.fetch_and_save_news()
        # Obtener el total actualizado de noticias
        total_news = News.objects.filter(is_deleted=False).count()
        
        # Calcular el total de páginas
        page_size = 25
        total_pages = (total_news + page_size - 1) // page_size  # Redondear hacia arriba
        
        message = f'Feed actualizado: {new_articles} nueva{"s" if new_articles != 1 else ""} noticia{"s" if new_articles != 1 else ""} encontrada{"s" if new_articles != 1 else ""}'
        return JsonResponse({
            'status': 'success',
            'message': message,
            'total_news': total_news,
            'total_pages': total_pages
        })
    except Exception as e:
        return JsonResponse({
            'status': 'error',
            'message': f'Error al actualizar el feed: {str(e)}'
        }, status=500)

def check_new_news(request):
    """
    Endpoint para verificar si hay noticias nuevas desde la última vez que el cliente verificó.
    Devuelve las nuevas noticias formateadas para ser insertadas en la interfaz.
    """
    try:
        # Obtener la fecha de la última noticia en la página actual
        last_checked = request.GET.get('last_checked')
        
        if not last_checked:
            return JsonResponse({'status': 'error', 'message': 'Falta el parámetro last_checked'})
        
        # Buscar noticias más recientes que la última revisada
        # Ordenamos por fecha de publicación descendente para tener las más recientes primero
        new_news = News.objects.filter(
            is_deleted=False,
            created_at__gt=last_checked
        ).order_by('-published_date')[:25]  # Límite de 25 para no sobrecargar
        
        if not new_news.exists():
            return JsonResponse({'status': 'no_new_news'})
        
        # Obtener el total de noticias
        total_news = News.objects.filter(is_deleted=False).count()
        
        # Calcular número total de páginas
        page_size = 25
        total_pages = (total_news + page_size - 1) // page_size  # Redondear hacia arriba
        
        # Renderizar las nuevas noticias (mantienen el orden del queryset)
        news_cards_html = []
        for article in new_news:
            html = render_to_string('news_card.html', {'article': article}, request=request)
            modal_html = render_to_string('news_modal.html', {'article': article}, request=request)
            news_cards_html.append({
                'card': html, 
                'modal': modal_html,
                'id': article.id
            })
        
        return JsonResponse({
            'status': 'success',
            'new_news_count': len(news_cards_html),
            'news_cards': news_cards_html,
            'current_time': str(timezone.now()),
            'total_news': total_news,
            'total_pages': total_pages
        })
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)

def get_news_count(request):
    """Obtiene el conteo actualizado de noticias"""
    total_news = News.objects.filter(is_deleted=False).count()
    total_pages = (total_news + 24) // 25  # Cálculo del número total de páginas (25 noticias por página)
    
    return JsonResponse({
        'status': 'success',
        'total_news': total_news,
        'total_pages': total_pages
    })


from django.shortcuts import render
from django.views.generic import ListView
from .models import News
from django.http import JsonResponse
from django.views.decorators.http import require_POST, require_GET
from django.template.loader import render_to_string
from .services import FeedService, EmbeddingService
from django.contrib.auth.decorators import user_passes_test
from django.utils.decorators import method_decorator
from django.utils import timezone
import pytz
from django.db.models import Q

# Create your views here.

@require_POST
def delete_news(request, pk):
    try:
        current_page = int(request.POST.get('current_page', 1))
        news = News.objects.get(pk=pk)
        news.is_deleted = True
        news.save()
        
        # Definir el filtro base para noticias visibles
        visible_news_filter = Q(is_deleted=False) & Q(is_filtered=False) & Q(is_ai_filtered=False) & Q(is_redundant=False)
        
        # Obtener la siguiente noticia para reemplazar la eliminada
        next_news = None
        total_news = News.objects.filter(visible_news_filter).count()
        total_pages = (total_news + 24) // 25  # Calcular el total de páginas
        
        # Calcular el offset para obtener la noticia que está justo fuera de la página actual
        offset = current_page * 25
        if offset < total_news:
            next_news = News.objects.filter(visible_news_filter).order_by('-published_date')[offset:offset+1].first()
        
        response_data = {
            'status': 'success',
            'total_news': total_news,
            'total_pages': total_pages
        }
        
        # Si hay una noticia para reemplazar, incluirla en la respuesta
        if next_news:
            card_html = render_to_string('news_card.html', {'article': next_news, 'user': request.user})
            modal_html = render_to_string('news_modal.html', {'article': next_news, 'user': request.user})
            response_data['html'] = card_html
            response_data['modal'] = modal_html
        
        return JsonResponse(response_data)
    except News.DoesNotExist:
        return JsonResponse({'status': 'error', 'message': 'Noticia no encontrada'})
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)})

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
        # Aplicar todos los filtros para noticias visibles
        return News.objects.filter(
            is_deleted=False,
            is_filtered=False,
            is_ai_filtered=False,
            is_redundant=False
        ).order_by('-published_date')
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # Usar el mismo filtro para el conteo total
        total_news = News.objects.filter(
            is_deleted=False,
            is_filtered=False,
            is_ai_filtered=False,
            is_redundant=False
        ).count()
        context['total_news'] = total_news
        return context

@require_GET
def update_feed(request):
    try:
        new_articles = FeedService.fetch_and_save_news()
        # Usar el filtro completo para el conteo
        total_news = News.objects.filter(
            is_deleted=False,
            is_filtered=False,
            is_ai_filtered=False,
            is_redundant=False
        ).count()
        total_pages = (total_news + 24) // 25  # Calcular el total de páginas
        
        return JsonResponse({
            'status': 'success',
            'message': f'Feed actualizado. {new_articles} nuevos artículos obtenidos.',
            'total_news': total_news,
            'total_pages': total_pages
        })
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)})

@require_GET
def check_new_news(request):
    try:
        last_checked = request.GET.get('last_checked')
        current_time = timezone.now().isoformat()
        
        # Definir el filtro base para noticias visibles
        visible_news_filter = Q(is_deleted=False) & Q(is_filtered=False) & Q(is_ai_filtered=False) & Q(is_redundant=False)

        # Obtener noticias nuevas desde la última comprobación, aplicando el filtro completo
        new_news = News.objects.filter(
            visible_news_filter, 
            created_at__gte=last_checked
        ).order_by('-published_date')
        
        # Preparar los datos de las tarjetas
        news_cards = []
        for article in new_news:
            card_html = render_to_string('news_card.html', {'article': article, 'user': request.user})
            modal_html = render_to_string('news_modal.html', {'article': article, 'user': request.user})
            news_cards.append({
                'id': article.id,
                'card': card_html,
                'modal': modal_html
            })
        
        # Obtener el total actualizado de noticias visibles
        total_news = News.objects.filter(visible_news_filter).count()
        total_pages = (total_news + 24) // 25  # Calcular el total de páginas
        
        return JsonResponse({
            'status': 'success',
            'current_time': current_time,
            'news_cards': news_cards,
            'total_news': total_news,
            'total_pages': total_pages
        })
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)})

@require_GET
def get_news_count(request):
    try:
        # Usar el filtro completo para el conteo
        total_news = News.objects.filter(
            is_deleted=False,
            is_filtered=False,
            is_ai_filtered=False,
            is_redundant=False
        ).count()
        total_pages = (total_news + 24) // 25  # Calcular el total de páginas
        
        return JsonResponse({
            'status': 'success',
            'total_news': total_news,
            'total_pages': total_pages
        })
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)})

@require_GET
def test_redundancy(request):
    """Vista para probar la detección de redundancia en noticias"""
    try:
        # Obtener fecha de hoy en GMT-5
        bogota_tz = pytz.timezone('America/Bogota')  # Bogotá es GMT-5
        today = timezone.now().astimezone(bogota_tz).date()
        
        # Obtener noticias redundantes
        redundant_news = News.objects.filter(
            is_redundant=True, 
            similar_to__isnull=False
        ).select_related('similar_to', 'source').order_by('-created_at')[:20]
        
        # Contar noticias redundantes de hoy
        # Necesitamos comparar en la zona horaria correcta
        today_start = timezone.datetime.combine(today, timezone.datetime.min.time())
        today_start = bogota_tz.localize(today_start)
        today_end = timezone.datetime.combine(today, timezone.datetime.max.time())
        today_end = bogota_tz.localize(today_end)
        
        redundant_today = News.objects.filter(
            is_redundant=True,
            published_date__gte=today_start,
            published_date__lte=today_end
        ).count()
        
        # Preparar el contexto
        context = {
            'redundant_news': redundant_news,
            'total_redundant': News.objects.filter(is_redundant=True).count(),
            'redundant_today': redundant_today,
            'current_date': today
        }
        
        return render(request, 'redundancy_test.html', context)
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)})

@require_GET
def generate_embeddings(request):
    """Vista para generar embeddings para noticias existentes"""
    try:
        # Inicializar modelo
        embedding_model_name = EmbeddingService.initialize_embedding_model()
        
        # Obtener noticias sin embedding
        news_without_embedding = News.objects.filter(
            embedding__isnull=True,
            is_deleted=False,
            is_filtered=False
        ).order_by('-published_date')[:50]  # Limitar a 50 para evitar sobrecarga
        
        processed_count = 0
        for news in news_without_embedding:
            # Combinar título y descripción para el embedding
            content = f"{news.title} {news.description}"
            embedding = EmbeddingService.generate_embedding(content, embedding_model_name)
            
            if embedding:
                news.embedding = embedding
                news.save(update_fields=['embedding'])
                processed_count += 1
        
        return JsonResponse({
            'status': 'success',
            'processed_count': processed_count,
            'remaining': News.objects.filter(embedding__isnull=True, is_deleted=False, is_filtered=False).count()
        })
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)})

@require_GET
def check_all_redundancy(request):
    """Vista para verificar redundancia en todas las noticias con embeddings"""
    try:
        # Inicializar modelo
        embedding_model_name = EmbeddingService.initialize_embedding_model()
        
        # Obtener noticias no marcadas como redundantes
        news_to_check = News.objects.filter(
            is_redundant=False,
            embedding__isnull=False,
            is_deleted=False,
            is_filtered=False
        ).order_by('-published_date')[:100]  # Limitar a 100 para evitar sobrecarga
        
        redundant_count = 0
        for news in news_to_check:
            is_redundant, similar_news, similarity_score = EmbeddingService.check_redundancy(
                news, embedding_model_name
            )
            
            if is_redundant and similar_news:
                news.is_redundant = True
                news.is_filtered = True  # Usamos is_filtered en lugar de is_deleted
                news.similar_to = similar_news
                news.similarity_score = similarity_score
                news.save()
                redundant_count += 1
        
        return JsonResponse({
            'status': 'success',
            'redundant_count': redundant_count,
            'total_checked': len(news_to_check)
        })
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)})


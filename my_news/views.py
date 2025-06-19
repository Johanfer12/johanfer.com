from django.shortcuts import render
from django.views.generic import ListView
from .models import News
from django.http import JsonResponse
from django.views.decorators.http import require_POST, require_GET
from django.template.loader import render_to_string
from .services import FeedService, EmbeddingService
from django.contrib.auth.decorators import user_passes_test
from django.contrib.auth.views import LoginView
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
    decorated_view = user_passes_test(lambda u: u.is_superuser, login_url='/noticias/login/')(view_func)
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
        # Obtener fecha de hoy en la zona horaria correcta (America/Bogota)
        bogota_tz = pytz.timezone('America/Bogota')
        today_local = timezone.now().astimezone(bogota_tz).date()
        today_start_utc = bogota_tz.localize(timezone.datetime.combine(today_local, timezone.datetime.min.time())).astimezone(pytz.utc)
        today_end_utc = bogota_tz.localize(timezone.datetime.combine(today_local, timezone.datetime.max.time())).astimezone(pytz.utc)

        # Queryset base para noticias creadas hoy
        news_today_qs = News.objects.filter(
            created_at__gte=today_start_utc,
            created_at__lte=today_end_utc
        )
        total_today = news_today_qs.count()

        # Obtener noticias redundantes del día (para mostrar la lista)
        redundant_news_today_list = News.objects.filter(
            is_redundant=True,
            similar_to__isnull=False,
            created_at__gte=today_start_utc,
            created_at__lte=today_end_utc
        ).select_related('similar_to', 'source', 'similar_to__source').order_by('-created_at')

        # Obtener listas de noticias para cada pestaña
        # 1. Noticias filtradas por keywords (pero no redundantes ni IA)
        keyword_filtered_news = news_today_qs.filter(
            filtered_by__isnull=False,
            is_redundant=False,
            is_ai_filtered=False
        ).select_related('source', 'filtered_by').order_by('-created_at')

        # 2. Noticias filtradas por IA (pero no redundantes)
        ai_filtered_news = news_today_qs.filter(
            is_ai_filtered=True,
            is_redundant=False
        ).select_related('source').order_by('-created_at')

        # Calcular estadísticas para la barra (lógica revisada para exclusividad)
        if total_today > 0:
            # 1. Redundantes (máxima prioridad)
            redundant_today_count = news_today_qs.filter(is_redundant=True).count()

            # 2. Filtradas IA (pero NO redundantes)
            filtered_ai_today_count = news_today_qs.filter(
                is_ai_filtered=True,
                is_redundant=False
            ).count()

            # 3. Filtradas Keyword (pero NO redundantes NI IA)
            filtered_keyword_today_count = news_today_qs.filter(
                filtered_by__isnull=False,
                is_redundant=False,
                is_ai_filtered=False
            ).count()

            # 4. Visibles (las restantes: no redundantes, no IA, no keyword)
            # Simplificado: Total - Redundantes - Filtradas IA - Filtradas Keyword
            visible_today_count = total_today - redundant_today_count - filtered_ai_today_count - filtered_keyword_today_count
            # Asegurar que no sea negativo por algún caso extraño
            visible_today_count = max(0, visible_today_count)

            # Verificación (opcional, pero útil para depurar)
            calculated_total = visible_today_count + filtered_keyword_today_count + filtered_ai_today_count + redundant_today_count
            if calculated_total != total_today:
                 # Si esto sigue ocurriendo, hay un estado de noticia no contemplado
                 print(f"Advertencia [LOGICA EXCLUSIVA]: Suma ({calculated_total}) no coincide con total ({total_today}).")
                 # Como fallback, ajustamos visibles para cuadrar, aunque indica un problema subyacente
                 visible_today_count = total_today - filtered_keyword_today_count - filtered_ai_today_count - redundant_today_count
                 visible_today_count = max(0, visible_today_count)

            # Calcular porcentajes
            visible_perc = (visible_today_count / total_today) * 100 if total_today > 0 else 0
            keyword_perc = (filtered_keyword_today_count / total_today) * 100 if total_today > 0 else 0
            ai_perc = (filtered_ai_today_count / total_today) * 100 if total_today > 0 else 0
            redundant_perc = (redundant_today_count / total_today) * 100 if total_today > 0 else 0
        else:
            visible_today_count = 0
            filtered_keyword_today_count = 0
            filtered_ai_today_count = 0
            redundant_today_count = 0
            visible_perc = 0
            keyword_perc = 0
            ai_perc = 0
            redundant_perc = 0

        # Total general de redundantes histórico
        total_redundant_all_time = News.objects.filter(is_redundant=True).count()

        # Preparar el contexto
        context = {
            'redundant_news': redundant_news_today_list, # Lista para mostrar abajo
            'keyword_filtered_news': keyword_filtered_news,  # Nueva variable para la pestaña de keywords
            'ai_filtered_news': ai_filtered_news,  # Nueva variable para la pestaña de IA
            'total_redundant': total_redundant_all_time,
            'current_date': today_local,
            'total_today': total_today,
            'visible_today_count': visible_today_count, # Contiene el recuento recalculado
            'filtered_keyword_today_count': filtered_keyword_today_count, # Contiene el recuento exclusivo
            'filtered_ai_today_count': filtered_ai_today_count,       # Contiene el recuento exclusivo
            'redundant_today_count': redundant_today_count,          # Contiene el recuento total redundante
            'visible_perc': visible_perc,
            'keyword_perc': keyword_perc,
            'ai_perc': ai_perc,
            'redundant_perc': redundant_perc,
        }

        return render(request, 'redundancy_test.html', context)
    except Exception as e:
        # Considera loguear el error aquí para depuración
        print(f"Error en test_redundancy: {str(e)}") # Log simple
        # Podrías devolver una página de error o un JsonResponse
        # Para mantener la consistencia con la plantilla, podrías renderizarla con un mensaje de error
        return render(request, 'redundancy_test.html', {'error_message': f'Ocurrió un error: {str(e)}'})

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

# Vista de Login Personalizada
class NewsLoginView(LoginView):
    template_name = 'news_login.html' # Apuntar al archivo creado por el usuario
    redirect_authenticated_user = True # Redirigir si ya está autenticado


from django.shortcuts import render
from django.views.generic import ListView
from .models import News, FeedSource
from django.http import JsonResponse
from django.views.decorators.http import require_POST, require_GET
from django.template.loader import render_to_string
from .services import FeedService, EmbeddingService
from django.contrib.auth.decorators import user_passes_test
from django.contrib.auth.views import LoginView
from django.utils.decorators import method_decorator
from django.utils import timezone
import pytz
from django.db.models import Q, Count
from .tasks import purge_old_news, retry_summarize_pending

# Create your views here.

@require_POST
def delete_news(request, pk):
    try:
        current_page = int(request.POST.get('current_page', 1))
        order = request.POST.get('order', 'desc')
        news = News.objects.get(pk=pk)
        news.is_deleted = True
        news.save()
        
        # Obtener la siguiente noticia para reemplazar la eliminada
        next_news = None
        total_news = News.visible.count()
        total_pages = (total_news + 24) // 25  # Calcular el total de páginas
        
        # Buscar noticia de reemplazo por keyset para mantener orden estable (siempre, también en descendente página 1)
        base_qs = News.visible.order_by('published_date' if order == 'asc' else '-published_date')
        page_start = (current_page - 1) * 25
        page_qs = list(base_qs[page_start:page_start + 25])
        if page_qs:
            anchor = page_qs[-1]
            if order == 'asc':
                keyset_q = (
                    Q(published_date__gt=anchor.published_date) |
                    (Q(published_date=anchor.published_date) & Q(id__gt=anchor.id))
                )
                ordering = 'published_date'
            else:
                keyset_q = (
                    Q(published_date__lt=anchor.published_date) |
                    (Q(published_date=anchor.published_date) & Q(id__lt=anchor.id))
                )
                ordering = '-published_date'
            next_news = News.visible.filter(keyset_q).order_by(ordering).first()
        
        response_data = {
            'status': 'success',
            'total_news': total_news,
            'total_pages': total_pages
        }
        
        # Si hay una noticia para reemplazar, incluirla en la respuesta
        if next_news:
            print(f"[DEBUG] Noticia de reemplazo encontrada: ID={next_news.id}, Título={next_news.title[:50]}...")
            card_html = render_to_string('news_card.html', {'article': next_news, 'user': request.user})
            modal_html = render_to_string('news_modal.html', {'article': next_news, 'user': request.user})
            response_data['html'] = card_html
            response_data['modal'] = modal_html
        else:
            print(f"[DEBUG] No se encontró noticia de reemplazo. Página: {current_page}, Total noticias: {total_news}")
        
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
    paginate_by = 25

    def get_queryset(self):
        # Usar el manager optimizado + búsqueda y orden dinámico
        order = self.request.GET.get('order', 'desc')
        search_query = self.request.GET.get('q')

        queryset = News.visible.select_related('source')
        if search_query:
            queryset = queryset.filter(
                Q(title__icontains=search_query) | Q(description__icontains=search_query)
            )

        if order == 'asc':
            queryset = queryset.order_by('published_date', 'id')
        else:
            queryset = queryset.order_by('-published_date', '-id')

        return queryset
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        # Reutilizar el count de paginación que ya calcula Django
        # En lugar de hacer self.get_queryset().count() duplicado
        total_news = context['paginator'].count
        context['total_news'] = total_news
        
        # Obtener página actual
        page = self.request.GET.get('page', 1)
        try:
            current_page = int(page)
        except (ValueError, TypeError):
            current_page = 1
            
        # Obtener noticias de respaldo (5 adicionales) por keyset (cursor) a partir del último ítem de la página
        order = self.request.GET.get('order', 'desc')
        ordering = 'published_date' if order == 'asc' else '-published_date'
        page_qs = list(self.get_queryset()[(current_page - 1) * 25: (current_page - 1) * 25 + 25])
        last_item = page_qs[-1] if page_qs else None  # último en la página independientemente del orden
        backup_news = []
        if last_item:
            if order == 'asc':
                backup_q = (
                    Q(published_date__gt=last_item.published_date) |
                    (Q(published_date=last_item.published_date) & Q(id__gt=last_item.id))
                )
            else:
                backup_q = (
                    Q(published_date__lt=last_item.published_date) |
                    (Q(published_date=last_item.published_date) & Q(id__lt=last_item.id))
                )
            backup_news = News.visible.select_related('source').filter(backup_q).order_by(ordering)[:5]
        
        # Renderizar noticias de respaldo como HTML para JavaScript
        backup_cards = []
        for article in backup_news:
            card_html = render_to_string('news_card.html', {'article': article, 'user': self.request.user})
            modal_html = render_to_string('news_modal.html', {'article': article, 'user': self.request.user})
            backup_cards.append({
                'id': article.id,
                'card': card_html,
                'modal': modal_html
            })
        
        context['backup_cards'] = backup_cards
        context['current_page'] = current_page
        context['order'] = order
        
        return context

@require_GET
def update_feed(request):
    try:
        # Reintentar completar resúmenes pendientes antes de buscar nuevas
        try:
            retry_summarize_pending(limit=50, days=15)
        except Exception as _:
            pass
        new_articles = FeedService.fetch_and_save_news()
        # Usar el manager optimizado
        total_news = News.visible.count()
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

        # Obtener noticias nuevas desde la última comprobación
        new_news = News.visible.filter(
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
        total_news = News.visible.count()
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
        # Usar el manager optimizado
        total_news = News.visible.count()
        total_pages = (total_news + 24) // 25  # Calcular el total de páginas
        
        return JsonResponse({
            'status': 'success',
            'total_news': total_news,
            'total_pages': total_pages
        })
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)})


@require_POST
@user_passes_test(lambda u: u.is_superuser, login_url='/noticias/login/')
def cleanup_old_news(request):
    try:
        days = int(request.POST.get('days', 15))
        removed = purge_old_news(days)
        total_news = News.visible.count()
        total_pages = (total_news + 24) // 25
        return JsonResponse({'status': 'success', 'removed': removed, 'total_news': total_news, 'total_pages': total_pages})
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)})


@require_POST
@user_passes_test(lambda u: u.is_superuser, login_url='/noticias/login/')
def retry_summaries(request):
    try:
        limit = int(request.POST.get('limit', 50))
        days = int(request.POST.get('days', 2))
        processed = retry_summarize_pending(limit=limit, days=days)
        return JsonResponse({'status': 'success', 'processed': processed})
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)})


@require_GET
def get_page(request):
    try:
        # Keyset pagination completa con cursor
        order = request.GET.get('order', 'desc')
        search_query = request.GET.get('q')
        page = int(request.GET.get('page', 1))  # fallback compat
        cursor = request.GET.get('cursor')  # formato: "timestamp_iso|id"

        base_qs = News.visible.select_related('source')
        if search_query:
            base_qs = base_qs.filter(
                Q(title__icontains=search_query) | Q(description__icontains=search_query)
            )

        # Orden estable por (published_date, id)
        if order == 'asc':
            base_qs = base_qs.order_by('published_date', 'id')
        else:
            base_qs = base_qs.order_by('-published_date', '-id')

        # Aplicar cursor si viene
        if cursor:
            try:
                ts_str, id_str = cursor.split('|')
                from django.utils.dateparse import parse_datetime
                anchor_dt = parse_datetime(ts_str)
                anchor_id = int(id_str)
                if order == 'asc':
                    key_q = Q(published_date__gt=anchor_dt) | (Q(published_date=anchor_dt) & Q(id__gt=anchor_id))
                else:
                    key_q = Q(published_date__lt=anchor_dt) | (Q(published_date=anchor_dt) & Q(id__lt=anchor_id))
                base_qs = base_qs.filter(key_q)
            except Exception:
                pass
        elif page and page > 1:
            # Fallback: derivar cursor desde page N por ancla del último ítem de la página anterior
            anchor_idx = (page - 1) * 25 - 1
            if anchor_idx >= 0:
                prev_slice = list(base_qs[:anchor_idx + 1])
                if prev_slice:
                    anchor = prev_slice[-1]
                    if order == 'asc':
                        key_q = Q(published_date__gt=anchor.published_date) | (Q(published_date=anchor.published_date) & Q(id__gt=anchor.id))
                    else:
                        key_q = Q(published_date__lt=anchor.published_date) | (Q(published_date=anchor.published_date) & Q(id__lt=anchor.id))
                    base_qs = base_qs.filter(key_q)

        page_size = 25
        window_qs = base_qs  # conservar para backup
        items = list(window_qs[:page_size + 1])  # pedir uno extra para construir next_cursor
        has_more = len(items) > page_size
        items = items[:page_size]

        cards = []
        for article in items:
            card_html = render_to_string('news_card.html', {'article': article, 'user': request.user})
            modal_html = render_to_string('news_modal.html', {'article': article, 'user': request.user})
            cards.append({'id': article.id, 'card': card_html, 'modal': modal_html})

        # Construir next_cursor
        next_cursor = None
        if has_more:
            last = items[-1]
            next_cursor = f"{last.published_date.isoformat()}|{last.id}"

        # Preparar backups por keyset - cargar más noticias para respaldo fluido
        backup_cards = []
        try:
            # Si es página 1, cargar las siguientes 25 noticias como respaldo
            backup_size = 25 if page == 1 else 5
            backup_qs = list(window_qs[page_size:page_size + backup_size])
            for article in backup_qs:
                card_html = render_to_string('news_card.html', {'article': article, 'user': request.user})
                modal_html = render_to_string('news_modal.html', {'article': article, 'user': request.user})
                backup_cards.append({'id': article.id, 'card': card_html, 'modal': modal_html})
        except Exception:
            pass

        # Conteo total independiente del cursor
        count_qs = News.visible
        if search_query:
            count_qs = count_qs.filter(Q(title__icontains=search_query) | Q(description__icontains=search_query))
        total_news = count_qs.count()
        total_pages = (total_news + 24) // 25

        

        # Si se solicita solo backup, devolver las siguientes 25 noticias desde el cursor actual
        backup_only = request.GET.get('backup_only', 'false').lower() == 'true'
        if backup_only:
            # Para backup_only, devolver hasta 25 noticias adicionales
            additional_backup = list(window_qs[page_size:page_size + 25])
            backup_cards = []
            for article in additional_backup:
                card_html = render_to_string('news_card.html', {'article': article, 'user': request.user})
                modal_html = render_to_string('news_modal.html', {'article': article, 'user': request.user})
                backup_cards.append({'id': article.id, 'card': card_html, 'modal': modal_html})
            
            return JsonResponse({
                'status': 'success',
                'backup_cards': backup_cards,
                'total_news': total_news,
                'total_pages': total_pages,
                'order': order
            })
        
        return JsonResponse({
            'status': 'success',
            'cards': cards,
            'next_cursor': next_cursor,
            'backup_cards': backup_cards,
            'total_news': total_news,
            'total_pages': total_pages,
            'order': order
        })
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)})


@require_POST
def undo_delete(request, pk):
    try:
        news = News.objects.get(pk=pk)
        if news.is_deleted:
            news.is_deleted = False
            # Restauramos cualquier marca de filtrado manual
            news.is_filtered = False
            news.is_ai_filtered = False
            news.is_redundant = False
            news.save()

        card_html = render_to_string('news_card.html', {'article': news, 'user': request.user})
        modal_html = render_to_string('news_modal.html', {'article': news, 'user': request.user})

        total_news = News.visible.count()
        total_pages = (total_news + 24) // 25

        return JsonResponse({
            'status': 'success',
            'html': card_html,
            'modal': modal_html,
            'total_news': total_news,
            'total_pages': total_pages
        })
    except News.DoesNotExist:
        return JsonResponse({'status': 'error', 'message': 'Noticia no encontrada'})
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)})



@require_GET
def test_redundancy(request):
    """Vista para probar la detección de redundancia en noticias"""
    try:
        # Obtener fecha seleccionada o fecha de hoy
        bogota_tz = pytz.timezone('America/Bogota')
        selected_date_str = request.GET.get('date')

        if selected_date_str:
            try:
                selected_date = timezone.datetime.strptime(selected_date_str, '%Y-%m-%d').date()
            except ValueError:
                selected_date = timezone.now().astimezone(bogota_tz).date()
        else:
            selected_date = timezone.now().astimezone(bogota_tz).date()

        # Convertir a UTC para consultas
        today_start_utc = bogota_tz.localize(timezone.datetime.combine(selected_date, timezone.datetime.min.time())).astimezone(pytz.utc)
        today_end_utc = bogota_tz.localize(timezone.datetime.combine(selected_date, timezone.datetime.max.time())).astimezone(pytz.utc)

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

        # Calcular estadísticas de redundancia por fuente
        source_stats = []
        sources = FeedSource.objects.filter(active=True)

        for source in sources:
            # Total de noticias de esta fuente hoy
            source_total_today = news_today_qs.filter(source=source).count()

            if source_total_today > 0:
                # Noticias redundantes de esta fuente hoy
                source_redundant_today = news_today_qs.filter(
                    source=source,
                    is_redundant=True
                ).count()

                # Calcular porcentaje de redundancia
                redundancy_percentage = (source_redundant_today / source_total_today) * 100

                source_stats.append({
                    'name': source.name,
                    'total_today': source_total_today,
                    'redundant_today': source_redundant_today,
                    'redundancy_percentage': redundancy_percentage,
                    'non_redundant_today': source_total_today - source_redundant_today
                })

        # Ordenar por porcentaje de redundancia descendente
        source_stats.sort(key=lambda x: x['redundancy_percentage'], reverse=True)

        # Preparar el contexto
        context = {
            'redundant_news': redundant_news_today_list, # Lista para mostrar abajo
            'keyword_filtered_news': keyword_filtered_news,  # Nueva variable para la pestaña de keywords
            'ai_filtered_news': ai_filtered_news,  # Nueva variable para la pestaña de IA
            'total_redundant': total_redundant_all_time,
            'current_date': selected_date,
            'total_today': total_today,
            'visible_today_count': visible_today_count, # Contiene el recuento recalculado
            'filtered_keyword_today_count': filtered_keyword_today_count, # Contiene el recuento exclusivo
            'filtered_ai_today_count': filtered_ai_today_count,       # Contiene el recuento exclusivo
            'redundant_today_count': redundant_today_count,          # Contiene el recuento total redundante
            'visible_perc': visible_perc,
            'keyword_perc': keyword_perc,
            'ai_perc': ai_perc,
            'redundant_perc': redundant_perc,
            'source_stats': source_stats,  # Nuevas estadísticas por fuente
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
        
        # Obtener noticias sin embedding usando el manager visible
        news_without_embedding = News.visible.filter(
            embedding__isnull=True
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
            'remaining': News.visible.filter(embedding__isnull=True).count()
        })
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)})

@require_GET
def check_all_redundancy(request):
    """Vista para verificar redundancia en todas las noticias con embeddings"""
    try:
        # Inicializar modelo
        embedding_model_name = EmbeddingService.initialize_embedding_model()
        
        # Obtener noticias no marcadas como redundantes usando el manager visible
        news_to_check = News.visible.filter(
            embedding__isnull=False
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


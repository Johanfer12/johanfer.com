from django.shortcuts import render
from django.views.generic import ListView, DetailView
from .models import News, FeedSource
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.shortcuts import get_object_or_404
from django.template.loader import render_to_string
from .services import FeedService
from django.contrib import messages

# Create your views here.

@require_POST
def delete_news(request, pk):
    news = get_object_or_404(News, pk=pk)
    news.is_deleted = True
    news.save()
    
    # Obtener la siguiente noticia que no está en la página actual
    page_size = 24
    current_page = int(request.POST.get('current_page', 1))
    offset = (current_page - 1) * page_size + page_size  # Calculamos el offset basado en la página actual
    
    next_news = News.objects.filter(is_deleted=False).order_by('-published_date')[offset-1:offset].first()
    
    if next_news:
        # Renderizar la nueva tarjeta de noticia
        html = render_to_string('news_card.html', {'article': next_news}, request=request)
        return JsonResponse({
            'status': 'success',
            'html': html,
            'newsId': next_news.pk
        })
    
    return JsonResponse({'status': 'success', 'html': None})

class NewsListView(ListView):
    model = News
    template_name = 'news_list.html'
    context_object_name = 'news'
    paginate_by = 24

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
        message = f'Feed actualizado: {new_articles} nueva{"s" if new_articles != 1 else ""} noticia{"s" if new_articles != 1 else ""} encontrada{"s" if new_articles != 1 else ""}'
        return JsonResponse({
            'status': 'success',
            'message': message
        })
    except Exception as e:
        return JsonResponse({
            'status': 'error',
            'message': f'Error al actualizar el feed: {str(e)}'
        }, status=500)

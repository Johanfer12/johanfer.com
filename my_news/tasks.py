from .services import FeedService
from django.utils import timezone
from datetime import timedelta
from .models import News
from .models import GeminiGlobalSetting

def update_news_cron():
    try:
        # Completar pendientes antes de traer nuevas
        try:
            retry_summarize_pending(limit=50, days=1)
        except Exception:
            pass
        FeedService.fetch_and_save_news()
        print("News data updated successfully")
        # Ejecutar limpieza tras actualización
        purge_old_news(15)
    except Exception as e:
        print(f"Error updating news data: {str(e)}") 


def purge_old_news(days: int = 15):
    """Elimina definitivamente noticias más viejas que 'days' días.
    Usa published_date como referencia.
    """
    try:
        cutoff = timezone.now() - timedelta(days=days)
        deleted_count, _ = News.objects.filter(published_date__lt=cutoff).delete()
        print(f"Purga completada: {deleted_count} noticias eliminadas (>{days} días)")
        return deleted_count
    except Exception as e:
        print(f"Error purgando noticias antiguas: {str(e)}")
        return 0


def retry_summarize_pending(limit: int = 50, days: int = 1):
    """Reintenta generar resumen/short_answer para noticias recientes sin procesar por IA."""
    try:
        client = FeedService.initialize_gemini()
        try:
            global_model_name = (GeminiGlobalSetting.objects.first() or GeminiGlobalSetting(model_name='gemini-2.0-flash')).model_name
        except Exception:
            global_model_name = 'gemini-2.0-flash'

        cutoff = timezone.now() - timedelta(days=days)
        qs = News.objects.filter(
            created_at__gte=cutoff,
            is_filtered=False,
            is_ai_filtered=False,
            short_answer__isnull=True,
        ).order_by('-created_at')[:limit]

        processed = 0
        for news in qs:
            processed_description, short_answer, ai_filter_reason = FeedService.process_content_with_gemini(
                news.title,
                news.description or '',
                client,
                global_model_name
            )

            if ai_filter_reason and isinstance(ai_filter_reason, str) and ai_filter_reason.strip():
                news.description = processed_description or news.description
                news.short_answer = short_answer
                news.is_filtered = True
                news.is_ai_filtered = True
                news.ai_filter_reason = ai_filter_reason.strip()
                news.save()
                processed += 1
                continue

            if processed_description:
                news.description = processed_description
            if short_answer is not None:
                news.short_answer = short_answer
            if processed_description or short_answer is not None:
                news.save()
                processed += 1

        print(f"Reintento resúmenes completado. Noticias procesadas: {processed}")
        return processed
    except Exception as e:
        print(f"Error en retry_summarize_pending: {str(e)}")
        return 0
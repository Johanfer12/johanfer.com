from .services import FeedService
from django.utils import timezone
from datetime import timedelta
from .models import News
from .models import GroqGlobalSetting
from .models import AIFilterInstruction

def update_news_cron():
    try:
        # Completar pendientes antes de traer nuevas
        try:
            retry_summarize_pending(limit=50, days=15)
        except Exception:
            pass
        FeedService.fetch_and_save_news()
        print("News data updated successfully")
        # Ejecutar limpieza tras actualizaciÃ³n
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
        print(f"Purga completada: {deleted_count} noticias eliminadas (> {days} días)")
        return deleted_count
    except Exception as e:
        print(f"Error purgando noticias antiguas: {str(e)}")
        return 0


def retry_summarize_pending(limit: int = 50, days: int = 15):
    """Reintenta generar resumen/short_answer para noticias recientes no filtradas por IA.

    Ampliado a una ventana de 15 días y sin depender de short_answer__isnull.
    Solo cuenta como procesada si se guardan cambios.
    """
    try:
        groq_client = FeedService.initialize_groq()
        try:
            global_model_name = (GroqGlobalSetting.objects.first() or GroqGlobalSetting(model_name='llama-3.3-70b-versatile')).model_name
        except Exception:
            global_model_name = 'llama-3.3-70b-versatile'

        try:
            filter_instructions_text = FeedService.build_filter_instructions_text(
                AIFilterInstruction.objects.filter(active=True)
            )
        except Exception:
            filter_instructions_text = FeedService._DEFAULT_FILTER_INSTRUCTIONS

        cutoff = timezone.now() - timedelta(days=days)
        qs = News.objects.filter(
            created_at__gte=cutoff,
            is_deleted=False,     # no reintentar si el usuario la eliminó
            is_ai_processed=False # solo las no procesadas por IA
        ).order_by('-created_at')[:limit]

        processed = 0
        for news in qs:
            saved_changes = False
            processed_description, short_answer, ai_filter_reason = FeedService.process_content_with_groq(
                news.title,
                news.description or '',
                groq_client,
                global_model_name,
                filter_instructions_text
            )

            if ai_filter_reason and isinstance(ai_filter_reason, str) and ai_filter_reason.strip():
                news.description = processed_description or news.description
                news.short_answer = short_answer
                news.is_filtered = True
                news.is_ai_filtered = True
                news.ai_filter_reason = ai_filter_reason.strip()
                news.is_ai_processed = True
                news.save()
                processed += 1
                continue

            # Actualizar solo si hay cambios reales
            new_description = processed_description if processed_description else news.description
            new_short_answer = short_answer if short_answer is not None else news.short_answer

            if (new_description != news.description) or (new_short_answer != news.short_answer):
                news.description = new_description
                news.short_answer = new_short_answer
                news.is_ai_processed = True
                news.save()
                processed += 1

        print(f"Reintento resÃºmenes completado. Noticias procesadas: {processed}")
        return processed
    except Exception as e:
        print(f"Error en retry_summarize_pending: {str(e)}")
        return 0

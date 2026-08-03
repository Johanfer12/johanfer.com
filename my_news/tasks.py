from .services import EmbeddingService, FeedService, DEFAULT_AI_MODEL
from .interest import INTEREST_DISTRIBUTION_CACHE_KEY, InterestModel, scored_population
from django.core.cache import cache
from django.utils import timezone
from datetime import timedelta
from .models import News
from .models import AIModelSetting
from .models import AIFilterInstruction
from django.conf import settings
from django.db import connection
import os
import portalocker
import logging


logger = logging.getLogger(__name__)


def purge_orphan_vectors(batch_size: int = 256):
    """Elimina de Qdrant puntos cuyo news_id ya no existe en la base de datos."""
    try:
        vector_index = FeedService.initialize_vector_index()
        if vector_index is None:
            return 0

        existing_news_ids = set(News.objects.values_list('id', flat=True))
        orphan_point_ids = []

        for point in vector_index.scroll_points(limit=batch_size):
            payload = getattr(point, 'payload', {}) or {}
            news_id = payload.get('news_id')
            if news_id is None:
                orphan_point_ids.append(point.id)
                continue

            try:
                normalized_news_id = int(news_id)
            except (TypeError, ValueError):
                orphan_point_ids.append(point.id)
                continue

            if normalized_news_id not in existing_news_ids:
                orphan_point_ids.append(point.id)

        deleted_vectors = 0
        for start in range(0, len(orphan_point_ids), batch_size):
            deleted_vectors += vector_index.delete_point_ids(
                orphan_point_ids[start:start + batch_size]
            )

        logger.info(f"Limpieza Qdrant completada: {deleted_vectors} vectores huérfanos eliminados")
        return deleted_vectors
    except Exception:
        logger.exception("Error limpiando vectores huérfanos en Qdrant")
        return 0

def retry_missing_embeddings(limit: int = 25, days: int = 15):
    """Indexa las noticias que se quedaron sin vector por un fallo puntual.

    Una noticia sin embedding es invisible para la detección de duplicados de
    todas las que vengan después, así que conviene recuperarla aunque su propio
    control de duplicados ya no se pueda deshacer.

    A propósito NO marca nada como redundante a posteriori: la noticia ya se
    publicó y el usuario puede haberla leído; hacerla desaparecer de la rejilla
    tiempo después sería peor que dejar pasar un duplicado. Se guarda la
    referencia a la más parecida y su puntuación, que es información suficiente
    para revisarlo desde el admin.

    ``limit`` acota las llamadas a Gemini por pasada.
    """
    try:
        vector_index = FeedService.initialize_vector_index()
        if vector_index is None:
            logger.warning("Qdrant no disponible; no se reintentan los embeddings pendientes.")
            return 0

        indexados = set()
        for point in vector_index.scroll_points(limit=256):
            news_id = (getattr(point, 'payload', {}) or {}).get('news_id')
            if news_id is not None:
                try:
                    indexados.add(int(news_id))
                except (TypeError, ValueError):
                    continue

        cutoff = timezone.now() - timedelta(days=days)
        # Se excluyen las que no se indexan por diseño: filtradas por palabra
        # (el filtro corta antes del embedding), redundantes y filtradas por IA.
        pendientes = (
            News.objects.filter(
                published_date__gte=cutoff,
                filtered_by__isnull=True,
                is_redundant=False,
                is_ai_filtered=False,
            )
            .exclude(id__in=indexados)
            .order_by('-published_date')[:limit]
        )

        if not pendientes:
            return 0

        gemini_client = FeedService.initialize_gemini()
        recuperadas = 0
        for news in pendientes:
            texto = f"{news.title} {news.description or ''}"
            embedding = EmbeddingService.generate_embedding(texto, gemini_client)
            if not embedding:
                logger.warning(
                    "Sigue sin poder generarse el embedding de la noticia %s", news.id
                )
                continue

            try:
                vector_index.ensure_collection(len(embedding))
                vector_index.upsert(
                    news.guid, embedding, FeedService.build_vector_payload(news)
                )
            except Exception:
                logger.exception("Error indexando la noticia %s en el reintento", news.id)
                continue

            recuperadas += 1

            # Solo informativo: se anota el parecido, sin ocultar nada.
            if news.similarity_score is None:
                news._embedding_vector = embedding
                try:
                    _, similar, score = EmbeddingService.check_redundancy(
                        news, gemini_client, None, vector_index
                    )
                except Exception:
                    logger.exception("Error calculando similitud de la noticia %s", news.id)
                    continue
                if similar is not None:
                    news.similar_to = similar
                    news.similarity_score = score
                    news.save(update_fields=['similar_to', 'similarity_score'])

        logger.info(
            "Reintento de embeddings: %s noticias indexadas de %s pendientes revisadas",
            recuperadas,
            len(pendientes),
        )
        return recuperadas
    except Exception:
        logger.exception("Error reintentando embeddings pendientes")
        return 0


def rescore_recent_news(limit: int = 0):
    """Repuntúa la ventana de referencia con los votos que haya ahora mismo.

    Cada noticia se puntúa al entrar, pero conserva ese valor para siempre: sin
    esto, votar no cambiaría nada de lo ya publicado y el feed quedaría
    describiendo unos gustos viejos.

    Cubre la ventana entera (``INTEREST_WINDOW_DAYS``), no solo lo que queda sin
    leer. Son dos motivos: la referencia del percentil no puede encoger según se
    lee, y así todas las noticias con las que se compara están puntuadas por el
    mismo modelo en la misma pasada.

    El coste medido con 164 noticias es de medio segundo, porque los vectores se
    piden todos de golpe. Si el modelo aún no tiene votos suficientes se sale sin
    llegar a hablar con Qdrant.

    Va al final del cron y después de la purga, para no robarle tiempo a la
    ingesta ni gastarlo en noticias que están a punto de borrarse.
    """
    try:
        model = InterestModel.load()
        if not model.is_trained:
            positives, negatives = model.label_counts
            logger.info(
                "Sin votos suficientes para puntuar (%s a favor / %s en contra); "
                "no se repuntúa.",
                positives,
                negatives,
            )
            return 0

        vector_index = FeedService.initialize_vector_index()
        if vector_index is None:
            logger.warning("Qdrant no disponible; no se repuntúa el feed.")
            return 0

        queryset = scored_population().order_by('-published_date')
        if limit and limit > 0:
            queryset = queryset[:limit]
        objetivo = list(queryset)
        if not objetivo:
            return 0

        vectores = vector_index.vectors_for_guids([n.guid for n in objetivo])

        pendientes = []
        puntuadas = 0
        for news in objetivo:
            vector = vectores.get(news.guid)
            if vector is None:
                continue
            news.interest_score = model.score(vector)
            pendientes.append(news)
            puntuadas += 1
            if len(pendientes) >= 200:
                News.objects.bulk_update(pendientes, ['interest_score'])
                pendientes = []

        if pendientes:
            News.objects.bulk_update(pendientes, ['interest_score'])

        # El percentil de la tarjeta se calcula sobre una distribución cacheada.
        cache.delete(INTEREST_DISTRIBUTION_CACHE_KEY)

        sin_vector = len(objetivo) - puntuadas
        logger.info(
            "Ventana de referencia repuntuada: %s noticias%s",
            puntuadas,
            f" ({sin_vector} sin vector, omitidas)" if sin_vector else "",
        )
        return puntuadas
    except Exception:
        logger.exception("Error repuntuando el feed")
        return 0


def update_news_cron():
    # En BASE_DIR y no en /tmp: ahí el sistema puede borrarlo en limpiezas/reinicios.
    lock_path = os.path.join(settings.BASE_DIR, 'my_news_update.lock')
    try:
        with portalocker.Lock(lock_path, timeout=0):
            # Completar algunas pendientes antes de traer nuevas, sin solapar el siguiente cron.
            try:
                retry_summarize_pending(limit=5, days=15)
            except Exception:
                logger.exception("Error reintentando resúmenes pendientes antes del cron")
            FeedService.fetch_and_save_news(max_ai_items=20)
            logger.info("Noticias actualizadas correctamente")
            # Recuperar las que se quedaron sin vector en pasadas anteriores, para
            # que vuelvan a contar en la detección de duplicados.
            try:
                retry_missing_embeddings(limit=25, days=15)
            except Exception:
                logger.exception("Error reintentando embeddings pendientes tras el cron")
            # Ejecutar limpieza tras actualización
            purge_old_news(15)
            # Lo último, y después de la purga: así no gasta trabajo en noticias
            # que se van a borrar y no puede retrasar la ingesta, que es lo que
            # tiene que llegar a tiempo.
            try:
                rescore_recent_news()
            except Exception:
                logger.exception("Error repuntuando el feed tras el cron")
    except portalocker.exceptions.LockException:
        logger.warning("Actualización de noticias omitida: ya hay otra ejecución en curso.")
    except Exception:
        logger.exception("Error actualizando noticias")


def purge_old_news(days: int = 15):
    """Elimina noticias no guardadas más viejas que ``days`` días.

    Usa ``published_date`` como referencia y conserva las noticias que el
    usuario haya marcado como guardadas.
    """
    try:
        cutoff = timezone.now() - timedelta(days=days)
        stale_news = News.objects.filter(published_date__lt=cutoff, is_saved=False)
        stale_guids = list(stale_news.values_list('guid', flat=True))
        deleted_count, _ = stale_news.delete()

        deleted_vectors = 0
        vector_index = FeedService.initialize_vector_index()
        if vector_index is not None:
            try:
                deleted_vectors += vector_index.delete_many(stale_guids)
            except Exception:
                logger.exception("Error eliminando vectores antiguos en Qdrant")

            deleted_vectors += purge_orphan_vectors()

        # Tras borrar filas, refrescar estadísticas del planificador de SQLite.
        # (VACUUM completo se evita: bloquea toda la BD y corre cada 30 min.)
        if deleted_count and connection.vendor == 'sqlite':
            try:
                with connection.cursor() as cursor:
                    cursor.execute('PRAGMA optimize')
            except Exception:
                logger.exception("Error ejecutando PRAGMA optimize tras la purga")

        logger.info(
            f"Purga completada: {deleted_count} noticias no guardadas eliminadas (> {days} días)"
        )
        if vector_index is not None:
            logger.info(f"Qdrant sincronizado: {deleted_vectors} vectores eliminados")
        return deleted_count
    except Exception:
        logger.exception("Error purgando noticias antiguas")
        return 0


def retry_summarize_pending(limit: int = 50, days: int = 15):
    """Reintenta generar resumen/short_answer para noticias recientes no filtradas por IA.

    Ampliado a una ventana de 15 días y sin depender de short_answer__isnull.
    Solo cuenta como procesada si se guardan cambios.
    """
    try:
        cerebras_client = FeedService.initialize_cerebras()
        try:
            ai_model_name = (
                AIModelSetting.objects.first()
                or AIModelSetting(model_name=DEFAULT_AI_MODEL)
            ).model_name
        except Exception:
            ai_model_name = DEFAULT_AI_MODEL

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
        ).order_by('created_at', 'id')[:limit]

        processed = 0
        for news in qs:
            processed_description, short_answer, ai_filter_reason = FeedService.process_content_with_cerebras(
                news.title,
                news.description or '',
                cerebras_client,
                ai_model_name,
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

        logger.info(f"Reintento resúmenes completado. Noticias procesadas: {processed}")
        return processed
    except Exception:
        logger.exception("Error en retry_summarize_pending")
        return 0

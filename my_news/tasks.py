from .services import (
    EmbeddingService,
    FeedService,
    DEFAULT_AI_MODEL,
    REDUNDANCY_WINDOW_DAYS,
)
from django.utils import timezone
from datetime import timedelta
from .models import News
from .models import AIModelSetting
from .models import AIFilterInstruction
from .ingestion_status import report_error
from django.conf import settings
from django.db import connection
import os
import portalocker
import logging


logger = logging.getLogger(__name__)


def purge_orphan_vectors(batch_size: int = 256):
    """Elimina de Qdrant los puntos que ya no sirven para nada.

    OJO: que un punto no tenga fila en News **no** lo convierte en huérfano.
    Desde que la ventana de duplicados es de un año, eso es lo normal: la
    noticia se purga a los 15 días y su vector sigue vivo para reconocer
    republicaciones. El criterio es la fecha, no la existencia de la fila.

    Queda como red de seguridad contra puntos sin fecha utilizable (los que
    escribiera una versión anterior), y corre una vez al día: recorre la
    colección entera, que con la ventana larga son ~28.000 puntos.
    """
    try:
        vector_index = FeedService.initialize_vector_index()
        if vector_index is None:
            return 0

        corte = timezone.now() - timedelta(days=REDUNDANCY_WINDOW_DAYS)
        corte_ts = int(corte.timestamp())
        orphan_point_ids = []

        for point in vector_index.scroll_points(limit=batch_size):
            payload = getattr(point, 'payload', {}) or {}
            published_ts = payload.get('published_ts')
            if published_ts is None:
                orphan_point_ids.append(point.id)
                continue

            try:
                if int(published_ts) < corte_ts:
                    orphan_point_ids.append(point.id)
            except (TypeError, ValueError):
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

        cutoff = timezone.now() - timedelta(days=days)
        # Se excluyen las que no se indexan por diseño: filtradas por palabra
        # (el filtro corta antes del embedding), redundantes y filtradas por IA.
        candidatas = list(
            News.objects.filter(
                published_date__gte=cutoff,
                filtered_by__isnull=True,
                is_redundant=False,
                is_ai_filtered=False,
            ).order_by('-published_date')
        )

        # Antes se recorría la colección entera para saber qué estaba indexado.
        # Con 1.151 puntos costaba 161 ms, pero con la ventana de un año son
        # ~28.000 puntos y ~3,9 s, 29 veces al día, para casi siempre no hacer
        # nada. Preguntar por los guids concretos no depende del tamaño de la
        # colección.
        ya_indexados = vector_index.known_guids([n.guid for n in candidatas])
        pendientes = [n for n in candidatas if n.guid not in ya_indexados][:limit]

        if not pendientes:
            return 0

        gemini_client = FeedService.initialize_gemini()

        # En lote, igual que la ingesta. De uno en uno esto gastaba hasta 25
        # peticiones por pasada y el límite gratuito de embeddings son 100 por
        # minuto: sumado a la ingesta de la misma pasada, se acercaba de más a
        # un techo que no hace ninguna falta rozar.
        embeddings = EmbeddingService.generate_embeddings_batch(
            [f"{news.title} {news.description or ''}" for news in pendientes],
            gemini_client,
        )

        recuperadas = 0
        for news, embedding in zip(pendientes, embeddings):
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
                news._embedding_attempted = True
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
            # Ejecutar limpieza tras actualización. El mantenimiento caro
            # (repaso de huérfanos y PRAGMA optimize) se reserva a la última
            # pasada del día: recorrer la colección entera 29 veces al día son
            # escrituras y lecturas en la SD a cambio de nada.
            purge_old_news(15, mantenimiento=timezone.localtime().hour >= 22)
    except portalocker.exceptions.LockException:
        # No es una avería: la pasada anterior sigue en marcha y terminará ella.
        logger.warning("Actualización de noticias omitida: ya hay otra ejecución en curso.")
    except Exception as e:
        logger.exception("Error actualizando noticias")
        # Que el fallo se vea en el feed y no solo aquí.
        report_error(
            'La actualización de noticias falló por completo.',
            detail=str(e),
        )


def purge_old_news(days: int = 15, mantenimiento: bool = False):
    """Elimina noticias no guardadas más viejas que ``days`` días.

    Usa ``published_date`` como referencia y conserva las noticias que el
    usuario haya marcado como guardadas.

    Los VECTORES no se borran con la noticia: sobreviven
    ``REDUNDANCY_WINDOW_DAYS`` (un año) para poder reconocer republicaciones de
    hace meses. Guardar el vector cuesta 3 KB; guardar la fila de la noticia
    para acompañarlo costaría multiplicar por 24 la base de datos, y en una SD
    eso son escrituras que no hacen falta.

    ``mantenimiento`` activa las tareas caras que solo valen la pena una vez al
    día: el repaso de huérfanos y el PRAGMA optimize.
    """
    try:
        cutoff = timezone.now() - timedelta(days=days)
        stale_news = News.objects.filter(published_date__lt=cutoff, is_saved=False)
        deleted_count, _ = stale_news.delete()

        deleted_vectors = 0
        vector_index = FeedService.initialize_vector_index()
        if vector_index is not None:
            try:
                # Una sola petición con un filtro de fecha, en lugar de
                # enumerar los guids: el criterio es la fecha y Qdrant sabe
                # aplicarlo él.
                corte_vectores = timezone.now() - timedelta(days=REDUNDANCY_WINDOW_DAYS)
                vector_index.delete_older_than(int(corte_vectores.timestamp()))
            except Exception:
                logger.exception("Error eliminando vectores antiguos en Qdrant")

            if mantenimiento:
                deleted_vectors += purge_orphan_vectors()

        # Tras borrar filas, refrescar estadísticas del planificador de SQLite.
        # Solo en la pasada de mantenimiento: PRAGMA optimize reescribe
        # estadísticas, y hacerlo 29 veces al día son escrituras a la SD que no
        # compran nada.
        if mantenimiento and deleted_count and connection.vendor == 'sqlite':
            try:
                with connection.cursor() as cursor:
                    cursor.execute('PRAGMA optimize')
            except Exception:
                logger.exception("Error ejecutando PRAGMA optimize tras la purga")

        logger.info(
            f"Purga completada: {deleted_count} noticias no guardadas eliminadas (> {days} días)"
        )
        if vector_index is not None and mantenimiento:
            logger.info(f"Qdrant sincronizado: {deleted_vectors} vectores huérfanos eliminados")
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
        try:
            ai_model_setting = (
                AIModelSetting.objects.first()
                or AIModelSetting(model_name=DEFAULT_AI_MODEL)
            )
            ai_model_name = ai_model_setting.model_name
        except Exception:
            ai_model_setting = None
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
            processed_description, short_answer, ai_filter_reason = FeedService.process_news_content(
                news.title,
                news.description or '',
                filter_instructions_text,
                ai_model_setting=ai_model_setting,
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

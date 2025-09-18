from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone
from datetime import timedelta
import time
import numpy as np

from my_news.models import News
from my_news.services import FeedService, EmbeddingService


class Command(BaseCommand):
    help = "Indexa en Qdrant las noticias de los últimos N días, generando embeddings con Gemini si faltan o la dimensión no coincide."

    def add_arguments(self, parser):
        parser.add_argument(
            "--days",
            type=int,
            default=14,
            help="Días hacia atrás a indexar (default: 14)",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=None,
            help="Límite máximo de noticias a procesar",
        )
        parser.add_argument(
            "--source-id",
            type=int,
            default=None,
            help="Filtra por una fuente específica (id)",
        )
        parser.add_argument(
            "--force",
            action="store_true",
            help="Recalcula el embedding aunque exista",
        )

    def handle(self, *args, **options):
        days = options["days"]
        limit = options["limit"]
        source_id = options["source_id"]
        force = options["force"]

        self.stdout.write(self.style.HTTP_INFO(f"Inicializando clientes (Gemini/Qdrant)..."))
        gemini_client = FeedService.initialize_gemini()
        vector_index = FeedService.initialize_vector_index()
        if vector_index is None:
            raise CommandError(
                "Qdrant no disponible. Asegúrate de tener qdrant-client instalado y QDRANT_URL configurado."
            )

        cutoff = timezone.now() - timedelta(days=days)
        qs = News.objects.filter(published_date__gte=cutoff)
        # Indexar solo candidatos relevantes para dedupe
        qs = qs.filter(is_filtered=False, is_redundant=False)
        if source_id:
            qs = qs.filter(source_id=source_id)
        qs = qs.order_by("published_date")
        if limit:
            qs = qs[:limit]

        total = qs.count()
        if total == 0:
            self.stdout.write("No hay noticias que indexar en el rango indicado.")
            return

        processed = 0
        indexed = 0
        skipped = 0

        # Detectar dimensión objetivo desde settings (usado por EmbeddingService)
        from django.conf import settings

        target_dim = int(getattr(settings, "GEMINI_EMBEDDING_DIM", 768))

        # Asegurar colección: si la primera noticia no tiene embedding o es otra dimensión, se corrige en el loop
        vector_index.ensure_collection(target_dim)

        start = time.time()
        for news in qs.iterator():
            processed += 1
            text = f"{news.title} {news.description or ''}".strip()
            emb = news.embedding
            needs_reembed = force or (not emb) or (isinstance(emb, list) and len(emb) != target_dim)
            if needs_reembed:
                emb = EmbeddingService.generate_embedding(text, gemini_client)
                if not emb:
                    skipped += 1
                    continue
                try:
                    news.embedding = emb
                    news.save(update_fields=["embedding"])
                except Exception:
                    # Si el modelo News no soporta actualizar embedding aquí, continuar solo con Qdrant
                    pass

            try:
                vector_index.ensure_collection(len(emb))
                published_ts = int(news.published_date.timestamp()) if news.published_date else int(time.time())
                payload = {
                    "news_id": news.id,
                    "source_id": news.source_id,
                    "published_ts": published_ts,
                    "is_filtered": bool(getattr(news, "is_filtered", False)),
                    "is_redundant": bool(getattr(news, "is_redundant", False)),
                    "model_version": getattr(settings, "GEMINI_EMBEDDING_MODEL", "gemini-embedding-001"),
                }
                vector_index.upsert(news.guid, emb, payload)
                indexed += 1
            except Exception as e:
                skipped += 1
                self.stderr.write(f"Error indexando guid={news.guid}: {e}")

            if processed % 50 == 0:
                self.stdout.write(f"Progreso: {processed}/{total} procesadas, {indexed} indexadas, {skipped} omitidas")

        elapsed = time.time() - start
        self.stdout.write(
            self.style.SUCCESS(
                f"Backfill completado en {elapsed:.1f}s. Procesadas={processed}, Indexadas={indexed}, Omitidas={skipped}"
            )
        )


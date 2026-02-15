from django.db import models
from django.utils import timezone
from django.db.models import Q

class VisibleNewsManager(models.Manager):
    """Manager para noticias visibles (no eliminadas, no filtradas, no redundantes, no filtradas por IA)"""
    def get_queryset(self):
        return super().get_queryset().filter(
            is_deleted=False,
            is_filtered=False,
            is_ai_filtered=False,
            is_redundant=False
        )
    
    def visible_filter(self):
        """Devuelve el filtro Q para noticias visibles"""
        return Q(is_deleted=False) & Q(is_filtered=False) & Q(is_ai_filtered=False) & Q(is_redundant=False)

class FeedSource(models.Model):
    name = models.CharField(max_length=200)
    url = models.URLField()
    active = models.BooleanField(default=True)
    last_fetch = models.DateTimeField(null=True, blank=True)
    deep_search = models.BooleanField(
        default=False,
        verbose_name="Búsqueda profunda",
        help_text="Obtener el contenido completo del artículo desde la URL original"
    )
    similarity_threshold = models.FloatField(
        default=0.92,
        verbose_name="Umbral de Similitud",
        help_text="Valor entre 0 y 1 (e.g., 0.92). Noticias con similitud mayor o igual serán marcadas como redundantes."
    )
    
    def __str__(self):
        return self.name

class News(models.Model):
    title = models.CharField(max_length=500)
    description = models.TextField()
    link = models.URLField()
    published_date = models.DateTimeField()
    source = models.ForeignKey(FeedSource, on_delete=models.CASCADE)
    guid = models.CharField(max_length=500, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    image_url = models.URLField(null=True, blank=True)
    is_deleted = models.BooleanField(default=False, verbose_name="Eliminada")
    is_filtered = models.BooleanField(default=False, verbose_name="Filtro Aut.")
    filtered_by = models.ForeignKey('FilterWord', null=True, blank=True, on_delete=models.SET_NULL,
                                  verbose_name="Palabra Filtro", related_name="filtered_news")
    
    # Nuevos campos para embeddings y detección de redundancia
    embedding = models.JSONField(null=True, blank=True, verbose_name="Embedding del contenido")
    similar_to = models.ForeignKey('self', on_delete=models.SET_NULL, null=True, blank=True, 
                                  verbose_name="Noticia similar", related_name="similar_news")
    similarity_score = models.FloatField(null=True, blank=True, verbose_name="% Similitud")
    is_redundant = models.BooleanField(default=False, verbose_name="Redundante")
    short_answer = models.TextField(null=True, blank=True, verbose_name="Respuesta corta")
    ai_filter_reason = models.TextField(null=True, blank=True, verbose_name="Razón Filtro IA")
    is_ai_filtered = models.BooleanField(default=False, verbose_name="Filtro IA")
    is_ai_processed = models.BooleanField(default=False, verbose_name="Procesada por IA")
    
    # Managers
    objects = models.Manager()  # Manager por defecto
    visible = VisibleNewsManager()  # Manager para noticias visibles
    
    class Meta:
        verbose_name = "Noticia"
        verbose_name_plural = "Noticias"
        ordering = ['-published_date']
        indexes = [
            models.Index(
                fields=['is_deleted', 'is_filtered', 'is_ai_filtered', 'is_redundant', 'published_date', 'id'],
                name='news_visible_pub_id_idx'
            ),
            models.Index(fields=['created_at', 'id'], name='news_created_id_idx'),
        ]
    
    def __str__(self):
        return self.title

class FilterWord(models.Model):
    word = models.CharField(
        max_length=100,
        unique=True,
        verbose_name="Palabra a filtrar"
    )
    active = models.BooleanField(
        default=True,
        verbose_name="Activo"
    )
    title_only = models.BooleanField(
        default=False,
        verbose_name="Solo en título",
        help_text="Si está activado, solo filtra noticias donde la palabra aparezca en el título"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Palabra Filtro"
        verbose_name_plural = "Palabras Filtro"
        ordering = ['word']

    def __str__(self):
        return self.word

class AIFilterInstruction(models.Model):
    instruction = models.TextField(
        unique=True,
        verbose_name="Instrucción para IA",
        help_text="Describe el tipo de contenido a filtrar (ej: 'Noticias sobre horóscopos', 'Artículos de opinión política muy sesgados')"
    )
    active = models.BooleanField(
        default=True,
        verbose_name="Activo"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Instrucción Filtro IA"
        verbose_name_plural = "Instrucciones Filtro IA"
        ordering = ['-created_at']

    def __str__(self):
        return self.instruction

class GeminiGlobalSetting(models.Model):
    model_name = models.CharField(
        max_length=100,
        default='gemini-2.0-flash',
        verbose_name="Modelo Gemini Global",
        help_text="Nombre del modelo de Gemini a utilizar globalmente (ej: 'gemini-1.5-flash', 'gemini-pro')."
    )
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Configuración Global Gemini ({self.model_name})"

    class Meta:
        verbose_name = "Configuración Global Gemini"
        verbose_name_plural = "Configuraciones Globales Gemini"


class GroqGlobalSetting(models.Model):
    model_name = models.CharField(
        max_length=100,
        default='llama-3.3-70b-versatile',
        verbose_name="Modelo Groq Global",
        help_text="Nombre del modelo de Groq a utilizar (ej: 'llama-3.3-70b-versatile', 'llama-3.1-8b-instant', 'mixtral-8x7b-32768')."
    )
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Configuración Global Groq ({self.model_name})"

    class Meta:
        verbose_name = "Configuración Global Groq"
        verbose_name_plural = "Configuraciones Globales Groq"

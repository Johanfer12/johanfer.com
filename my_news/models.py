from django.db import models
from django.utils import timezone

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
    is_deleted = models.BooleanField(default=False, verbose_name="Eliminada por usuario")
    is_filtered = models.BooleanField(default=False, verbose_name="Filtrada automáticamente")
    
    # Nuevos campos para embeddings y detección de redundancia
    embedding = models.JSONField(null=True, blank=True, verbose_name="Embedding del contenido")
    similar_to = models.ForeignKey('self', on_delete=models.SET_NULL, null=True, blank=True, 
                                  verbose_name="Noticia similar", related_name="similar_news")
    similarity_score = models.FloatField(null=True, blank=True, verbose_name="Puntuación de similitud")
    is_redundant = models.BooleanField(default=False, verbose_name="Es redundante")
    
    class Meta:
        verbose_name = "Noticia"
        verbose_name_plural = "Noticias"
        ordering = ['-published_date']
    
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
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Palabra filtrada"
        verbose_name_plural = "Palabras filtradas"
        ordering = ['word']

    def __str__(self):
        return self.word

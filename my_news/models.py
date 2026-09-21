from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q

from . import ai_providers

class VisibleNewsManager(models.Manager):
    """Manager para noticias visibles (no eliminadas, no filtradas, no redundantes, no filtradas por IA)"""
    def get_queryset(self):
        return super().get_queryset().filter(self.visible_filter())

    def editorial_filter(self):
        """Filtro compartido para contenido apto para mostrarse."""
        return Q(is_filtered=False) & Q(is_ai_filtered=False) & Q(is_redundant=False) & Q(is_ai_processed=True)
    
    def visible_filter(self):
        """Devuelve el filtro Q para noticias visibles"""
        return Q(is_deleted=False) & self.editorial_filter()

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
        default=0.85,
        verbose_name="Umbral de Similitud",
        help_text=(
            "Valor entre 0 y 1. Noticias con similitud mayor o igual serán marcadas como "
            "redundantes. 0.85 es el punto medido sobre el histórico: por encima son "
            "duplicados reales y por debajo son noticias distintas. Con 0.92 solo se caza "
            "un tercio de los duplicados."
        )
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
    deleted_at = models.DateTimeField(null=True, blank=True, verbose_name="Eliminada en")
    is_saved = models.BooleanField(default=False, verbose_name="Guardada")
    is_filtered = models.BooleanField(default=False, verbose_name="Filtro Aut.")
    filtered_by = models.ForeignKey('FilterWord', null=True, blank=True, on_delete=models.SET_NULL,
                                  verbose_name="Palabra Filtro", related_name="filtered_news")
    
    # Campos para detección de redundancia; los vectores viven en Qdrant.
    similar_to = models.ForeignKey('self', on_delete=models.SET_NULL, null=True, blank=True, 
                                  verbose_name="Noticia similar", related_name="similar_news")
    similarity_score = models.FloatField(null=True, blank=True, verbose_name="% Similitud")
    # La ventana de duplicados es de un año pero las noticias se purgan a los
    # 15 días, así que el original de un duplicado antiguo ya no tiene fila a
    # la que apuntar con `similar_to`. Aquí queda su titular y enlace, sacados
    # del payload de Qdrant, para poder revisarlo desde el admin.
    similar_ref = models.CharField(
        max_length=600, blank=True, default='',
        verbose_name="Original (ya purgado)"
    )
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
            models.Index(fields=['is_deleted', 'deleted_at', 'id'], name='news_deleted_at_idx'),
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

class AIModelSetting(models.Model):
    """Proveedor y modelo de IA con que se resumen las noticias.

    Los detalles de cada proveedor (limites medidos, por que se eligio, que se
    descarto) estan en ``my_news/ai_providers.py``.
    """

    SIN_RESPALDO = ''
    RESPALDO_CHOICES = [(SIN_RESPALDO, 'Sin respaldo')] + ai_providers.PROVIDER_CHOICES

    REASONING_AUTO = ''
    REASONING_CHOICES = [
        (REASONING_AUTO, 'Automático (según el modelo)'),
        ('none', 'Sin razonamiento'),
        ('low', 'Bajo (recomendado)'),
        ('medium', 'Medio'),
        ('high', 'Alto'),
    ]
    MIN_REASONING_TOKENS = ai_providers.MIN_REASONING_TOKENS

    provider = models.CharField(
        max_length=20,
        default=ai_providers.DEFAULT_PROVIDER,
        choices=ai_providers.PROVIDER_CHOICES,
        verbose_name="Proveedor",
        help_text="Quién genera los resúmenes. El primero que se intenta.",
    )
    model_name = models.CharField(
        max_length=100,
        blank=True,
        default=ai_providers.DEFAULT_MODELS[ai_providers.DEFAULT_PROVIDER],
        verbose_name="Modelo IA Global",
        help_text=(
            "Modelo del proveedor de arriba (ej: 'gemini-3.5-flash-lite'). "
            "Vacío usa el modelo por defecto de ese proveedor."
        ),
    )
    fallback_provider = models.CharField(
        max_length=20,
        blank=True,
        default=ai_providers.DEFAULT_FALLBACK,
        choices=RESPALDO_CHOICES,
        verbose_name="Proveedor de respaldo",
        help_text=(
            "A quién recurrir cuando el principal se queda sin cuota, en vez "
            "de pausar la ingesta. Usa su modelo por defecto. Vacío lo desactiva."
        ),
    )
    thinking_level = models.CharField(
        max_length=10,
        blank=True,
        default='',
        choices=ai_providers.THINKING_CHOICES,
        verbose_name="Pensamiento (Gemini)",
        help_text=(
            "Solo afecta a Gemini. Medido en gemini-3.5-flash-lite: de los "
            "cuatro niveles solo 'Alto' piensa de verdad; los demás dan cero "
            "tokens de pensamiento y no cambian nada. 'Alto' cuesta el triple "
            "de tokens y ~19 s por noticia en vez de 1,4 s."
        ),
    )
    reasoning_effort = models.CharField(
        max_length=10,
        blank=True,
        default=REASONING_AUTO,
        choices=REASONING_CHOICES,
        verbose_name="Razonamiento",
        help_text=(
            "Solo afecta a Groq; Gemini 3.5 Lite no gasta tokens de "
            "razonamiento (medido). 'Automático' usa el valor probado de cada "
            "modelo. Medido: 'bajo' no mejora el resumen, que es transcripción, "
            "pero estabiliza el short_answer; 'medio' y 'alto' lo empeoran, "
            "volviéndolo nulo en titulares que sí esconden el dato."
        ),
    )
    max_completion_tokens = models.PositiveIntegerField(
        null=True,
        blank=True,
        verbose_name="Tokens de respuesta",
        help_text=(
            "Presupuesto de salida por noticia en Groq. Vacío usa el valor "
            "probado para cada modelo. OJO: el razonamiento se cobra aquí "
            f"dentro, así que por encima de 'bajo' hacen falta {MIN_REASONING_TOKENS} "
            "o la respuesta llega truncada y sin JSON, perdiendo la noticia."
        ),
    )
    updated_at = models.DateTimeField(auto_now=True)

    def clean(self):
        """Impide guardar razonamiento con un presupuesto que no le da.

        Es la combinación que rompe la ingesta en silencio: la respuesta no
        llega recortada, llega truncada y sin JSON.
        """
        super().clean()
        razona = self.reasoning_effort not in (self.REASONING_AUTO, 'none', 'low')
        if (razona and self.max_completion_tokens is not None
                and self.max_completion_tokens < self.MIN_REASONING_TOKENS):
            raise ValidationError({
                'max_completion_tokens': (
                    f"Con razonamiento '{self.reasoning_effort}' hacen falta al "
                    f"menos {self.MIN_REASONING_TOKENS} tokens: el razonamiento "
                    "se cobra dentro de este presupuesto y con menos la "
                    "respuesta llega truncada y sin JSON."
                )
            })

    def __str__(self):
        return f"Configuración Global de Modelo IA ({self.model_name})"

    class Meta:
        verbose_name = "Configuración Global de Modelo IA"
        verbose_name_plural = "Configuraciones Globales de Modelo IA"


class IngestionStatus(models.Model):
    """Resultado de la última pasada de ingesta, para poder verlo desde el feed.

    Existe porque el cron corre en otro proceso: el caché por defecto es LocMem
    y no cruza de django-crontab a gunicorn, así que la única forma de que la
    web sepa qué pasó en la última pasada es dejarlo escrito en la base.

    Hasta ahora un fallo de la IA solo se notaba porque el feed dejaba de traer
    noticias, y había que entrar por SSH a leer el log para saber por qué.

    Es una fila única (``pk=1``); se sobrescribe en cada pasada.
    """

    STATE_OK = 'ok'
    STATE_PAUSED = 'paused'
    STATE_ERROR = 'error'
    STATE_CHOICES = [
        (STATE_OK, 'Correcta'),
        (STATE_PAUSED, 'Pausada'),
        (STATE_ERROR, 'Con error'),
    ]

    SINGLETON_PK = 1

    state = models.CharField(
        max_length=10,
        choices=STATE_CHOICES,
        default=STATE_OK,
        verbose_name="Estado",
    )
    reason = models.CharField(
        max_length=200,
        blank=True,
        verbose_name="Motivo",
        help_text="Resumen corto y legible de por qué se pausó o falló.",
    )
    detail = models.TextField(
        blank=True,
        verbose_name="Detalle",
        help_text="Mensaje técnico del proveedor, para diagnosticar sin abrir el log.",
    )
    new_count = models.IntegerField(
        default=0,
        verbose_name="Noticias nuevas",
    )
    retry_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Reintento estimado",
        help_text="Cuándo se espera que la cuota vuelva, si el proveedor lo indicó.",
    )
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Actualizado")

    class Meta:
        verbose_name = "Estado de la ingesta"
        verbose_name_plural = "Estado de la ingesta"

    def __str__(self):
        return f"Ingesta {self.get_state_display()} ({self.updated_at:%Y-%m-%d %H:%M})"

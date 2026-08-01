from django.db import models


class WatchedItem(models.Model):
    """Un evento del historial: una película vista o un episodio visto.

    La fuente fue Trakt hasta julio 2026 y es Simkl desde agosto 2026 (ver
    SIMKL_MIGRATION_PLAN.md). Los registros históricos de Trakt se conservan tal
    cual, con su `trakt_id` y su URL; lo que une ambas épocas es `tmdb_id`.
    """

    MEDIA_TYPES = (
        ('movie', 'Película'),
        ('episode', 'Episodio'),
    )

    SOURCES = (
        ('trakt', 'Trakt'),
        ('simkl', 'Simkl'),
    )

    # Clave de deduplicación: 'movie:<tmdb>' o 'show:<tmdb>:s01e05'. Es texto porque
    # un UniqueConstraint sobre (tmdb_id, season, episode) no serviría: en SQLite los
    # NULL de las películas no colisionan entre sí.
    dedup_key = models.CharField(max_length=64, unique=True, verbose_name="Clave única")
    source = models.CharField(max_length=10, choices=SOURCES, default='simkl', verbose_name="Fuente")
    media_type = models.CharField(max_length=10, choices=MEDIA_TYPES, verbose_name="Tipo")
    title = models.CharField(max_length=300, verbose_name="Título")  # película o nombre de la serie
    episode_title = models.CharField(max_length=300, blank=True, default='', verbose_name="Título episodio")
    season = models.PositiveSmallIntegerField(null=True, blank=True, verbose_name="Temporada")
    episode = models.PositiveSmallIntegerField(null=True, blank=True, verbose_name="Episodio")
    year = models.PositiveIntegerField(null=True, blank=True, verbose_name="Año")
    overview = models.TextField(blank=True, default='', verbose_name="Sinopsis")
    user_rating = models.PositiveSmallIntegerField(null=True, blank=True, verbose_name="Mi calificación")
    public_rating = models.FloatField(null=True, blank=True, verbose_name="Calificación general")
    total_episodes = models.PositiveIntegerField(null=True, blank=True, verbose_name="Episodios totales")
    available_episodes = models.PositiveIntegerField(null=True, blank=True, verbose_name="Episodios disponibles")
    watched_at = models.DateTimeField(verbose_name="Visto el")
    tmdb_id = models.PositiveIntegerField(db_index=True, null=True, blank=True, verbose_name="ID TMDB")
    imdb_id = models.CharField(max_length=20, blank=True, default='', db_index=True, verbose_name="ID IMDB")
    simkl_id = models.PositiveIntegerField(null=True, blank=True, verbose_name="ID Simkl")
    detail_url = models.URLField(blank=True, default='', verbose_name="Ficha")
    # Solo en los registros heredados de Trakt.
    trakt_id = models.PositiveIntegerField(null=True, blank=True, verbose_name="ID Trakt")
    trakt_history_id = models.BigIntegerField(null=True, blank=True, unique=True, verbose_name="ID historial Trakt")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-watched_at']
        verbose_name = 'Visto'
        verbose_name_plural = 'Vistos'
        indexes = [
            models.Index(fields=['-watched_at'], name='watched_at_idx'),
        ]

    @staticmethod
    def build_dedup_key(media_type, tmdb_id, season=None, episode=None):
        if media_type == 'movie':
            return f"movie:{tmdb_id}"
        return f"show:{tmdb_id}:s{season or 0:02d}e{episode or 0:02d}"

    @property
    def work_key(self):
        """Identifica la obra (serie o película), no el evento. Agrupa las tarjetas."""
        return self.tmdb_id

    @property
    def poster_name(self):
        # Un póster por obra: los episodios comparten el póster de la serie.
        kind = 'show' if self.media_type == 'episode' else 'movie'
        return f"{kind}_{self.tmdb_id}.webp"

    @property
    def display_label(self):
        if self.media_type == 'episode':
            if self.season is not None and self.episode is not None:
                return f"T{self.season:02d}E{self.episode:02d}"
            return "Episodio"
        return "Película"

    def __str__(self):
        if self.media_type == 'episode':
            return f"{self.title} {self.display_label}"
        return self.title


class SimklSyncState(models.Model):
    """Guarda el `activities.all` de la última sincronización.

    Sirve de doble propósito: gatear el pull (si Simkl no reporta cambios, no se
    descarga nada) y alimentar `date_from` para pedir solo lo modificado. Vive en la
    BD y no en un archivo para que no se pierda en un despliegue.
    """

    last_activity_at = models.CharField(max_length=40, blank=True, default='', verbose_name="Última actividad")
    last_synced_at = models.DateTimeField(auto_now=True, verbose_name="Última corrida")
    # Ids de TMDB que Simkl reporta a medias (/sync/playback), separados por coma. Se
    # guardan en el sync para que la vista no tenga que llamar a la API en cada render.
    in_progress_ids = models.TextField(blank=True, default='', verbose_name="En curso")

    class Meta:
        verbose_name = 'Estado de sync Simkl'
        verbose_name_plural = 'Estado de sync Simkl'

    @classmethod
    def load(cls):
        state, _ = cls.objects.get_or_create(pk=1)
        return state

    @property
    def in_progress_tmdb_ids(self):
        return {int(part) for part in self.in_progress_ids.split(',') if part.strip().isdigit()}

    def __str__(self):
        return f"Simkl @ {self.last_activity_at or 'nunca'}"

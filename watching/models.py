from django.db import models


class WatchedItem(models.Model):
    """Un evento del historial de Trakt (película vista o episodio visto)."""

    MEDIA_TYPES = (
        ('movie', 'Película'),
        ('episode', 'Episodio'),
    )

    trakt_history_id = models.BigIntegerField(unique=True, verbose_name="ID historial Trakt")
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
    trakt_id = models.PositiveIntegerField(verbose_name="ID Trakt")  # de la película o la serie
    tmdb_id = models.PositiveIntegerField(null=True, blank=True, verbose_name="ID TMDB")
    trakt_url = models.URLField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-watched_at']
        verbose_name = 'Visto'
        verbose_name_plural = 'Vistos'
        indexes = [
            models.Index(fields=['-watched_at'], name='watched_at_idx'),
        ]

    @property
    def poster_name(self):
        # Un póster por obra: los episodios comparten el póster de la serie.
        kind = 'show' if self.media_type == 'episode' else 'movie'
        return f"{kind}_{self.trakt_id}.webp"

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

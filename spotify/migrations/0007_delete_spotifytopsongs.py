from django.db import migrations


class Migration(migrations.Migration):
    """Elimina SpotifyTopSongs: sin uso desde que el top de canciones se
    muestra vía iframe de la playlist (la sincronización con la API se retiró
    en junio 2026)."""

    dependencies = [
        ('spotify', '0006_spotifytopsongs_rank'),
    ]

    operations = [
        migrations.DeleteModel(
            name='SpotifyTopSongs',
        ),
    ]

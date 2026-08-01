"""Migra el historial de Trakt a un modelo agnóstico de fuente, listo para Simkl.

Los registros existentes se conservan intactos: se les marca `source='trakt'`, se les
calcula la `dedup_key` a partir de `tmdb_id` y su `trakt_url` pasa a `detail_url`.
"""

from django.db import migrations, models


def backfill(apps, schema_editor):
    WatchedItem = apps.get_model('watching', 'WatchedItem')

    used_keys = set()
    updated = []
    for item in WatchedItem.objects.all().order_by('watched_at', 'id'):
        if item.tmdb_id:
            if item.media_type == 'movie':
                key = f"movie:{item.tmdb_id}"
            else:
                key = f"show:{item.tmdb_id}:s{item.season or 0:02d}e{item.episode or 0:02d}"
        else:
            # Sin TMDB no hay clave estable por obra: se cae al id de historial de Trakt.
            key = f"trakt:{item.trakt_history_id or item.pk}"

        # Un revisionado produciría la misma clave: se desambigua con un sufijo para
        # no perder la fila (las vistas cuentan las repeticiones como 'plays').
        base_key = key
        repeat = 1
        while key in used_keys:
            repeat += 1
            key = f"{base_key}#{repeat}"
        used_keys.add(key)

        item.dedup_key = key
        item.source = 'trakt'
        updated.append(item)

    WatchedItem.objects.bulk_update(updated, ['dedup_key', 'source'], batch_size=500)


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('watching', '0005_watcheditem_available_episodes'),
    ]

    operations = [
        migrations.RenameField(
            model_name='watcheditem',
            old_name='trakt_url',
            new_name='detail_url',
        ),
        migrations.AlterField(
            model_name='watcheditem',
            name='detail_url',
            field=models.URLField(blank=True, default='', verbose_name='Ficha'),
        ),
        # dedup_key entra sin unique para poder rellenarla; se sella al final.
        migrations.AddField(
            model_name='watcheditem',
            name='dedup_key',
            field=models.CharField(default='', max_length=64, verbose_name='Clave única'),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='watcheditem',
            name='source',
            field=models.CharField(
                choices=[('trakt', 'Trakt'), ('simkl', 'Simkl')],
                default='simkl', max_length=10, verbose_name='Fuente',
            ),
        ),
        migrations.AddField(
            model_name='watcheditem',
            name='imdb_id',
            field=models.CharField(blank=True, db_index=True, default='', max_length=20, verbose_name='ID IMDB'),
        ),
        migrations.AddField(
            model_name='watcheditem',
            name='simkl_id',
            field=models.PositiveIntegerField(blank=True, null=True, verbose_name='ID Simkl'),
        ),
        migrations.AlterField(
            model_name='watcheditem',
            name='tmdb_id',
            field=models.PositiveIntegerField(blank=True, db_index=True, null=True, verbose_name='ID TMDB'),
        ),
        migrations.AlterField(
            model_name='watcheditem',
            name='trakt_id',
            field=models.PositiveIntegerField(blank=True, null=True, verbose_name='ID Trakt'),
        ),
        migrations.AlterField(
            model_name='watcheditem',
            name='trakt_history_id',
            field=models.BigIntegerField(blank=True, null=True, unique=True, verbose_name='ID historial Trakt'),
        ),
        migrations.RunPython(backfill, noop),
        migrations.AlterField(
            model_name='watcheditem',
            name='dedup_key',
            field=models.CharField(max_length=64, unique=True, verbose_name='Clave única'),
        ),
        migrations.CreateModel(
            name='SimklSyncState',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('last_activity_at', models.CharField(blank=True, default='', max_length=40, verbose_name='Última actividad')),
                ('last_synced_at', models.DateTimeField(auto_now=True, verbose_name='Última corrida')),
            ],
            options={
                'verbose_name': 'Estado de sync Simkl',
                'verbose_name_plural': 'Estado de sync Simkl',
            },
        ),
    ]

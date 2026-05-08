# Generated manually for Spotify top song ordering.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('spotify', '0005_alter_deletedsongs_album_cover_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='spotifytopsongs',
            name='rank',
            field=models.PositiveSmallIntegerField(default=0),
        ),
        migrations.AlterModelOptions(
            name='spotifytopsongs',
            options={
                'ordering': ['rank', 'id'],
                'verbose_name': 'Canción Top',
                'verbose_name_plural': 'Canciones Top',
            },
        ),
    ]

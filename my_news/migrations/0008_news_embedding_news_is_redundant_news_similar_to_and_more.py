# Generated by Django 4.2.9 on 2025-02-28 01:58

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('my_news', '0007_filterword'),
    ]

    operations = [
        migrations.AddField(
            model_name='news',
            name='embedding',
            field=models.JSONField(blank=True, null=True, verbose_name='Embedding del contenido'),
        ),
        migrations.AddField(
            model_name='news',
            name='is_redundant',
            field=models.BooleanField(default=False, verbose_name='Es redundante'),
        ),
        migrations.AddField(
            model_name='news',
            name='similar_to',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='similar_news', to='my_news.news', verbose_name='Noticia similar'),
        ),
        migrations.AddField(
            model_name='news',
            name='similarity_score',
            field=models.FloatField(blank=True, null=True, verbose_name='Puntuación de similitud'),
        ),
    ]

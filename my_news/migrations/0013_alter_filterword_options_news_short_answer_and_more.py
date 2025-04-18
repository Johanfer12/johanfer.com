# Generated by Django 5.0.4 on 2025-04-03 20:38

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('my_news', '0012_feedsource_similarity_threshold'),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='filterword',
            options={'ordering': ['word'], 'verbose_name': 'Palabra Filtro', 'verbose_name_plural': 'Palabras Filtro'},
        ),
        migrations.AddField(
            model_name='news',
            name='short_answer',
            field=models.TextField(blank=True, null=True, verbose_name='Respuesta corta'),
        ),
        migrations.AlterField(
            model_name='news',
            name='filtered_by',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='filtered_news', to='my_news.filterword', verbose_name='Palabra Filtro'),
        ),
        migrations.AlterField(
            model_name='news',
            name='is_deleted',
            field=models.BooleanField(default=False, verbose_name='Eliminada'),
        ),
        migrations.AlterField(
            model_name='news',
            name='is_filtered',
            field=models.BooleanField(default=False, verbose_name='Filtro Aut.'),
        ),
        migrations.AlterField(
            model_name='news',
            name='is_redundant',
            field=models.BooleanField(default=False, verbose_name='Redundante'),
        ),
        migrations.AlterField(
            model_name='news',
            name='similarity_score',
            field=models.FloatField(blank=True, null=True, verbose_name='% Similitud'),
        ),
    ]

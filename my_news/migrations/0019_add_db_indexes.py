# Generated by Django 5.0.4 on 2025-06-29 20:57

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('my_news', '0018_alter_geminiglobalsetting_model_name'),
    ]

    operations = [
        migrations.AlterField(
            model_name='news',
            name='created_at',
            field=models.DateTimeField(auto_now_add=True, db_index=True),
        ),
        migrations.AlterField(
            model_name='news',
            name='is_ai_filtered',
            field=models.BooleanField(db_index=True, default=False, verbose_name='Filtro IA'),
        ),
        migrations.AlterField(
            model_name='news',
            name='is_deleted',
            field=models.BooleanField(db_index=True, default=False, verbose_name='Eliminada'),
        ),
        migrations.AlterField(
            model_name='news',
            name='is_filtered',
            field=models.BooleanField(db_index=True, default=False, verbose_name='Filtro Aut.'),
        ),
        migrations.AlterField(
            model_name='news',
            name='is_redundant',
            field=models.BooleanField(db_index=True, default=False, verbose_name='Redundante'),
        ),
        migrations.AlterField(
            model_name='news',
            name='published_date',
            field=models.DateTimeField(db_index=True),
        ),
        migrations.AddIndex(
            model_name='news',
            index=models.Index(fields=['created_at', 'is_deleted', 'is_filtered', 'is_ai_filtered', 'is_redundant'], name='news_visible_idx'),
        ),
        migrations.AddIndex(
            model_name='news',
            index=models.Index(fields=['source', 'published_date'], name='news_source_date_idx'),
        ),
        migrations.AddIndex(
            model_name='news',
            index=models.Index(fields=['is_redundant', 'is_filtered', 'embedding'], name='news_redundancy_idx'),
        ),
    ]

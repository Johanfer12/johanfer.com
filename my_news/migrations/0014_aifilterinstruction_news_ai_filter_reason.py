# Generated by Django 5.0.4 on 2025-04-04 01:07

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('my_news', '0013_alter_filterword_options_news_short_answer_and_more'),
    ]

    operations = [
        migrations.CreateModel(
            name='AIFilterInstruction',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('instruction', models.TextField(help_text="Describe el tipo de contenido a filtrar (ej: 'Noticias sobre horóscopos', 'Artículos de opinión política muy sesgados')", unique=True, verbose_name='Instrucción para IA')),
                ('active', models.BooleanField(default=True, verbose_name='Activo')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
            ],
            options={
                'verbose_name': 'Instrucción Filtro IA',
                'verbose_name_plural': 'Instrucciones Filtro IA',
                'ordering': ['-created_at'],
            },
        ),
        migrations.AddField(
            model_name='news',
            name='ai_filter_reason',
            field=models.TextField(blank=True, null=True, verbose_name='Razón Filtro IA'),
        ),
    ]

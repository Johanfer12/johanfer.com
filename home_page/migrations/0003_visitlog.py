from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('home_page', '0002_book_genres_deletedbook_genres'),
    ]

    operations = [
        migrations.CreateModel(
            name='VisitLog',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('ip_address', models.CharField(db_index=True, max_length=45)),
                ('country', models.CharField(blank=True, default='', max_length=120)),
                ('path', models.CharField(db_index=True, max_length=255)),
                ('user_agent', models.TextField(blank=True, default='')),
                ('referrer', models.TextField(blank=True, default='')),
                ('visited_at', models.DateTimeField(auto_now_add=True, db_index=True)),
            ],
            options={
                'verbose_name': 'Visita',
                'verbose_name_plural': 'Visitas',
                'ordering': ['-visited_at'],
            },
        ),
    ]

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('my_news', '0025_news_news_visible_pub_id_idx_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='news',
            name='is_saved',
            field=models.BooleanField(default=False, verbose_name='Guardada'),
        ),
    ]

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("my_news", "0028_news_deleted_at_news_news_deleted_at_idx"),
    ]

    operations = [
        migrations.RemoveIndex(
            model_name="news",
            name="news_redundancy_idx",
        ),
        migrations.RemoveField(
            model_name="news",
            name="embedding",
        ),
    ]

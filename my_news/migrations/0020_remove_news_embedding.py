from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("my_news", "0019_add_db_indexes"),
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

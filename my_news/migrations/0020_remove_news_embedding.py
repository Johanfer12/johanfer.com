"""Quita News.embedding: los vectores viven en Qdrant, no en SQLite.

OJO CON EL NUMERO: se llama 0020 pero depende de la 0028, asi que se aplica
despues de ella, no en el hueco que sugiere su nombre. `showmigrations` la
lista fuera de orden y confunde. No se renombra porque Django registra las
migraciones aplicadas por su nombre: cambiarlo haria que produccion la creyera
pendiente y volviera a intentar borrar una columna que ya no existe.
"""
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("my_news", "0028_news_deleted_at_news_news_deleted_at_idx"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="news",
            name="embedding",
        ),
    ]

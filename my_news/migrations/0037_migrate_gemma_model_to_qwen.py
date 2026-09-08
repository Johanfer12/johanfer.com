"""Cambia el modelo de resumenes de 'gemma-4-31b' a 'qwen-3.8-27b'.

Cerebras retiro el acceso a gemma-4-31b: sigue apareciendo en /v1/models pero
cualquier llamada real responde 404 model_not_found, asi que la ingesta se
pauso. qwen-3.8-27b es el sustituto disponible con la misma clave, y ademas
con topes mucho mas holgados (450 peticiones/minuto frente a 5).

Solo se toca la fila que sigue apuntando al modelo muerto: si el modelo se
cambio a mano desde el admin, esa eleccion se respeta.
"""

from django.db import migrations, models


OLD_MODEL = 'gemma-4-31b'
NEW_MODEL = 'qwen-3.8-27b'


def migrate_retired_model(apps, schema_editor):
    AIModelSetting = apps.get_model('my_news', 'AIModelSetting')
    AIModelSetting.objects.filter(model_name=OLD_MODEL).update(model_name=NEW_MODEL)


def revert_to_retired_model(apps, schema_editor):
    AIModelSetting = apps.get_model('my_news', 'AIModelSetting')
    AIModelSetting.objects.filter(model_name=NEW_MODEL).update(model_name=OLD_MODEL)


class Migration(migrations.Migration):

    dependencies = [
        ('my_news', '0036_remove_news_interest_score_remove_news_user_vote_and_more'),
    ]

    operations = [
        migrations.AlterField(
            model_name='aimodelsetting',
            name='model_name',
            field=models.CharField(
                default=NEW_MODEL,
                help_text="Nombre del modelo de IA a utilizar para resúmenes (ej: 'qwen-3.8-27b').",
                max_length=100,
                verbose_name='Modelo IA Global',
            ),
        ),
        migrations.RunPython(migrate_retired_model, revert_to_retired_model),
    ]

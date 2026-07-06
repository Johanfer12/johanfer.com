from django.db import migrations, models


class Migration(migrations.Migration):
    """Renombra CerebrasGlobalSetting a AIModelSetting (nombre neutral de
    proveedor, conserva los datos) y elimina los modelos muertos de
    configuraciones Gemini y Groq."""

    dependencies = [
        ('my_news', '0030_cerebrasglobalsetting'),
    ]

    operations = [
        migrations.RenameModel(
            old_name='CerebrasGlobalSetting',
            new_name='AIModelSetting',
        ),
        migrations.AlterModelOptions(
            name='aimodelsetting',
            options={
                'verbose_name': 'Configuración Global de Modelo IA',
                'verbose_name_plural': 'Configuraciones Globales de Modelo IA',
            },
        ),
        migrations.AlterField(
            model_name='aimodelsetting',
            name='model_name',
            field=models.CharField(
                default='gemma-4-31b',
                help_text="Nombre del modelo de IA a utilizar para resúmenes (ej: 'gemma-4-31b').",
                max_length=100,
                verbose_name='Modelo IA Global',
            ),
        ),
        migrations.DeleteModel(
            name='GeminiGlobalSetting',
        ),
        migrations.DeleteModel(
            name='GroqGlobalSetting',
        ),
    ]

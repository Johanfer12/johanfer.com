from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('watching', '0008_remove_simklsyncstate_in_progress_ids_and_more')]
    operations = [migrations.AddField(
        model_name='simklsyncstate', name='entry_pending',
        field=models.JSONField(default=dict, blank=True, verbose_name='Pendientes por entrada Simkl'),
    )]

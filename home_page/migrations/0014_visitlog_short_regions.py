from django.db import migrations

PREFIXES = (', Departamento del ', ', Departamento de ', ', Departamento ')


def shorten_regions(apps, schema_editor):
    """«Cali, Departamento del Valle del Cauca» → «Cali, Valle del Cauca».

    Son las ciudades que rellenó backfill_visit_ip_data desde ipwho.is antes
    de que acortara la región. Copia de middleware.short_region: una
    migración no debe importar código de la app.
    """
    VisitLog = apps.get_model('home_page', 'VisitLog')
    for visit in VisitLog.objects.filter(city__contains=', Departamento '):
        for prefix in PREFIXES:
            if prefix in visit.city:
                visit.city = visit.city.replace(prefix, ', ', 1)
                visit.save(update_fields=['city'])
                break


class Migration(migrations.Migration):

    dependencies = [
        ('home_page', '0013_visitlog_isp'),
    ]

    operations = [
        migrations.RunPython(shorten_regions, migrations.RunPython.noop),
    ]

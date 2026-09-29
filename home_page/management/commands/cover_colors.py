import os

from django.conf import settings
from django.core.management.base import BaseCommand

from home_page import cover_colors

FOLDERS = ('Covers', 'Posters')


class Command(BaseCommand):
    help = (
        "Anota el color medio de las portadas y carátulas ya descargadas "
        "(media/Covers y media/Posters). Las nuevas lo anotan solas al descargarse."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--todas', action='store_true',
            help="Recalcula también las que ya tienen color (p. ej. si se reemplazó la imagen).",
        )

    def handle(self, *args, **options):
        for subfolder in FOLDERS:
            folder = os.path.join(settings.MEDIA_ROOT, subfolder)
            if not os.path.isdir(folder):
                self.stdout.write(f"{subfolder}: no existe, se salta")
                continue

            data = dict(cover_colors.load_index(folder))
            names = sorted(
                name for name in os.listdir(folder)
                if name.lower().endswith('.webp') and not name.startswith('temp_')
            )
            present = set(names)
            # Colores de imágenes que ya no están: fuera del índice.
            stale = [name for name in data if name not in present]
            for name in stale:
                del data[name]

            added = 0
            for name in names:
                if name in data and not options['todas']:
                    continue
                color = cover_colors.average_color(os.path.join(folder, name))
                if color:
                    data[name] = color
                    added += 1

            cover_colors.save_index(folder, data)
            self.stdout.write(
                f"{subfolder}: {added} anotadas, {len(stale)} retiradas, {len(data)} en total"
            )

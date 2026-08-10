"""Regenera los iconos de la PWA.

El favicon original solo llega a 48x48, asi que en vez de escalarlo —lo que da
un icono borroso a 512— se redibuja su mismo motivo (luna creciente y dos
destellos) a la resolucion que haga falta.

    python manage.py generate_pwa_icons
"""
import math
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand

BG = (7, 7, 21, 255)          # --bg-1 del sitio
MOON = (177, 183, 205, 255)   # el mismo gris lavanda del favicon
OUTLINE = (0, 0, 0, 255)
SS = 4                        # supersampling antes de reducir


def _star_mask(size, cx, cy, r, inner=0.32, rot=-math.pi / 2):
    from PIL import Image, ImageDraw

    mask = Image.new('L', (size, size), 0)
    points = []
    for i in range(8):
        angle = rot + i * math.pi / 4
        radius = r if i % 2 == 0 else r * inner
        points.append((cx + radius * math.cos(angle), cy + radius * math.sin(angle)))
    ImageDraw.Draw(mask).polygon(points, fill=255)
    return mask


def _circle_mask(size, cx, cy, r):
    from PIL import Image, ImageDraw

    mask = Image.new('L', (size, size), 0)
    ImageDraw.Draw(mask).ellipse([cx - r, cy - r, cx + r, cy + r], fill=255)
    return mask


def _grow(mask, px):
    """Dilata la mascara px pixeles; asi se pinta el contorno negro."""
    from PIL import ImageFilter

    out = mask
    left = int(round(px))
    while left > 0:
        step = min(4, left)  # MaxFilter(2n+1) dilata n pixeles
        out = out.filter(ImageFilter.MaxFilter(step * 2 + 1))
        left -= step
    return out


def draw_icon(size, scale=1.0, radius_ratio=0.22):
    """scale < 1 encoge el motivo, para la zona segura de los iconos maskable."""
    from PIL import Image, ImageDraw

    S = size * SS
    img = Image.new('RGBA', (S, S), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    if radius_ratio:
        draw.rounded_rectangle([0, 0, S - 1, S - 1], radius=int(S * radius_ratio), fill=BG)
    else:
        draw.rectangle([0, 0, S - 1, S - 1], fill=BG)

    u = S * scale
    off = (S - u) / 2

    def P(x, y):
        return (off + x * u, off + y * u)

    stroke = max(1.0, u * 0.028)

    # Luna: circulo grande menos circulo desplazado.
    c1, r1 = P(0.44, 0.56), u * 0.38
    c2, r2 = P(0.68, 0.30), u * 0.33
    moon = Image.composite(
        Image.new('L', (S, S), 0),
        _circle_mask(S, c1[0], c1[1], r1),
        _circle_mask(S, c2[0], c2[1], r2),
    )

    shapes = [
        moon,
        _star_mask(S, *P(0.80, 0.20), u * 0.16),
        _star_mask(S, *P(0.585, 0.395), u * 0.085),
    ]
    union = shapes[0]
    for mask in shapes[1:]:
        union = Image.composite(Image.new('L', (S, S), 255), union, mask)

    # El contorno sale de dilatar la silueta; el relleno va encima.
    img.paste(Image.new('RGBA', (S, S), OUTLINE), (0, 0), _grow(union, stroke))
    img.paste(Image.new('RGBA', (S, S), MOON), (0, 0), union)
    return img.resize((size, size), Image.LANCZOS)


class Command(BaseCommand):
    help = 'Regenera los iconos PNG de la PWA en static/Img/.'

    def handle(self, *args, **options):
        out = Path(settings.BASE_DIR) / 'static' / 'Img'
        targets = [
            ('pwa-icon-192.png', dict(size=192)),
            ('pwa-icon-512.png', dict(size=512)),
            # El icono maskable se recorta: el motivo va al 70% y sin esquinas
            # redondeadas, que ya las pone el sistema.
            ('pwa-icon-maskable-512.png', dict(size=512, scale=0.70, radius_ratio=0)),
            ('apple-touch-icon.png', dict(size=180)),
        ]
        for name, kwargs in targets:
            draw_icon(**kwargs).save(out / name)
            self.stdout.write(self.style.SUCCESS(f'  {name}'))

        self.stdout.write('Iconos regenerados. Recuerda ejecutar collectstatic al desplegar.')

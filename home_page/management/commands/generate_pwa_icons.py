"""Regenera los iconos del sitio: favicon (SVG + ICO) e iconos de la PWA.

El motivo —luna creciente y dos destellos— se define UNA vez, en coordenadas
unitarias (`_geometria`), y de ahi salen las dos salidas: el SVG que se sirve a
los navegadores modernos y el rasterizado con Pillow para el ICO y los PNG. Asi
no hay dos dibujos que puedan divergir.

Antes el favicon era un bitmap suelto de 48x48 como maximo: en pantallas HiDPI
el navegador lo estiraba y se veia dentado. El SVG resuelve eso, y el ICO se
regenera con tamanos hasta 64 para los navegadores que no aceptan SVG.

    python manage.py generate_pwa_icons
"""
import math
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand

# Paleta: los mismos tokens de static/css/tokens.css.
GRAD = ((0x34, 0x1b, 0x63), (0x13, 0x1b, 0x46), (0x07, 0x07, 0x15))  # bg-3 -> bg-2 -> bg-1
MOON = (0xc6, 0xd6, 0xf5)  # --accent
SS = 4  # supersampling antes de reducir

# Motivo en coordenadas unitarias (0..1 sobre la caja del dibujo).
LUNA_FUERA = (0.44, 0.56, 0.38)   # cx, cy, r del circulo grande
LUNA_MUESCA = (0.68, 0.30, 0.33)  # cx, cy, r del circulo que se resta
DESTELLOS = (                     # cx, cy, r; el segundo desaparece en tamanos pequenos
    (0.80, 0.20, 0.16),
    (0.585, 0.395, 0.085),
)
ESTRELLA_INTERIOR = 0.32  # radio del valle respecto a la punta


def _geometria(scale, detalle=True):
    """Devuelve el motivo colocado en la caja unitaria, encogido a `scale`.

    `detalle=False` deja fuera el destello pequeno: por debajo de 32 px se
    convierte en tres pixeles sucios que solo ensucian la silueta.
    """
    off = (1.0 - scale) / 2

    def sitio(cx, cy, r):
        return (off + cx * scale, off + cy * scale, r * scale)

    destellos = DESTELLOS if detalle else DESTELLOS[:1]
    return {
        'fuera': sitio(*LUNA_FUERA),
        'muesca': sitio(*LUNA_MUESCA),
        'destellos': [sitio(*d) for d in destellos],
    }


def _puntas_estrella(cx, cy, r):
    """Los 8 vertices de un destello de cuatro puntas."""
    puntos = []
    for i in range(8):
        angulo = -math.pi / 2 + i * math.pi / 4
        radio = r if i % 2 == 0 else r * ESTRELLA_INTERIOR
        puntos.append((cx + radio * math.cos(angulo), cy + radio * math.sin(angulo)))
    return puntos


# --- SVG ---------------------------------------------------------------------


def construir_svg(size=64, scale=0.84, radius_ratio=0.22):
    g = _geometria(scale)
    u = size

    def n(v):
        return round(v * u, 2)

    fuera, muesca = g['fuera'], g['muesca']
    estrellas = '\n    '.join(
        '<polygon points="{}" fill="#{:02x}{:02x}{:02x}"/>'.format(
            ' '.join(f'{n(x)},{n(y)}' for x, y in _puntas_estrella(*d)), *MOON
        )
        for d in g['destellos']
    )
    (r1, g1, b1), (r2, g2, b2), (r3, g3, b3) = GRAD
    return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {u} {u}">
  <!-- Generado por `python manage.py generate_pwa_icons`. No editar a mano. -->
  <defs>
    <linearGradient id="cielo" x1="1" y1="0" x2="0" y2="1">
      <stop offset="0" stop-color="#{r1:02x}{g1:02x}{b1:02x}"/>
      <stop offset="0.5" stop-color="#{r2:02x}{g2:02x}{b2:02x}"/>
      <stop offset="1" stop-color="#{r3:02x}{g3:02x}{b3:02x}"/>
    </linearGradient>
    <mask id="luna">
      <circle cx="{n(fuera[0])}" cy="{n(fuera[1])}" r="{n(fuera[2])}" fill="#fff"/>
      <circle cx="{n(muesca[0])}" cy="{n(muesca[1])}" r="{n(muesca[2])}" fill="#000"/>
    </mask>
  </defs>
  <rect width="{u}" height="{u}" rx="{n(radius_ratio)}" fill="url(#cielo)"/>
  <circle cx="{n(fuera[0])}" cy="{n(fuera[1])}" r="{n(fuera[2])}"
          fill="#{MOON[0]:02x}{MOON[1]:02x}{MOON[2]:02x}" mask="url(#luna)"/>
  {estrellas}
</svg>
'''


# --- Rasterizado -------------------------------------------------------------


def _fondo_degradado(size):
    """Degradado diagonal (arriba-derecha -> abajo-izquierda) entre las 3 paradas."""
    from PIL import Image

    lado = 256
    pixeles = []
    for y in range(lado):
        for x in range(lado):
            t = ((lado - 1 - x) + y) / (2 * (lado - 1))
            if t < 0.5:
                a, b, k = GRAD[0], GRAD[1], t * 2
            else:
                a, b, k = GRAD[1], GRAD[2], (t - 0.5) * 2
            pixeles.append(tuple(int(round(a[i] + (b[i] - a[i]) * k)) for i in range(3)))
    grad = Image.new('RGB', (lado, lado))
    grad.putdata(pixeles)
    return grad.resize((size, size), Image.BICUBIC).convert('RGBA')


def _mascara_circulo(size, cx, cy, r):
    from PIL import Image, ImageDraw

    mask = Image.new('L', (size, size), 0)
    ImageDraw.Draw(mask).ellipse([cx - r, cy - r, cx + r, cy + r], fill=255)
    return mask


def draw_icon(size, scale=0.80, radius_ratio=0.22, detalle=True):
    """`scale` < 1 encoge el motivo; los iconos maskable necesitan zona segura."""
    from PIL import Image, ImageDraw

    S = size * SS
    g = _geometria(scale, detalle=detalle)

    img = _fondo_degradado(S)
    if radius_ratio:
        esquinas = Image.new('L', (S, S), 0)
        ImageDraw.Draw(esquinas).rounded_rectangle(
            [0, 0, S - 1, S - 1], radius=int(S * radius_ratio), fill=255
        )
        img.putalpha(esquinas)

    def P(v):
        return v * S

    fuera, muesca = g['fuera'], g['muesca']
    luna = Image.composite(
        Image.new('L', (S, S), 0),
        _mascara_circulo(S, P(fuera[0]), P(fuera[1]), P(fuera[2])),
        _mascara_circulo(S, P(muesca[0]), P(muesca[1]), P(muesca[2])),
    )

    union = luna
    for cx, cy, r in g['destellos']:
        estrella = Image.new('L', (S, S), 0)
        ImageDraw.Draw(estrella).polygon(
            [(P(x), P(y)) for x, y in _puntas_estrella(cx, cy, r)], fill=255
        )
        union = Image.composite(Image.new('L', (S, S), 255), union, estrella)

    img.paste(Image.new('RGBA', (S, S), MOON + (255,)), (0, 0), union)
    return img.resize((size, size), Image.LANCZOS)


class Command(BaseCommand):
    help = 'Regenera el favicon (SVG + ICO) y los iconos PNG de la PWA.'

    def handle(self, *args, **options):
        base = Path(settings.BASE_DIR) / 'static'
        img_dir = base / 'Img'

        (base / 'favicon.svg').write_text(construir_svg(), encoding='utf-8')
        self.stdout.write(self.style.SUCCESS('  favicon.svg'))

        # El ICO lleva varios tamanos; el detalle fino sobra por debajo de 48.
        marcos = [draw_icon(px, scale=0.84, detalle=px >= 48) for px in (16, 32, 48, 64)]
        marcos[-1].save(
            base / 'favicon.ico',
            format='ICO',
            sizes=[(m.width, m.height) for m in marcos],
            append_images=marcos[:-1],
        )
        self.stdout.write(self.style.SUCCESS('  favicon.ico (16/32/48/64)'))

        objetivos = [
            ('pwa-icon-192.png', dict(size=192)),
            ('pwa-icon-512.png', dict(size=512)),
            # El maskable se recorta: motivo al 62% y sin esquinas redondeadas,
            # que ya las pone el sistema.
            ('pwa-icon-maskable-512.png', dict(size=512, scale=0.62, radius_ratio=0)),
            ('apple-touch-icon.png', dict(size=180)),
        ]
        for nombre, kwargs in objetivos:
            draw_icon(**kwargs).save(img_dir / nombre)
            self.stdout.write(self.style.SUCCESS(f'  {nombre}'))

        self.stdout.write('Iconos regenerados. Recuerda ejecutar collectstatic al desplegar.')

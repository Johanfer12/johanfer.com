"""Color medio de cada portada y carátula, para pintar el hueco mientras cargan.

Mientras llega la imagen, todas las tarjetas eran el mismo rectángulo oscuro. Con
el color medio de su propia imagen el hueco ya anticipa lo que va a aparecer.

El color vive en un índice JSON junto a las imágenes (`media/Covers/.colors.json`
y `media/Posters/.colors.json`), no en la base: en TV hay una fila por episodio
pero una carátula por obra, y el color es de la imagen, no de la fila. Lo
escribe la descarga (`download_as_webp`) y lo rellena para lo ya descargado
`manage.py cover_colors`.
"""
import json
import logging
import os

from django.conf import settings
from PIL import Image

logger = logging.getLogger(__name__)

INDEX_NAME = '.colors.json'

# Índice leído por carpeta, junto con el mtime del fichero: se relee solo si ha
# cambiado, así que servir una rejilla no abre el JSON una vez por tarjeta.
_cache = {}


def average_color(path):
    """'#rrggbb' con el color medio de la imagen, o None si no se puede leer."""
    try:
        with Image.open(path) as image:
            pixel = image.convert('RGB').resize((1, 1), Image.Resampling.BOX).getpixel((0, 0))
    except Exception:
        logger.warning("No se pudo calcular el color de %s", path, exc_info=True)
        return None
    return '#{:02x}{:02x}{:02x}'.format(*pixel)


def _index_path(folder):
    return os.path.join(folder, INDEX_NAME)


def load_index(folder):
    path = _index_path(folder)
    try:
        mtime = os.path.getmtime(path)
    except OSError:
        return {}
    cached = _cache.get(folder)
    if cached and cached[0] == mtime:
        return cached[1]
    try:
        with open(path, encoding='utf-8') as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        logger.warning("Índice de colores ilegible: %s", path, exc_info=True)
        data = {}
    _cache[folder] = (mtime, data)
    return data


def save_index(folder, data):
    """Escribe el índice entero de una vez (temporal + rename: nunca a medias)."""
    path = _index_path(folder)
    temp = f'{path}.tmp'
    with open(temp, 'w', encoding='utf-8') as fh:
        json.dump(data, fh, separators=(',', ':'), sort_keys=True)
    os.replace(temp, path)
    _cache.pop(folder, None)


def remember(file_path):
    """Calcula y anota el color de una imagen recién guardada."""
    color = average_color(file_path)
    if not color:
        return None
    folder, name = os.path.split(file_path)
    data = dict(load_index(folder))
    if data.get(name) != color:
        data[name] = color
        save_index(folder, data)
    return color


def color_for(subfolder, name):
    """Color anotado para `media/<subfolder>/<name>`, o '' si no hay."""
    if not name:
        return ''
    return load_index(os.path.join(settings.MEDIA_ROOT, subfolder)).get(name, '')

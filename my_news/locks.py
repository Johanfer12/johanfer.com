"""Cerrojo de la ingesta de noticias.

Vive aparte de `tasks.py` porque la web también lo consulta (el botón de
actualizar del feed), y `tasks.py` arrastra `services.py` con numpy, feedparser
y el resto de la ingesta: el proceso de gunicorn no necesita nada de eso para
saber si hay una pasada en marcha.
"""
import os

import portalocker
from django.conf import settings


def update_lock_path():
    # En BASE_DIR y no en /tmp: ahí el sistema puede borrarlo en limpiezas/reinicios.
    return os.path.join(settings.BASE_DIR, 'my_news_update.lock')


def news_update_running():
    """Indica si hay una pasada en marcha (del cron o lanzada desde el feed)."""
    try:
        with portalocker.Lock(update_lock_path(), timeout=0):
            return False
    except portalocker.exceptions.LockException:
        return True

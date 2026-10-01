from django import template
from django.conf import settings

register = template.Library()

# Las imágenes de las noticias son de los medios y se piden a través de
# Cloudflare Images (Transformations, activado en la zona con "cualquier
# origen"). Cloudflare las descarga del medio, no de la Pi, y las cachea.
#
# - width=1280 + scale-down: solo achica las que sobran. Casi todas llegan a
#   ~1024 px, que ya es menos de lo que pide la tarjeta en un móvil; las que se
#   pasan (Wowhead manda 3840×2160) son las que cuestan decodificar.
# - format=webp y NO auto: auto sirve AVIF, que en un Helio G99 tarda el doble
#   en decodificarse (~42 ms frente a ~21 de JPEG y WebP). WebP pesa un 15-25%
#   menos que el JPEG original y se decodifica igual de rápido.
# - onerror=redirect: si Cloudflare no puede (medio que bloquea, cuota del plan
#   gratuito agotada: 5.000 imágenes únicas al mes), redirige al original.
#   Por si ni eso, news_cards_common.js reintenta con data-original-src.
CDN_OPTIONS = 'width=1280,fit=scale-down,format=webp,onerror=redirect'


def cdn_path(url):
    """Ruta /cdn-cgi/... de una imagen, o None si no pasa por Cloudflare."""
    if not url or not settings.NEWS_IMAGE_CDN:
        return None
    if not url.startswith(('http://', 'https://')):
        return None
    return f'/cdn-cgi/image/{CDN_OPTIONS}/{url}'


@register.filter
def news_image_src(url):
    """URL de la imagen de una noticia, pasada por Cloudflare en producción.

    En local no existe /cdn-cgi/, así que se devuelve la original.
    """
    return cdn_path(url) or url


# Primera petición de cada imagen: Cloudflare tiene que bajarla del medio,
# convertirla y guardarla antes de responder (medido: 0,6-1,8 s, frente a ~0,25
# ya cacheada). Si esa primera petición la hace el lector, la paga él; por eso
# la ingesta la hace antes, solo con las noticias que de verdad se van a ver.
WARM_BASE_URL = 'https://johanfer.com'
WARM_WORKERS = 4
WARM_TIMEOUT = 20


def warm_news_images(urls):
    """Pide a Cloudflare las imágenes para que ya estén cacheadas. Devuelve cuántas.

    Nunca lanza: calentar es una mejora, no puede romper la ingesta.
    Se lleva la cabecera Accept de un navegador porque sin ella Cloudflare
    devuelve el JPEG original sin transformar ni cachear la variante WebP.
    """
    import logging
    from concurrent.futures import ThreadPoolExecutor
    import requests

    paths = [p for p in dict.fromkeys(cdn_path(u) for u in urls) if p]
    if not paths:
        return 0

    def pedir(path):
        try:
            # Se descarga el cuerpo entero: cortar la conexión a medias
            # podría hacer que Cloudflare no llegue a guardar la variante.
            r = requests.get(
                WARM_BASE_URL + path,
                headers={'Accept': 'image/webp,*/*'},
                timeout=WARM_TIMEOUT,
            )
            return r.status_code < 400
        except Exception:
            return False

    try:
        with ThreadPoolExecutor(max_workers=WARM_WORKERS) as pool:
            ok = sum(pool.map(pedir, paths))
    except Exception:
        logging.getLogger(__name__).exception('No se pudo calentar la caché de imágenes')
        return 0
    logging.getLogger(__name__).info('Imágenes calentadas en Cloudflare: %s de %s', ok, len(paths))
    return ok

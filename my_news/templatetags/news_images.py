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


@register.filter
def news_image_src(url):
    """URL de la imagen de una noticia, pasada por Cloudflare en producción.

    En local no existe /cdn-cgi/, así que se devuelve la original.
    """
    if not url or not settings.NEWS_IMAGE_CDN:
        return url
    if not url.startswith(('http://', 'https://')):
        return url
    return f'/cdn-cgi/image/{CDN_OPTIONS}/{url}'

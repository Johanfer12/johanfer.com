"""Contador de visitas ajenas desde Colombia (el que se pinta en la cabecera).

Cuenta lo que aún no se ha mirado: abrir /visitas/ sella las visitas como
vistas y la insignia se apaga, sin necesidad de borrar nada.
"""
from django.core.cache import cache
from django.db.models import Q
from django.utils import timezone as dj_timezone

from .models import OwnerSignature, VisitLog

BADGE_CACHE_KEY = 'visits-badge-colombia'
BADGE_CACHE_TTL = 60 * 60  # Se invalida al registrar una visita nueva.


def colombian_filter():
    # country_code se rellena desde ipwho.is, pero las filas antiguas solo
    # tenían el nombre del país.
    return Q(country_code__iexact='CO') | Q(country__icontains='colombia')


def exclude_owner(visit_qs):
    """Quita las visitas propias: IP o visitor_id que hayan pasado por el login."""
    ips = set()
    visitor_ids = set()
    for ip, visitor_id in OwnerSignature.objects.values_list('ip_address', 'visitor_id'):
        if ip:
            ips.add(ip)
        if visitor_id:
            visitor_ids.add(visitor_id)

    if ips:
        visit_qs = visit_qs.exclude(ip_address__in=ips)
    if visitor_ids:
        visit_qs = visit_qs.exclude(visitor_id__in=visitor_ids)
    return visit_qs


def foreign_colombian_visits():
    return exclude_owner(VisitLog.objects.filter(colombian_filter()))


def mark_seen(visit_qs=None):
    """Sella lo que se acaba de mirar en /visitas/.

    Se sella solo lo que se ha visto de verdad: con un filtro activo, las
    visitas que quedaron fuera siguen pendientes. Devuelve cuántas se sellaron.
    """
    if visit_qs is None:
        visit_qs = VisitLog.objects.all()

    marked = visit_qs.filter(seen_at__isnull=True).update(
        seen_at=dj_timezone.now(),
    )
    if marked:
        invalidate_badge()
    return marked


def badge_count():
    cached = cache.get(BADGE_CACHE_KEY)
    if cached is not None:
        return cached

    count = foreign_colombian_visits().filter(seen_at__isnull=True).count()
    cache.set(BADGE_CACHE_KEY, count, BADGE_CACHE_TTL)
    return count


def invalidate_badge():
    cache.delete(BADGE_CACHE_KEY)

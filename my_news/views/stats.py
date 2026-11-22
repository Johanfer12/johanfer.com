"""Estadísticas: noticias por fuente y por día, y el estado de la Raspberry Pi."""
import json
import platform
import subprocess
from datetime import timedelta

from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.http import require_GET

from Bookshelf.http_utils import superuser_required

from ..models import News
from .common import _day_bounds_local


# Ventanas del panel de estadísticas. 15 es lo que conserva `purge_old_news`,
# así que esa opción equivale a «todo lo que hay en la base».
NEWS_STATS_WINDOWS = (1, 7, 15)


NEWS_STATS_RETENTION_DAYS = 15


def _news_stats_rows(days):
    """Noticias por fuente y por día, repartidas entre feed y descartadas.

    Se agrupa en Python y no en SQL: son ~2.300 filas y así el día se calcula
    en la zona horaria local, que SQLite no convierte por su cuenta.
    """
    # El corte es la medianoche local del primer día de la ventana, no «hace N
    # horas»: si no, entran noticias del día anterior al primero de la gráfica
    # y el total de las tarjetas no cuadra con el de las barras por día.
    first_day = timezone.localdate() - timedelta(days=days - 1)
    _, cutoff, _ = _day_bounds_local(first_day)
    rows = News.objects.filter(published_date__gte=cutoff).values_list(
        'source__name', 'published_date',
        'is_filtered', 'is_ai_filtered', 'is_redundant', 'is_ai_processed',
    )

    per_source = {}
    per_day = {}
    for name, published, filtered, ai_filtered, redundant, processed in rows:
        # La fuente es obligatoria, pero su nombre puede quedar en blanco.
        name = name or 'Sin nombre'
        # Mismo criterio que el manager de noticias visibles, menos el borrado
        # personal: lo leído sigue contando como que llegó al feed.
        in_feed = processed and not (filtered or ai_filtered or redundant)
        bucket = per_source.setdefault(name, {'feed': 0, 'discarded': 0})
        bucket['feed' if in_feed else 'discarded'] += 1

        day = timezone.localtime(published).date().isoformat()
        day_bucket = per_day.setdefault(day, {'feed': 0, 'discarded': 0})
        day_bucket['feed' if in_feed else 'discarded'] += 1

    return per_source, per_day


@require_GET
@superuser_required
def news_stats(request):
    """Cuántas noticias trae cada fuente y cuántas se quedan por el camino."""
    try:
        days = int(request.GET.get('dias') or 7)
    except (TypeError, ValueError):
        days = 7
    if days not in NEWS_STATS_WINDOWS:
        days = 7

    per_source, per_day = _news_stats_rows(days)

    # De más a menos, que es como se quiere leer un ranking de fuentes.
    ordered = sorted(
        per_source.items(),
        key=lambda item: (-(item[1]['feed'] + item[1]['discarded']), item[0]),
    )
    source_labels = [name for name, _ in ordered]
    source_feed = [counts['feed'] for _, counts in ordered]
    source_discarded = [counts['discarded'] for _, counts in ordered]

    # Todos los días de la ventana, también los que no trajeron nada: un hueco
    # es justo lo que se quiere ver si la ingesta se paró.
    today = timezone.localdate()
    day_keys = [(today - timedelta(days=offset)).isoformat() for offset in range(days - 1, -1, -1)]
    day_feed = [per_day.get(day, {}).get('feed', 0) for day in day_keys]
    day_discarded = [per_day.get(day, {}).get('discarded', 0) for day in day_keys]

    total_feed = sum(source_feed)
    total_discarded = sum(source_discarded)
    total = total_feed + total_discarded

    context = {
        'days': days,
        'windows': NEWS_STATS_WINDOWS,
        'retention_days': NEWS_STATS_RETENTION_DAYS,
        'total_news_window': total,
        'total_feed': total_feed,
        'total_discarded': total_discarded,
        'discarded_share': round(total_discarded * 100 / total) if total else 0,
        'daily_average': round(total / days, 1) if days else 0,
        'source_count': len(ordered),
        'source_labels_json': json.dumps(source_labels),
        'source_feed_json': json.dumps(source_feed),
        'source_discarded_json': json.dumps(source_discarded),
        'day_labels_json': json.dumps([day[8:10] + '/' + day[5:7] for day in day_keys]),
        'day_feed_json': json.dumps(day_feed),
        'day_discarded_json': json.dumps(day_discarded),
    }
    return render(request, 'news_stats.html', context)


VCGENCMD = '/usr/bin/vcgencmd'

# Avisos de `vcgencmd get_throttled`: los bits bajos son lo que pasa ahora y
# los altos lo que ha pasado desde el arranque.
THROTTLED_FLAGS = (
    (0x1, "Under-voltage detectado"),
    (0x2, "Límite de frecuencia ARM"),
    (0x4, "Actualmente limitado"),
    (0x8, "Soft temperature limit activo"),
    (0x10000, "Under-voltage ha ocurrido"),
    (0x20000, "Límite de frecuencia ARM ha ocurrido"),
    (0x40000, "Throttling ha ocurrido"),
    (0x80000, "Soft temperature limit ha ocurrido"),
)


def _vcgencmd(*args):
    """Salida de `vcgencmd` sin espacios a los lados, o None si falló.

    Las excepciones (no está instalado, tarda más de 5 s) se dejan subir:
    cada dato las enseña en su casilla.
    """
    result = subprocess.run([VCGENCMD, *args], capture_output=True, text=True, timeout=5)
    if result.returncode != 0:
        return None
    return result.stdout.strip()


def _temperature_label(output):
    """«temp=48.3'C» → «48.3°C»."""
    return output.replace("temp=", "").replace("'C", "") + "°C"


def _throttled_label(output):
    throttled_val = int(output.split('=')[1], 16)
    if throttled_val == 0:
        return "No hay limitaciones"
    return ", ".join(label for flag, label in THROTTLED_FLAGS if throttled_val & flag)


# (clave en la plantilla, argumentos de vcgencmd, cómo leer su salida)
VCGENCMD_STATS = (
    ('temperature', ('measure_temp',), _temperature_label),
    ('voltage', ('measure_volts', 'core'), lambda out: out.replace('volt=', '')),
    ('cpu_frequency', ('measure_clock', 'arm'),
     lambda out: f"{int(out.split('=')[1]) / 1000000:.0f} MHz"),
    ('memory_arm', ('get_mem', 'arm'), lambda out: out.replace('arm=', '')),
    ('memory_gpu', ('get_mem', 'gpu'), lambda out: out.replace('gpu=', '')),
    # Si el Pi está limitando el rendimiento por temperatura o voltaje.
    ('throttled', ('get_throttled',), _throttled_label),
)


@require_GET
@superuser_required
def system_stats(request):
    """Vista para mostrar estadísticas del sistema Raspberry Pi"""
    stats = {}
    is_raspberry_pi = False
    error_message = None

    try:
        # Detectar si estamos en Raspberry Pi
        system_info = platform.uname()
        is_raspberry_pi = 'arm' in system_info.machine.lower() or 'aarch64' in system_info.machine.lower()

        if is_raspberry_pi:
            for key, args, parse in VCGENCMD_STATS:
                try:
                    output = _vcgencmd(*args)
                    if output is not None:
                        stats[key] = parse(output)
                except Exception as e:
                    stats[key] = f"Error: {str(e)}"
        else:
            error_message = "Este sistema no es un Raspberry Pi. Las estadísticas de vcgencmd no están disponibles."

        # Información del sistema (disponible en cualquier plataforma)
        stats['system'] = f"{system_info.system} {system_info.release}"
        stats['machine'] = system_info.machine
        stats['hostname'] = system_info.node

        # Uptime (intentar obtener en Linux)
        try:
            with open('/proc/uptime', 'r') as f:
                uptime_seconds = float(f.readline().split()[0])
            total_minutes, _ = divmod(int(uptime_seconds), 60)
            total_hours, minutes = divmod(total_minutes, 60)
            total_days, hours = divmod(total_hours, 24)
            months, rest_days = divmod(total_days, 30)
            weeks, days = divmod(rest_days, 7)
            parts = []
            if months:
                parts.append(f"{months} mes" if months == 1 else f"{months} meses")
            if weeks:
                parts.append(f"{weeks} semana" if weeks == 1 else f"{weeks} semanas")
            if days:
                parts.append(f"{days} día" if days == 1 else f"{days} días")
            if hours:
                parts.append(f"{hours}h")
            parts.append(f"{minutes}m")
            stats['uptime'] = ' '.join(parts)
        except Exception:
            stats['uptime'] = "N/A"

        # Carga del sistema
        try:
            with open('/proc/loadavg', 'r') as f:
                load_avg = f.readline().split()[:3]
                stats['load_average'] = f"{load_avg[0]} {load_avg[1]} {load_avg[2]}"
        except Exception:
            stats['load_average'] = "N/A"

    except Exception as e:
        error_message = f"Error al obtener estadísticas: {str(e)}"

    context = {
        'stats': stats,
        'is_raspberry_pi': is_raspberry_pi,
        'error_message': error_message,
    }

    return render(request, 'system_stats.html', context)

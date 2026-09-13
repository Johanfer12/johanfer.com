"""Recuperación explícita de marcas locales de Nuvio que no llegaron a Simkl."""

import json
import re
from datetime import datetime, timezone

from .anime_mapping import resolve_series_anime


def read_watched(path, profile='1'):
    # java.util.Properties escapa :, =, unicode y las barras del JSON.
    def unescape(match):
        value = match.group(1)
        if value.startswith('u') and len(value) == 5:
            return chr(int(value[1:], 16))
        return {'n': '\n', 'r': '\r', 't': '\t', 'f': '\f'}.get(value, value)
    for line in path.read_text(encoding='utf-8').splitlines():
        key, sep, value = line.partition('=')
        if sep and key == f'watched_{profile}':
            result = json.loads(re.sub(r'\\(u[0-9a-fA-F]{4}|.)', unescape, value))
            if isinstance(result, dict):
                provider = (result.get('providerPayloads') or {}).get('simkl') or {}
                result = provider.get('itemGroups', result.get('items'))
            if not isinstance(result, list):
                raise ValueError('Formato de historial Nuvio desconocido')
            return result
    raise ValueError('No existe el perfil solicitado en el archivo')


def recovery_candidates(records, content_id, since, fetch_catalog):
    """Solo marcas watched explícitas; nunca convertir progreso parcial en visto."""
    resolved = {}
    unresolved = []
    for record in records:
        if record.get('id') != content_id:
            continue
        for event in record.get('entries') or []:
            try:
                when = datetime.fromtimestamp(event['markedAtEpochMs'] / 1000, timezone.utc)
                if when < since:
                    continue
                target = resolve_series_anime(content_id, event.get('season'), event.get('episode'), fetch_catalog)
                key = (target.simkl_id, target.number)
                # Repetir una lectura no crea un rewatch ni cambia la primera fecha.
                if key not in resolved or when < resolved[key][1]:
                    resolved[key] = (target, when)
            except (ValueError, KeyError, TypeError, OverflowError) as exc:
                unresolved.append({'season': event.get('season'), 'episode': event.get('episode'), 'reason': str(exc)})
    return list(resolved.values()), unresolved

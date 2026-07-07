from datetime import timedelta

from django.shortcuts import render
from django.utils import timezone

from .models import WatchedItem

# Una serie con actividad en esta ventana se considera "en curso" (listón Viendo)
WATCHING_WINDOW_DAYS = 14


def _group_by_media(items):
    """Agrupa los eventos por obra (trakt_id): una tarjeta por serie/película.

    El queryset llega ordenado por -watched_at, así que el primer evento de
    cada obra es el más reciente y el orden de las tarjetas queda cronológico.
    """
    shows = {}
    movies = {}
    for item in items:
        if item.media_type == 'episode':
            episode_key = (item.season, item.episode)
            entry = shows.get(item.trakt_id)
            if entry is None:
                shows[item.trakt_id] = {
                    'latest': item,
                    'plays': 1,
                    'episode_keys': {episode_key},
                    'episode_count': 1,
                    'episode_total': item.total_episodes or 1,
                    'available_episodes': item.available_episodes,
                }
            else:
                entry['plays'] += 1
                entry['episode_keys'].add(episode_key)
                entry['episode_count'] = len(entry['episode_keys'])
                entry['episode_total'] = max(
                    entry['episode_total'],
                    item.total_episodes or entry['episode_count'],
                )
                if item.available_episodes:
                    entry['available_episodes'] = max(
                        entry['available_episodes'] or 0,
                        item.available_episodes,
                    )
            continue

        bucket = movies
        entry = bucket.get(item.trakt_id)
        if entry is None:
            bucket[item.trakt_id] = {'latest': item, 'plays': 1}
        else:
            entry['plays'] += 1
    return list(shows.values()), list(movies.values())


def watching(request):
    tipo = request.GET.get('tipo', 'series')
    if tipo not in ('series', 'peliculas'):
        tipo = 'series'

    items = list(WatchedItem.objects.all())
    show_cards, movie_cards = _group_by_media(items)

    watching_cutoff = timezone.now() - timedelta(days=WATCHING_WINDOW_DAYS)
    for card in show_cards:
        available = card.get('available_episodes')
        seen_total = card.get('episode_total') or card.get('episode_count') or 0
        is_complete = bool(available and seen_total >= available)
        card['is_watching'] = card['latest'].watched_at >= watching_cutoff and not is_complete

    if tipo == 'peliculas':
        cards, watch_label = movie_cards, 'películas'
    else:
        cards, watch_label = show_cards, 'series'

    return render(request, 'watching.html', {
        'cards': cards,
        'active_tipo': tipo,
        'watch_label': watch_label,
        'total_watched': len(cards),
    })

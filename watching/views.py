import json
from collections import Counter, defaultdict
from datetime import timedelta

from django.conf import settings
from django.core.paginator import Paginator
from django.http import JsonResponse
from django.shortcuts import render
from django.utils import timezone

from Bookshelf.html_sanitizer import sanitize_html
from home_page.templatetags.sanitizers import rating_stars

from .models import WatchedItem

# Una serie con actividad en esta ventana se considera "en curso" (listón Viendo)
WATCHING_WINDOW_DAYS = 14


def _group_by_media(items):
    """Agrupa los eventos por obra (trakt_id): una tarjeta por serie/película.

    El queryset llega ordenado por (-watched_at, -season, -episode), así que el
    primer evento de cada obra es el más reciente; ante fechas empatadas gana el
    episodio más alto (para que 'latest' sea el finale, no un episodio arbitrario).
    """
    shows = {}
    movies = {}
    for item in items:
        watched_year = timezone.localtime(item.watched_at).year
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
                    'watched_years': {watched_year},
                }
            else:
                entry['plays'] += 1
                entry['episode_keys'].add(episode_key)
                entry['episode_count'] = len(entry['episode_keys'])
                entry['episode_total'] = max(
                    entry['episode_total'],
                    item.total_episodes or entry['episode_count'],
                )
                entry['watched_years'].add(watched_year)
                if item.available_episodes:
                    entry['available_episodes'] = max(
                        entry['available_episodes'] or 0,
                        item.available_episodes,
                    )
            continue

        bucket = movies
        entry = bucket.get(item.trakt_id)
        if entry is None:
            bucket[item.trakt_id] = {'latest': item, 'plays': 1, 'watched_years': {watched_year}}
        else:
            entry['plays'] += 1
            entry['watched_years'].add(watched_year)
    return list(shows.values()), list(movies.values())


def _sort_cards(cards, orden):
    """Ordena las tarjetas por fecha de última vista o por mi nota."""
    if orden == 'fecha_asc':
        cards.sort(key=lambda c: c['latest'].watched_at)
    elif orden == 'nota_desc':
        cards.sort(key=lambda c: (c['latest'].user_rating or 0, c['latest'].watched_at), reverse=True)
    elif orden == 'nota_asc':
        # Sin nota (None) al final también en ascendente
        cards.sort(key=lambda c: (c['latest'].user_rating or 11, c['latest'].watched_at))
    else:  # fecha_desc (orden por defecto)
        cards.sort(key=lambda c: c['latest'].watched_at, reverse=True)


def watching(request):
    tipo = request.GET.get('tipo', 'series')
    if tipo not in ('series', 'peliculas'):
        tipo = 'series'
    orden = request.GET.get('orden', 'fecha_desc')
    if orden not in ('fecha_desc', 'fecha_asc', 'nota_desc', 'nota_asc'):
        orden = 'fecha_desc'
    query = (request.GET.get('q') or '').strip()

    # Orden por fecha desc; en empate (p.ej. una temporada marcada de golpe con la
    # misma fecha) gana el episodio más alto, para que "Último" sea el finale real.
    items = list(WatchedItem.objects.order_by('-watched_at', '-season', '-episode'))
    show_cards, movie_cards = _group_by_media(items)

    watching_cutoff = timezone.now() - timedelta(days=WATCHING_WINDOW_DAYS)
    for card in show_cards:
        available = card.get('available_episodes')
        seen_total = card.get('episode_total') or card.get('episode_count') or 0
        is_complete = bool(available and seen_total >= available)
        card['is_watching'] = card['latest'].watched_at >= watching_cutoff and not is_complete

    if tipo == 'peliculas':
        cards, watch_label, watch_noun = movie_cards, 'películas', 'película'
    else:
        cards, watch_label, watch_noun = show_cards, 'series', 'serie'
    if query:
        needle = query.lower()
        year = int(query) if query.isdigit() else None
        cards = [
            c for c in cards
            if needle in c['latest'].title.lower()
            or (year is not None and year in c.get('watched_years', ()))
        ]
    _sort_cards(cards, orden)

    paginator = Paginator(cards, 20)  # 20 tarjetas por vista, igual que en libros
    page_obj = paginator.get_page(request.GET.get('page', 1))

    if request.headers.get('x-requested-with') == 'XMLHttpRequest':
        card_data = []
        for card in page_obj:
            latest = card['latest']
            card_data.append({
                'id': latest.id,
                'title': latest.title,
                'media_type': latest.media_type,
                'poster_url': f"{settings.MEDIA_URL}Posters/{latest.poster_name}",
                'trakt_url': latest.trakt_url or '#',
                'year': latest.year,
                'episode_total': card.get('episode_total'),
                'display_label': latest.display_label,
                'episode_title': latest.episode_title,
                'plays': card.get('plays', 1),
                'user_rating_html': rating_stars(latest.user_rating),
                'public_rating_html': rating_stars(latest.public_rating),
                'watched_at': timezone.localtime(latest.watched_at).strftime('%d/%m/%Y'),
                'overview': sanitize_html(latest.overview) if latest.overview else '',
                'is_watching': card.get('is_watching', False),
            })
        return JsonResponse({
            'cards': card_data,
            'has_next': page_obj.has_next(),
            'total_watched': paginator.count,
            'query': query,
        })

    return render(request, 'watching.html', {
        'cards': page_obj,
        'active_tipo': tipo,
        'active_orden': orden,
        'watch_label': watch_label,
        'watch_noun': watch_noun,
        'total_watched': paginator.count,
        'current_query': query,
    })


def _stars_label(rating):
    """Nota Trakt 1-10 -> estrellas del sitio (5 con medias), ej. 7 -> ★★★½."""
    five_star = rating / 2
    label = '★' * int(five_star)
    if five_star % 1:
        label += '½'
    return label


def watching_stats(request):
    # El historial personal es pequeño: se agrupa en Python, lo que además
    # permite usar la zona horaria local (SQLite no convierte fechas solo).
    shows_by_year = defaultdict(set)
    movies_by_year = defaultdict(set)
    work_ratings = {}  # una obra (tipo, trakt_id) -> mi nota
    release_years = {}  # una obra (tipo, trakt_id) -> año de estreno

    for item in WatchedItem.objects.all():
        work_key = (item.media_type == 'episode', item.trakt_id)
        if item.year:
            release_years.setdefault(work_key, item.year)
        if item.user_rating:
            work_ratings.setdefault(work_key, item.user_rating)
        local_dt = timezone.localtime(item.watched_at)
        # Trakt marca con el epoch Unix (1969/1970 local) lo visto sin fecha
        # conocida: fuera de las estadísticas temporales.
        if local_dt.year <= 1970:
            continue
        if item.media_type == 'episode':
            shows_by_year[local_dt.year].add(item.trakt_id)
        else:
            movies_by_year[local_dt.year].add(item.trakt_id)

    years = sorted(set(shows_by_year) | set(movies_by_year))
    rating_counts = Counter(work_ratings.values())
    ratings = sorted(rating_counts)
    decade_counts = Counter((year // 10) * 10 for year in release_years.values())
    decades = sorted(decade_counts)

    context = {
        'years_labels': json.dumps(years),
        'shows_per_year': json.dumps([len(shows_by_year.get(year, ())) for year in years]),
        'movies_per_year': json.dumps([len(movies_by_year.get(year, ())) for year in years]),
        'ratings_labels': json.dumps([_stars_label(rating) for rating in ratings]),
        'ratings_values': json.dumps([rating_counts[rating] for rating in ratings]),
        'decades_labels': json.dumps([f'{decade}s' for decade in decades]),
        'decades_values': json.dumps([decade_counts[decade] for decade in decades]),
    }
    return render(request, 'watching_stats.html', context)

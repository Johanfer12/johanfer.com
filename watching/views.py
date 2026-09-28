import json
import os
from collections import Counter, defaultdict
from datetime import timedelta

from django.conf import settings
from django.core.paginator import Paginator
from django.http import JsonResponse
from django.shortcuts import render
from django.utils import timezone

from Bookshelf.html_sanitizer import sanitize_html
from home_page.templatetags.sanitizers import rating_stars

from .models import SimklSyncState, WatchedItem

# Ventana de actividad para el listón "Viendo": una serie con episodios pendientes que
# no se toca en tres semanas deja de contar como en curso.
WATCHING_WINDOW_DAYS = 21


def _group_by_media(items):
    """Agrupa los eventos por obra (tmdb_id): una tarjeta por serie/película.

    Se agrupa por TMDB y no por el id de la fuente porque el historial viene de dos
    épocas (Trakt hasta julio 2026, Simkl desde agosto) y TMDB es el único id que
    ambas comparten.

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
            entry = shows.get(item.tmdb_id)
            if entry is None:
                shows[item.tmdb_id] = {
                    'latest': item,
                    'plays': 1,
                    'episode_keys': {episode_key},
                    'episode_count': 1,
                    'episode_total': item.total_episodes or 1,
                    'watched_years': {watched_year},
                    'part_titles': set(),
                    'has_legacy_rows': False,
                }
                entry = shows[item.tmdb_id]
            else:
                entry['plays'] += 1
                entry['episode_keys'].add(episode_key)
                entry['episode_count'] = len(entry['episode_keys'])
                entry['episode_total'] = max(
                    entry['episode_total'],
                    item.total_episodes or entry['episode_count'],
                )
                entry['watched_years'].add(watched_year)
            if item.part_title:
                entry['part_titles'].add(item.part_title)
            else:
                entry['has_legacy_rows'] = True
            continue

        bucket = movies
        entry = bucket.get(item.tmdb_id)
        if entry is None:
            bucket[item.tmdb_id] = {'latest': item, 'plays': 1, 'watched_years': {watched_year}}
        else:
            entry['plays'] += 1
            entry['watched_years'].add(watched_year)
    return list(shows.values()), list(movies.values())


def _arc_label(part_title, part_titles, work_title):
    """Lo que distingue a un arco de los demás de la misma obra.

    Las fichas de Simkl repiten el nombre de la franquicia en cualquier posición
    ("JoJo no Kimyou na Bouken: Stone Ocean", "Steel Ball Run: JoJo no Kimyou na
    Bouken"), así que se parte por ': ' y se descarta lo que comparten.
    """
    split = lambda title: [s.strip() for s in title.split(': ') if s.strip()]
    counts = Counter(s.casefold() for title in part_titles for s in set(split(title)))
    shared = {s for s, n in counts.items() if n > 1} | {work_title.casefold()}
    return ': '.join(s for s in split(part_title) if s.casefold() not in shared)


def _apply_arcs(show_cards):
    """Arco y carátula de la parte más reciente, en el anime que Simkl parte en varias.

    El arco solo se nombra si hay al menos dos fichas con nombre distinto. La carátula
    cambia también cuando la otra parte es el historial de Trakt (Re:Zero): basta con
    que la obra tenga más de una. Si la del arco aún no está en disco, se queda la de
    TMDB en vez de pintar el hueco.
    """
    posters_dir = os.path.join(settings.MEDIA_ROOT, 'Posters')
    for card in show_cards:
        latest = card['latest']
        card['poster_name'] = latest.poster_name
        card['arc'] = ''
        if not latest.part_title:
            continue
        titles = card['part_titles']
        if len(titles) > 1:
            card['arc'] = _arc_label(latest.part_title, titles, latest.title)
        parts = len(titles) + (1 if card['has_legacy_rows'] else 0)
        name = latest.part_poster_name
        if parts > 1 and name and os.path.exists(os.path.join(posters_dir, name)):
            card['poster_name'] = name


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
    _apply_arcs(show_cards)
    for card in movie_cards:
        card['poster_name'] = card['latest'].poster_name

    # "Viendo" = le quedan episodios por delante del último que vi (los calcula el sync
    # con el catálogo de Simkl) y lo vi hace poco. Hacen falta las dos condiciones: sin
    # la ventana, el listón resucitaría en cuanto Simkl añada los episodios de una
    # temporada anunciada; sin los pendientes, lo llevaría todo lo recién terminado.
    pending_works = SimklSyncState.load().pending_tmdb_ids
    watching_cutoff = timezone.now() - timedelta(days=WATCHING_WINDOW_DAYS)
    for card in show_cards:
        card['is_watching'] = (
            card['latest'].tmdb_id in pending_works
            and card['latest'].watched_at >= watching_cutoff
        )

    # Aviso de pendiente por calificar: es una tarea del dueño del historial, así
    # que solo se calcula con la sesión iniciada. Lo que aún se está viendo queda
    # fuera: la nota se pone al terminar, y marcarlo antes sería pedir algo que
    # todavía no toca.
    if request.user.is_authenticated:
        for card in show_cards + movie_cards:
            card['needs_rating'] = not card['latest'].user_rating and not card.get('is_watching')

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
                'poster_url': f"{settings.MEDIA_URL}Posters/{card['poster_name']}",
                'arc': card.get('arc', ''),
                'detail_url': latest.detail_url or '#',
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
                'needs_rating': card.get('needs_rating', False),
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
    """Nota 1-10 (misma escala en Trakt y Simkl) -> estrellas del sitio, ej. 7 -> ★★★½."""
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
    work_ratings = {}  # una obra (tipo, tmdb_id) -> mi nota
    release_years = {}  # una obra (tipo, tmdb_id) -> año de estreno

    for item in WatchedItem.objects.all():
        work_key = (item.media_type == 'episode', item.tmdb_id)
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
            shows_by_year[local_dt.year].add(item.tmdb_id)
        else:
            movies_by_year[local_dt.year].add(item.tmdb_id)

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

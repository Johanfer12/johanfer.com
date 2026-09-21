from django.shortcuts import render, redirect
from django.core.paginator import Paginator
from django.http import JsonResponse
from django.http import HttpResponse
from django.contrib.auth.decorators import user_passes_test
from django.views.decorators.http import require_GET
from .models import Book
from .models import VisitLog
from .models import OwnerSignature
from .middleware import get_client_ip
from .visit_stats import badge_count, invalidate_badge, mark_seen
from django.db.models import Count, Sum
from django.db.models import F, Q
from django.urls import reverse
from django.utils import timezone as dj_timezone
from django.utils.safestring import mark_safe
from django.templatetags.static import static
from django.conf import settings
from Bookshelf.html_sanitizer import sanitize_html
from home_page.templatetags.sanitizers import rating_stars
import hashlib
import json
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode, urlparse

SESSION_VISITOR_KEY = 'visit_visitor_id'

# PWA: color de marca y estáticos que el service worker guarda al instalarse.
PWA_THEME_COLOR = '#070715'
# Además de los iconos, se precarga TODO lo que pinta la pantalla de arranque
# (`start_url` es `/`, la portada). Antes solo estaban los iconos, así que el
# primer lanzamiento tras instalar bajaba las hojas, la fuente y los cuatro
# iconos desde la Pi, con el TTFB que eso supone: la caja se pintaba, luego
# entraba la tipografía y recomponía el texto, y luego aparecían los iconos.
# Ya en caché, la misma portada sirve esos ficheros en menos de 20 ms.
#
# Son ~55 KB sobre los ~102 KB de PNG que ya había. OJO: la versión de la caché
# sale del hash de esta lista, así que ahora un cambio en base.css o en home.css
# rota la caché entera y se vuelve a bajar todo una vez. Es el precio de que la
# lista no pueda quedarse con URLs viejas.
PWA_PRECACHE_STATIC = (
    'favicon.ico',
    'favicon.svg',
    'Img/pwa-icon-192.png',
    'Img/pwa-icon-512.png',
    'Img/pwa-icon-maskable-512.png',
    'Img/apple-touch-icon.png',
    # Comunes a las dieciséis páginas.
    'fonts/ubuntu.woff2',
    'fonts/ubuntu-medium.woff2',
    'css/tokens.css',
    'css/base.css',
    # La portada, que es la pantalla de arranque de la app.
    'css/home.css',
    'js/pwa.js',
    'js/gyro_parallax.js',
    'js/background_motion.js',
    'Img/library-icon.svg',
    'Img/spotify-icon.svg',
    'Img/watch-icon.svg',
    'Img/news-icon.svg',
)


def _iso2_to_flag(iso2):
    if not iso2 or len(iso2) != 2 or not iso2.isalpha():
        return ''
    base = 127397
    return chr(ord(iso2[0].upper()) + base) + chr(ord(iso2[1].upper()) + base)


def _extract_iso2_from_country_text(country):
    if not country:
        return ''
    value = country.strip()
    if len(value) == 2 and value.isalpha():
        return value.upper()
    parts = value.replace('-', ' ').split()
    if parts and len(parts[0]) == 2 and parts[0].isalpha():
        return parts[0].upper()
    return ''


def home(request):
    return render(request, 'home_page.html')

# Órdenes disponibles del bookshelf; los libros en curso siempre van primero
BOOK_ORDERS = {
    'fecha_desc': ('-is_reading', F('date_read').desc(nulls_last=True), '-id'),
    'fecha_asc': ('-is_reading', F('date_read').asc(nulls_last=True), 'id'),
    'nota_desc': ('-is_reading', '-my_rating', '-id'),
    'nota_asc': ('-is_reading', 'my_rating', '-id'),
}


def bookshelf(request):
    query = (request.GET.get('q') or '').strip()
    orden = request.GET.get('orden', 'fecha_desc')
    if orden not in BOOK_ORDERS:
        orden = 'fecha_desc'
    books = Book.objects.all().order_by(*BOOK_ORDERS[orden])
    if query:
        book_filter = Q(title__icontains=query) | Q(author__icontains=query)
        if query.isdigit():
            book_filter |= Q(date_read__year=int(query))
        books = books.filter(book_filter)

    # Set up pagination
    paginator = Paginator(books, 20)  # 20 libros por vista
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)
    total_books = paginator.count  # Total de libros (reutiliza el count del paginador)

    # Truncar el título de los libros que tienen ':' (solo los de la página visible)
    for book in page_obj:
        if ':' in book.title:
            book.title = book.title.split(':', 1)[0]

    if request.headers.get('x-requested-with') == 'XMLHttpRequest':
        # Si la petición es AJAX, devolver los datos en formato JSON
        book_data = []
        for book in page_obj:
            book_data.append({
                'title': book.title,
                'author': book.author,
                'my_rating_html': rating_stars(book.my_rating, 5),
                'public_rating_html': rating_stars(book.public_rating, 5),
                'date_read': book.date_read.strftime('%Y-%m-%d') if book.date_read else None,
                'is_reading': book.is_reading,
                'book_link': book.goodreads_url,
                'cover_image': f"{settings.MEDIA_URL}Covers/{book.id}.webp",
                'id': book.id,
                'description': sanitize_html(book.description),
                'genres': book.genres or '',
                'num_pages': book.num_pages,
                'published_year': book.published_year,
            })
        return JsonResponse({
            'books': book_data,
            'has_next': page_obj.has_next(),
            'query': query,
            'total_books': total_books,
        })
    else:
        # Para peticiones normales, renderizar la plantilla
        return render(request, 'bookshelf.html', {
            'page_obj': page_obj,
            'total_books': total_books,
            'current_query': query,
        })

def about(request):
    # Guardar la página de origen para decidir el botón de retorno en About
    referer = request.META.get('HTTP_REFERER', '')
    if 'bookshelf' in referer:
        request.session['about_source'] = 'bookshelf'
    elif 'spotify' in referer:
        request.session['about_source'] = 'spotify'
    elif 'noticias' in referer:
        request.session['about_source'] = 'news'
    
    return render(request, 'about.html')

def stats(request):
    # Los libros en curso no tienen fecha: fuera de las estadísticas
    books = Book.objects.filter(date_read__isnull=False)

    # Libros leídos por año
    books_per_year = books.values('date_read__year').annotate(total=Count('id')).order_by('date_read__year')
    books_per_year_labels = [entry['date_read__year'] for entry in books_per_year]
    books_per_year_values = [entry['total'] for entry in books_per_year]

    # Cantidad de estrellas (una sola query agregada en vez de una por rating)
    stars_labels = ['1 Estrella', '2 Estrellas', '3 Estrellas', '4 Estrellas', '5 Estrellas']
    rating_counts = {
        entry['my_rating']: entry['total']
        for entry in books.values('my_rating').annotate(total=Count('id'))
    }
    stars_values = [rating_counts.get(i, 0) for i in range(1, 6)]

    # Paginas leidas por año, usando el dato que entrega el RSS de Goodreads.
    pages_per_year = (
        books.exclude(num_pages__isnull=True)
        .values('date_read__year')
        .annotate(total=Sum('num_pages'))
        .order_by('date_read__year')
    )
    pages_per_year_labels = [entry['date_read__year'] for entry in pages_per_year]
    pages_per_year_values = [entry['total'] for entry in pages_per_year]

    context = {
        'books_per_year_labels': json.dumps(books_per_year_labels),
        'books_per_year_values': json.dumps(books_per_year_values),
        'stars_labels': json.dumps(stars_labels),
        'stars_values': json.dumps(stars_values),
        'pages_per_year_labels': json.dumps(pages_per_year_labels),
        'pages_per_year_values': json.dumps(pages_per_year_values)
    }

    return render(request, 'stats.html', context)

def custom_404_view(request, exception):
    return render(request, '404.html', status=404)


def _get_visitor_id(request):
    return (request.session.get(SESSION_VISITOR_KEY) or '').strip()


def _parse_visit_date(value):
    if not value:
        return None
    try:
        dt = datetime.strptime(value, '%Y-%m-%d')
    except ValueError:
        return None
    return dj_timezone.make_aware(dt, dj_timezone.get_current_timezone())


def _get_visits_filters(request):
    def _read_value(key):
        get_value = (request.GET.get(key) or '').strip()
        if get_value:
            return get_value
        if request.method == 'POST':
            return (request.POST.get(key) or '').strip()
        return ''

    return {
        'ip': _read_value('ip'),
        'country': _read_value('country'),
        'path': _read_value('path'),
        'ua': _read_value('ua'),
        'from': _read_value('from'),
        'to': _read_value('to'),
    }


def _apply_visits_filters(filters):
    visit_qs = VisitLog.objects.all()
    if filters['ip']:
        visit_qs = visit_qs.filter(ip_address__icontains=filters['ip'])
    if filters['country']:
        visit_qs = visit_qs.filter(country__icontains=filters['country'])
    if filters['path']:
        visit_qs = visit_qs.filter(path__icontains=filters['path'])
    if filters['ua']:
        visit_qs = visit_qs.filter(user_agent__icontains=filters['ua'])

    date_from = _parse_visit_date(filters['from'])
    date_to = _parse_visit_date(filters['to'])
    if date_from:
        visit_qs = visit_qs.filter(visited_at__gte=date_from)
    if date_to:
        visit_qs = visit_qs.filter(visited_at__lt=date_to + timedelta(days=1))

    return visit_qs


def _owner_signatures():
    """IPs y visitor_id que han pasado por el login; es decir, míos."""
    ips = set()
    visitor_ids = set()
    for ip, visitor_id in OwnerSignature.objects.values_list('ip_address', 'visitor_id'):
        if ip:
            ips.add(ip)
        if visitor_id:
            visitor_ids.add(visitor_id)
    return ips, visitor_ids


def _owner_marks(request):
    """Señas que identifican mis visitas: las del login más la sesión de ahora."""
    owner_ips, owner_visitor_ids = _owner_signatures()
    current_ip = get_client_ip(request)
    current_visitor_id = _get_visitor_id(request)
    if current_ip:
        owner_ips.add(current_ip)
    if current_visitor_id:
        owner_visitor_ids.add(current_visitor_id)
    return owner_ips, owner_visitor_ids


def _mine_filter(owner_ips, owner_visitor_ids):
    mine = Q(pk__in=[])  # Neutro: sin firmas, ninguna visita es mía.
    if owner_ips:
        mine |= Q(ip_address__in=owner_ips)
    if owner_visitor_ids:
        mine |= Q(visitor_id__in=owner_visitor_ids)
    return mine


def _group_key(country_code, country):
    """Clave estable de un país, y traducible a un filtro SQL.

    Se agrupa por country_code cuando lo hay, para que 'US' y 'United States'
    no salgan como dos países; las filas sin código caen en su nombre.
    """
    iso2 = (country_code or '').strip().upper()
    if iso2:
        return f'cc:{iso2}'
    return f'name:{(country or "").strip().casefold()}'


def _group_queryset(visit_qs, group_key):
    """Reduce un queryset al país de esa clave. None si la clave no vale."""
    if group_key.startswith('cc:'):
        iso2 = group_key[3:]
        if not (len(iso2) == 2 and iso2.isalpha()):
            return None
        return visit_qs.filter(country_code__iexact=iso2)
    if group_key.startswith('name:'):
        return visit_qs.filter(country_code='', country__iexact=group_key[5:])
    return None


def _country_groups(visit_qs, mine):
    """Resumen por país: una consulta agregada, sin traerse las visitas.

    Con miles de filas, pintar todas las tablas de golpe costaba segundos de
    plantilla y megabytes de HTML. Las filas se piden por país (visits_rows).
    """
    rows = (
        visit_qs
        .values('country_code', 'country')
        .annotate(total=Count('id'), mine_total=Count('id', filter=mine))
    )

    groups = {}
    for row in rows:
        iso2 = (row['country_code'] or '').strip().upper()
        if not iso2:
            iso2 = _extract_iso2_from_country_text(row['country'])

        country_name = (row['country'] or '').strip()
        country_label = country_name or iso2 or 'País desconocido'
        key = _group_key(row['country_code'], row['country'])

        group = groups.get(key)
        if group is None:
            group = groups[key] = {
                'key': key,
                'country': country_label,
                'country_flag': _iso2_to_flag(iso2),
                'country_iso2': iso2.lower() if iso2 else '',
                'is_local': country_label.casefold() == 'local',
                'is_unknown': country_label == 'País desconocido',
                'visit_count': 0,
                'self_count': 0,
            }
        if group['country'] in (iso2, 'País desconocido') and country_name:
            group['country'] = country_name
        group['visit_count'] += row['total']
        group['self_count'] += row['mine_total']

    grouped_visits = list(groups.values())
    grouped_visits.sort(key=lambda group: (
        not (
            group['country_iso2'] == 'co'
            or group['country'].casefold() == 'colombia'
        ),
        -group['visit_count'],
    ))
    return grouped_visits


VISITS_ROWS_PAGE_SIZE = 300

visits_access_required = user_passes_test(
    lambda u: u.is_superuser or (
        settings.DEBUG and settings.VISITS_ALLOW_LOCAL_WITHOUT_LOGIN
    ),
    login_url='/noticias/login/',
)


def _is_ajax(request):
    return request.headers.get('x-requested-with') == 'XMLHttpRequest'


def _delete_visits(request, filtered_qs):
    """Aplica la acción de borrado del POST. Devuelve cuántas visitas se fueron."""
    delete_one = (request.POST.get('delete_one') or '').strip()
    action = (request.POST.get('action') or '').strip()
    deleted = 0

    if delete_one.isdigit():
        deleted, _ = filtered_qs.filter(id=int(delete_one)).delete()
    elif action == 'delete_selected':
        selected_ids = [
            visit_id
            for value in request.POST.getlist('selected_visits')
            for visit_id in value.split(',')
            if visit_id.isdigit()
        ]
        if selected_ids:
            deleted, _ = filtered_qs.filter(id__in=selected_ids).delete()
    elif action == 'delete_group':
        # Borrado por país: no se mandan ids, así no depende de cuántas filas
        # se hayan cargado en el modal ni viaja una lista de miles de números.
        group_qs = _group_queryset(filtered_qs, (request.POST.get('group') or '').strip())
        if group_qs is not None:
            if request.POST.get('self_only') == '1':
                owner_ips, owner_visitor_ids = _owner_marks(request)
                group_qs = group_qs.filter(_mine_filter(owner_ips, owner_visitor_ids))
            deleted, _ = group_qs.delete()
    elif action == 'delete_all_filtered':
        deleted, _ = filtered_qs.delete()

    invalidate_badge()
    return deleted


@visits_access_required
def visits(request):
    # Guardar la página de origen para decidir el botón de retorno (igual que en About)
    referer_path = urlparse(request.META.get('HTTP_REFERER', '')).path
    if referer_path and referer_path != request.path:
        if referer_path.startswith('/bookshelf'):
            request.session['visits_source'] = 'bookshelf'
        elif referer_path.startswith('/viendo'):
            request.session['visits_source'] = 'viendo'
        elif referer_path.startswith('/spotify'):
            request.session['visits_source'] = 'spotify'
        elif referer_path.startswith('/noticias'):
            request.session['visits_source'] = 'news'
        elif referer_path == '/':
            request.session['visits_source'] = 'home'

    filters = _get_visits_filters(request)
    filtered_qs = _apply_visits_filters(filters)

    if request.method == 'POST':
        deleted = _delete_visits(request, filtered_qs)

        if _is_ajax(request):
            # Sin recargar: el modal abierto se queda donde estaba.
            group_key = (request.POST.get('group') or '').strip()
            group_qs = _group_queryset(filtered_qs, group_key) if group_key else None
            owner_ips, owner_visitor_ids = _owner_marks(request)
            payload = {
                'deleted': deleted,
                'total_visits': filtered_qs.count(),
            }
            if group_qs is not None:
                mine = _mine_filter(owner_ips, owner_visitor_ids)
                payload['group_count'] = group_qs.count()
                payload['group_self_count'] = group_qs.filter(mine).count()
            return JsonResponse(payload)

        query_string = urlencode({k: v for k, v in filters.items() if v})
        if query_string:
            return redirect(f"{request.path}?{query_string}")
        return redirect(request.path)

    owner_ips, owner_visitor_ids = _owner_marks(request)
    mine = _mine_filter(owner_ips, owner_visitor_ids)
    visit_groups = _country_groups(filtered_qs, mine)

    # Entrar aquí es haberlas mirado: la insignia de la cabecera se apaga.
    # Solo lo que se está viendo; con un filtro activo, el resto sigue pendiente.
    mark_seen(filtered_qs)

    return render(request, 'visits.html', {
        'visit_groups': visit_groups,
        'total_visits': sum(group['visit_count'] for group in visit_groups),
        'filters': filters,
        'rows_page_size': VISITS_ROWS_PAGE_SIZE,
    })


@require_GET
@visits_access_required
def visits_badge_state(request):
    """Cuántas visitas pendientes hay ahora mismo, para la insignia.

    La cabecera la pinta al renderizar la página, así que sin esto el número se
    queda congelado hasta la siguiente recarga. `badge_count` va cacheado y la
    caché se invalida al registrar una visita, de modo que el sondeo normal no
    llega ni a tocar la base.
    """
    return JsonResponse({'status': 'success', 'badge': badge_count()})


@visits_access_required
def visits_rows(request):
    """Filas de un país, ya en JSON y por tandas.

    La página solo pinta las tarjetas; la tabla de un país se pide al abrir su
    modal, que es cuando se mira de verdad.
    """
    filters = _get_visits_filters(request)
    group_qs = _group_queryset(_apply_visits_filters(filters), (request.GET.get('group') or '').strip())
    if group_qs is None:
        return JsonResponse({'error': 'grupo desconocido'}, status=400)

    try:
        offset = max(int(request.GET.get('offset') or 0), 0)
    except ValueError:
        offset = 0

    owner_ips, owner_visitor_ids = _owner_marks(request)
    page = list(
        group_qs.order_by('-visited_at', '-id')
        .values('id', 'visited_at', 'ip_address', 'visitor_id', 'path', 'user_agent')
        [offset:offset + VISITS_ROWS_PAGE_SIZE + 1]
    )
    has_more = len(page) > VISITS_ROWS_PAGE_SIZE
    page = page[:VISITS_ROWS_PAGE_SIZE]

    rows = [{
        'id': row['id'],
        'visited_at': dj_timezone.localtime(row['visited_at']).strftime('%Y-%m-%d %H:%M:%S'),
        'ip_address': row['ip_address'],
        'path': row['path'],
        'user_agent': row['user_agent'] or '-',
        'is_self': row['ip_address'] in owner_ips or bool(row['visitor_id'] and row['visitor_id'] in owner_visitor_ids),
    } for row in page]

    return JsonResponse({'rows': rows, 'has_more': has_more, 'offset': offset + len(rows)})


def manifest_webmanifest(request):
    """Manifiesto de la PWA. Se genera aquí y no como plantilla para no depender
    del escapado HTML de Django dentro de un JSON."""
    icon = lambda name, size: {
        'src': static(f'Img/{name}'),
        'sizes': f'{size}x{size}',
        'type': 'image/png',
    }
    shortcut_icon = [icon('pwa-icon-192.png', 192)]

    manifest = {
        'id': '/',
        'name': settings.SITE_NAME,
        'short_name': settings.SITE_SHORT_NAME,
        'description': settings.SITE_META_DESCRIPTION,
        'lang': 'es',
        'dir': 'ltr',
        'start_url': '/',
        'scope': '/',
        'display': 'standalone',
        'display_override': ['standalone', 'minimal-ui'],
        'background_color': PWA_THEME_COLOR,
        'theme_color': PWA_THEME_COLOR,
        'orientation': 'any',
        'icons': [
            dict(icon('pwa-icon-192.png', 192), purpose='any'),
            dict(icon('pwa-icon-512.png', 512), purpose='any'),
            dict(icon('pwa-icon-maskable-512.png', 512), purpose='maskable'),
        ],
        'shortcuts': [
            {'name': 'Noticias', 'url': '/noticias/', 'icons': shortcut_icon},
            {'name': 'Libros', 'url': reverse('home_page:bookshelf'), 'icons': shortcut_icon},
            {'name': 'TV', 'url': '/viendo/', 'icons': shortcut_icon},
        ],
    }
    response = JsonResponse(manifest, json_dumps_params={'ensure_ascii': False, 'indent': 2})
    response['Content-Type'] = 'application/manifest+json'
    return response


def service_worker(request):
    """El service worker se sirve desde la raíz para que su ámbito sea todo el
    sitio; bajo /static/ solo controlaría /static/."""
    precache = [static(path) for path in PWA_PRECACHE_STATIC]
    offline_url = reverse('home_page:offline')
    # La versión cuelga de las URLs cacheadas: al cambiar el hash de un estático
    # cambia el nombre de la caché y la anterior se descarta sola.
    version = hashlib.md5('|'.join(precache + [offline_url]).encode()).hexdigest()[:12]

    response = render(request, 'sw.js', {
        'sw_version': version,
        'offline_url': offline_url,
        'home_url': reverse('home_page:index'),
        'precache_urls': mark_safe(json.dumps(precache)),
    }, content_type='application/javascript; charset=utf-8')
    response['Service-Worker-Allowed'] = '/'
    # `no-cache` a secas no basta: Cloudflare cachea .js por extensión y
    # reescribía esto a max-age=172800, así que un service worker nuevo podía
    # quedarse dos días atrapado en el edge.
    response['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    return response


def offline(request):
    return render(request, 'offline.html')


def robots_txt(request):
    lines = [
        "User-agent: *",
        "Allow: /",
        "Disallow: /j_admin/",
        "Disallow: /noticias/",
        "",
        f"Sitemap: {request.scheme}://{request.get_host()}{reverse('home_page:sitemap_xml')}",
    ]
    return HttpResponse("\n".join(lines), content_type="text/plain; charset=utf-8")


def sitemap_xml(request):
    base = f"{request.scheme}://{request.get_host()}"
    now = datetime.now(timezone.utc).date().isoformat()
    urls = [
        reverse('home_page:index'),
        reverse('home_page:bookshelf'),
        reverse('home_page:stats'),
        reverse('home_page:about'),
        reverse('spotify:dashboard'),
        reverse('spotify:stats'),
        reverse('spotify:deleted'),
        reverse('watching:index'),
        reverse('watching:stats'),
    ]

    body = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">',
    ]
    for path in urls:
        body.extend([
            "  <url>",
            f"    <loc>{base}{path}</loc>",
            f"    <lastmod>{now}</lastmod>",
            "  </url>",
        ])
    body.append("</urlset>")
    return HttpResponse("\n".join(body), content_type="application/xml; charset=utf-8")

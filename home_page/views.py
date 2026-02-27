from django.shortcuts import render, redirect
from django.core.paginator import Paginator
from django.http import JsonResponse
from django.http import HttpResponse
from django.contrib.auth.decorators import user_passes_test
from .models import Book
from .models import VisitLog
from django.db.models import Count
from django.db.models import Q
from django.urls import reverse
from django.utils import timezone as dj_timezone
import json
from datetime import datetime, timezone
from urllib.parse import urlencode

SESSION_VISITOR_KEY = 'visit_visitor_id'


COUNTRY_TO_ISO2 = {
    'argentina': 'AR',
    'bolivia': 'BO',
    'brazil': 'BR',
    'brasil': 'BR',
    'canada': 'CA',
    'chile': 'CL',
    'colombia': 'CO',
    'costa rica': 'CR',
    'dominican republic': 'DO',
    'ecuador': 'EC',
    'el salvador': 'SV',
    'spain': 'ES',
    'españa': 'ES',
    'guatemala': 'GT',
    'honduras': 'HN',
    'mexico': 'MX',
    'méxico': 'MX',
    'nicaragua': 'NI',
    'panama': 'PA',
    'panamá': 'PA',
    'paraguay': 'PY',
    'peru': 'PE',
    'perú': 'PE',
    'puerto rico': 'PR',
    'united kingdom': 'GB',
    'united states': 'US',
    'uruguay': 'UY',
    'venezuela': 'VE',
}


def _iso2_to_flag(iso2):
    if not iso2 or len(iso2) != 2 or not iso2.isalpha():
        return ''
    base = 127397
    return chr(ord(iso2[0].upper()) + base) + chr(ord(iso2[1].upper()) + base)


def _country_to_flag(country):
    if not country:
        return ''
    value = country.strip()
    iso2 = value.upper() if len(value) == 2 and value.isalpha() else COUNTRY_TO_ISO2.get(value.lower(), '')
    return _iso2_to_flag(iso2)


def home(request):
    return render(request, 'home_page.html')

def bookshelf(request):
    query = (request.GET.get('q') or '').strip()
    books = Book.objects.all().order_by('-id')
    if query:
        books = books.filter(Q(title__icontains=query) | Q(author__icontains=query))

    total_books = books.count()  # Total de libros en la base de datos
    
    # Truncar el título de los libros que tienen ':' en el título
    for book in books:
        if ':' in book.title:
            book.title = book.title.split(':', 1)[0]
    
    # Set up pagination
    paginator = Paginator(books, 20)  # 20 libros por vista
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)
    
    if request.headers.get('x-requested-with') == 'XMLHttpRequest':
        # Si la petición es AJAX, devolver los datos en formato JSON
        book_data = []
        for book in page_obj:
            book_data.append({
                'title': book.title,
                'author': book.author,
                'my_rating': book.my_rating,
                'public_rating': book.public_rating,
                'date_read': book.date_read.strftime('%Y-%m-%d'),
                'book_link': book.book_link,
                'cover_image': f"/static/Img/Covers/{book.id}.webp",
                'id': book.id,
                'description': book.description,
                'genres': book.genres or ''
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
    # Guardar la página de origen si viene de bookshelf o spotify
    referer = request.META.get('HTTP_REFERER', '')
    if 'bookshelf' in referer:
        request.session['about_source'] = 'bookshelf'
    elif 'spotify' in referer:
        request.session['about_source'] = 'spotify'
    
    return render(request, 'about.html')

def stats(request):
    books = Book.objects.all()

    # Libros leídos por año
    books_per_year = books.values('date_read__year').annotate(total=Count('id')).order_by('date_read__year')
    books_per_year_labels = [entry['date_read__year'] for entry in books_per_year]
    books_per_year_values = [entry['total'] for entry in books_per_year]

    # Cantidad de estrellas
    stars_labels = ['1 Estrella', '2 Estrellas', '3 Estrellas', '4 Estrellas', '5 Estrellas']
    stars_values = [books.filter(my_rating=i).count() for i in range(1, 6)]

    # Top generos mas leidos (maximo 5)
    genre_counter = {}
    for raw_genres in books.values_list('genres', flat=True):
        if not raw_genres:
            continue
        for part in raw_genres.split(','):
            genre = part.strip()
            if not genre:
                continue
            genre_counter[genre] = genre_counter.get(genre, 0) + 1

    top_genres = sorted(genre_counter.items(), key=lambda x: x[1], reverse=True)[:5]
    top_genres_labels = [entry[0] for entry in top_genres]
    top_genres_values = [entry[1] for entry in top_genres]

    context = {
        'books_per_year_labels': json.dumps(books_per_year_labels),
        'books_per_year_values': json.dumps(books_per_year_values),
        'stars_labels': json.dumps(stars_labels),
        'stars_values': json.dumps(stars_values),
        'top_genres_labels': json.dumps(top_genres_labels),
        'top_genres_values': json.dumps(top_genres_values)
    }

    return render(request, 'stats.html', context)

def custom_404_view(request, exception):
    return render(request, '404.html', status=404)


def _get_client_ip(request):
    forwarded = request.headers.get('X-Forwarded-For')
    if forwarded:
        return forwarded.split(',')[0].strip()
    return (request.META.get('REMOTE_ADDR') or '').strip()


def _get_visitor_id(request):
    return (request.session.get(SESSION_VISITOR_KEY) or '').strip()


def _parse_datetime_local(value):
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value)
    except ValueError:
        return None
    if dj_timezone.is_naive(dt):
        dt = dj_timezone.make_aware(dt, dj_timezone.get_current_timezone())
    return dt


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

    date_from = _parse_datetime_local(filters['from'])
    date_to = _parse_datetime_local(filters['to'])
    if date_from:
        visit_qs = visit_qs.filter(visited_at__gte=date_from)
    if date_to:
        visit_qs = visit_qs.filter(visited_at__lte=date_to)

    return visit_qs


@user_passes_test(lambda u: u.is_superuser, login_url='/noticias/login/')
def visits(request):
    filters = _get_visits_filters(request)
    filtered_qs = _apply_visits_filters(filters)

    if request.method == 'POST':
        delete_one = (request.POST.get('delete_one') or '').strip()
        action = (request.POST.get('action') or '').strip()

        if delete_one.isdigit():
            filtered_qs.filter(id=int(delete_one)).delete()
        elif action == 'delete_selected':
            selected_ids = [v for v in request.POST.getlist('selected_visits') if v.isdigit()]
            if selected_ids:
                filtered_qs.filter(id__in=selected_ids).delete()
        elif action == 'delete_all_filtered':
            filtered_qs.delete()

        query_string = urlencode({k: v for k, v in filters.items() if v})
        if query_string:
            return redirect(f"{request.path}?{query_string}")
        return redirect(request.path)

    visit_qs = filtered_qs.order_by('-visited_at')
    paginator = Paginator(visit_qs, 100)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)
    current_ip = _get_client_ip(request)
    current_visitor_id = _get_visitor_id(request)

    for visit in page_obj.object_list:
        visit.country_flag = _country_to_flag(visit.country)
        visit.is_self = (
            bool(current_visitor_id and visit.visitor_id == current_visitor_id)
            or bool(current_ip and visit.ip_address == current_ip)
        )

    query_params = request.GET.copy()
    if 'page' in query_params:
        del query_params['page']

    return render(request, 'visitas.html', {
        'page_obj': page_obj,
        'total_visits': visit_qs.count(),
        'current_ip': current_ip,
        'current_visitor_id': current_visitor_id,
        'filter_query': query_params.urlencode(),
        'filters': filters,
    })


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

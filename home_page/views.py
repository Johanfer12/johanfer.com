from django.shortcuts import render, redirect
from django.core.paginator import Paginator
from django.http import JsonResponse
from django.http import HttpResponse
from django.contrib.auth.decorators import user_passes_test
from .models import Book
from .models import VisitLog
from .middleware import get_client_ip
from django.db.models import Count, Sum
from django.db.models import Q
from django.urls import reverse
from django.utils import timezone as dj_timezone
from django.conf import settings
from Bookshelf.html_sanitizer import sanitize_html
import json
from datetime import datetime, timezone
from urllib.parse import urlencode

SESSION_VISITOR_KEY = 'visit_visitor_id'


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

def bookshelf(request):
    query = (request.GET.get('q') or '').strip()
    # Los libros en curso van primero, luego los leídos del más reciente al más viejo
    books = Book.objects.all().order_by('-is_reading', '-id')
    if query:
        books = books.filter(Q(title__icontains=query) | Q(author__icontains=query))

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
                'my_rating': book.my_rating,
                'public_rating': book.public_rating,
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
    current_ip = get_client_ip(request)
    current_visitor_id = _get_visitor_id(request)

    for visit in page_obj.object_list:
        iso2 = (visit.country_code or '').upper()
        if not iso2:
            iso2 = _extract_iso2_from_country_text(visit.country)
        visit.country_flag = _iso2_to_flag(iso2)
        visit.country_iso2 = iso2.lower() if iso2 else ''
        visit.is_self = (
            bool(current_visitor_id and visit.visitor_id == current_visitor_id)
            or bool(current_ip and visit.ip_address == current_ip)
        )

    query_params = request.GET.copy()
    if 'page' in query_params:
        del query_params['page']

    return render(request, 'visits.html', {
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

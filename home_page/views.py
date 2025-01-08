from django.shortcuts import render
from django.core.paginator import Paginator
from django.http import JsonResponse
from .models import Book
from django.db.models import Count
import json

def home(request):
    return render(request, 'home_page.html')

def bookshelf(request):
    books = Book.objects.all().order_by('-id')
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
                'description': book.description
            })
        return JsonResponse({'books': book_data, 'has_next': page_obj.has_next()})
    else:
        # Para peticiones normales, renderizar la plantilla
        return render(request, 'bookshelf.html', {'page_obj': page_obj, 'total_books': total_books})

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

    # Top autores más leídos
    top_authors = books.values('author').annotate(total=Count('id')).order_by('-total')[:5]
    top_authors_labels = [entry['author'] for entry in top_authors]
    top_authors_values = [entry['total'] for entry in top_authors]

    context = {
        'books_per_year_labels': json.dumps(books_per_year_labels),
        'books_per_year_values': json.dumps(books_per_year_values),
        'stars_labels': json.dumps(stars_labels),
        'stars_values': json.dumps(stars_values),
        'top_authors_labels': json.dumps(top_authors_labels),
        'top_authors_values': json.dumps(top_authors_values)
    }

    return render(request, 'stats.html', context)

def custom_404_view(request, exception):
    return render(request, '404.html', status=404)
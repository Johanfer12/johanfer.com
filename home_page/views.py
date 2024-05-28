from django.shortcuts import render
from .models import Book
from django.db.models import Count
import json

def book_list(request):
    # Ordenar los libros por fecha de lectura en orden descendente    
    books = Book.objects.all().order_by('-id')

    # Truncar el título de cada libro si contiene dos puntos
    for book in books:
        if ':' in book.title:
            book.title = book.title.split(':', 1)[0]
                
    return render(request, 'home_page.html', {'books': books})

def about(request):
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
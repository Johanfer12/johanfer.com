from django.shortcuts import render
from .models import Book, scrap_books

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
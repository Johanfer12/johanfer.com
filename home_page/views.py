from django.shortcuts import render
from .models import Book, scrap_books

def book_list(request):
    # Ordenar los libros por fecha de lectura en orden descendente    
    books = Book.objects.all().order_by('-id')
    #scrap_books()
    return render(request, 'home_page.html', {'books': books})

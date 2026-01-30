from django.core.management.base import BaseCommand
from home_page.models import Book
from home_page.utils import extract_goodreads_id
from collections import defaultdict

class Command(BaseCommand):
    help = 'Elimina libros duplicados basándose en el ID de Goodreads, manteniendo el más antiguo.'

    def handle(self, *args, **options):
        books = Book.objects.all().order_by('id')
        books_by_gid = defaultdict(list)
        
        self.stdout.write("Buscando duplicados...")
        
        # Agrupar libros por Goodreads ID
        for book in books:
            gid = extract_goodreads_id(book.book_link)
            if gid:
                books_by_gid[gid].append(book)
        
        duplicates_found = 0
        deleted_count = 0
        
        for gid, book_list in books_by_gid.items():
            if len(book_list) > 1:
                duplicates_found += 1
                # El primero de la lista es el más antiguo (menor ID) porque ordenamos por 'id'
                original = book_list[0]
                duplicates = book_list[1:]
                
                self.stdout.write(self.style.WARNING(f"Duplicado encontrado para ID {gid} ('{original.title}'):"))
                
                for dup in duplicates:
                    self.stdout.write(f" - Eliminando duplicado (ID: {dup.id}, Título: '{dup.title}', URL: {dup.book_link})")
                    dup.delete()
                    deleted_count += 1
                    
        if duplicates_found == 0:
            self.stdout.write(self.style.SUCCESS("No se encontraron duplicados."))
        else:
            self.stdout.write(self.style.SUCCESS(f"Limpieza completada. Se eliminaron {deleted_count} libros duplicados."))

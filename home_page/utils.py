from bs4 import BeautifulSoup
import requests
import os
from datetime import datetime
from PIL import Image
import re
from django.utils import timezone
from .models import Book, DeletedBook

def modify_cover_url(cover_url):
    return re.sub(r'(_SX\d+_SY\d+_|_SY\d+_SX\d+_|_SX\d+_|_SY\d+_)', '_SY700_', cover_url)

def convert_to_webp(source_path, destination_path):
    try:
        with Image.open(source_path) as img:
            img.thumbnail((300, 450), Image.Resampling.LANCZOS)
            if img.mode in ("RGBA", "P"):
                img = img.convert("RGB")
            img.save(destination_path, 'WEBP')
    except Exception as e:
        print(f"Error al convertir la imagen: {e}")

def get_book_description(book_url, headers):
    try:
        full_url = f"https://www.goodreads.com{book_url}"
        response = requests.get(full_url, headers=headers)
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, 'html.parser')
            description_span = soup.find('span', class_='Formatted')
            if description_span:
                return str(description_span)
    except Exception as e:
        print(f"Error al obtener descripción: {e}")
    return None

def process_rating(rating_element):
    if rating_element:
        rating_title = rating_element.find('span', class_='staticStars').get('title', '')
        if 'did not like it' in rating_title:
            return 1
        elif 'it was ok' in rating_title:
            return 2
        elif 'really liked it' in rating_title:
            return 4
        elif 'liked it' in rating_title:
            return 3
        elif 'it was amazing' in rating_title:
            return 5
    return 0

def process_date(date_read_str):
    try:
        if ',' in date_read_str:
            return datetime.strptime(date_read_str, '%b %d, %Y').date()
        return datetime.strptime(date_read_str + ' 01', '%b %Y %d').date()
    except:
        return None

def refresh_books_data():
    folder_path = "static/Img/Covers"
    if not os.path.exists(folder_path):
        os.makedirs(folder_path)

    base_url = "https://www.goodreads.com/review/list/27786474-johan-gonzalez?print=true&ref=nav_mybooks&shelf=read&utf8=%E2%9C%93"
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.3'
    }

    response = requests.get(base_url, headers=headers)

    if response.status_code == 200:
        soup = BeautifulSoup(response.text, 'html.parser')
        pagination_div = soup.find("div", id="reviewPagination")
        last_page_link = pagination_div.find_all("a")[-2]
        total_pages = int(last_page_link.text)

        # Calcular número total de libros en Goodreads
        reviews = soup.find_all('tr', class_='bookalike review')
        libros_por_pagina = len(reviews)
        total_libros_goodreads = (total_pages - 1) * libros_por_pagina
        ultima_pagina_reviews = BeautifulSoup(requests.get(f"{base_url}&page={total_pages}", headers=headers).text, 'html.parser')
        total_libros_goodreads += len(ultima_pagina_reviews.find_all('tr', class_='bookalike review'))

        # Comparar con libros en base de datos
        total_libros_db = Book.objects.count()

        if total_libros_db == total_libros_goodreads:
            print("No hay nuevos libros para actualizar")
            return

        # Obtener todos los book_links existentes
        current_books = set(Book.objects.values_list('book_link', flat=True))
        book_counter = 0  # Inicializar contador en 0 si empezamos de cero

        if total_libros_db == 0:
            # Si la DB está vacía, procesar todas las páginas desde la última a la primera
            page_range = range(total_pages, 0, -1)
        else:
            # Si ya hay libros, solo procesar la primera página
            page_range = range(1, 2)
            book_counter = total_libros_db  # Inicializar contador con total actual si ya hay libros

        for page_number in page_range:
            page_url = f"{base_url}&page={page_number}"
            response = requests.get(page_url, headers=headers)
            soup = BeautifulSoup(response.text, 'html.parser')
            reviews = soup.find_all('tr', class_='bookalike review')

            # Si estamos procesando desde el inicio, invertir el orden de los reviews
            if total_libros_db == 0:
                reviews = reviews[::-1]

            for review in reviews:
                book_link = review.find('td', class_='field title').find('a')['href']
                
                # Si el libro ya existe, saltamos al siguiente
                if book_link in current_books:
                    continue

                # Procesar datos del libro nuevo
                title = review.find('td', class_='field title').find('a').get_text(strip=True)
                author = review.find('td', class_='field author').find('a').get_text(strip=True)
                rating_element = review.find('td', class_='field rating')
                my_rating = process_rating(rating_element)
                public_rating = review.find('td', class_='field avg_rating').find('div', class_='value').get_text(strip=True)
                date_read_str = review.find('td', class_='field date_read').find('span', class_='date_read_value').get_text(strip=True)
                date_read = process_date(date_read_str)
                description = get_book_description(book_link, headers)

                # Procesar portada antes de crear el libro
                cover_link = None
                cover_info = review.find('td', class_='field cover')
                if cover_info:
                    cover_link = cover_info.find('img')['src']

                # Crear el libro con la URL de la portada
                nuevo_libro = Book.objects.create(
                    title=title,
                    author=author,
                    cover_link=cover_link,
                    my_rating=my_rating,
                    public_rating=public_rating,
                    date_read=date_read,
                    book_link=book_link,
                    description=description
                )

                # Procesar y guardar la imagen de la portada
                if cover_link and cover_link.endswith('.jpg'):
                    modified_cover_url = modify_cover_url(cover_link)
                    file_name = f"{nuevo_libro.id}.webp"
                    file_path = os.path.join(folder_path, file_name)
                    
                    if not os.path.exists(file_path):
                        temp_jpg_path = os.path.join(folder_path, f"temp_{nuevo_libro.id}.jpg")
                        try:
                            with open(temp_jpg_path, 'wb') as f:
                                response = requests.get(modified_cover_url)
                                f.write(response.content)
                            convert_to_webp(temp_jpg_path, file_path)
                            os.remove(temp_jpg_path)
                        except Exception as e:
                            print(f"Error al procesar imagen: {e}")

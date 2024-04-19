from django.db import models
from bs4 import BeautifulSoup
import requests
import os
import re
import sqlite3
from datetime import datetime

def modify_cover_url(cover_url):
    return re.sub(r'(_SX\d+_SY\d+_|_SY\d+_SX\d+_|_SX\d+_|_SY\d+_)', '_SY700_', cover_url)

def scrap_books():
    folder_path = "static/Img/Covers"
    if not os.path.exists(folder_path):
        os.makedirs(folder_path)

    # Crear una conexión a la base de datos
    conn = sqlite3.connect('database.db')    
    # Crear un cursor
    c = conn.cursor()
    # Crear la tabla si no existe
    c.execute('''CREATE TABLE IF NOT EXISTS books
                (id INTEGER PRIMARY KEY,
                title TEXT,
                author TEXT,
                cover_link TEXT,
                my_rating INTEGER,
                public_rating TEXT,
                date_read TEXT,
                book_link TEXT UNIQUE)''')

    base_url = "https://www.goodreads.com/review/list/27786474-johan-gonzalez?print=true&ref=nav_mybooks&shelf=read&utf8=%E2%9C%93"
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.3'
    }

    response = requests.get(base_url, headers=headers)

    if response.status_code == 200:
        soup = BeautifulSoup(response.text, 'html.parser')
        pagination_div = soup.find("div", id="reviewPagination")# Encontrar el último enlace de paginación para obtener el número total de páginas disponibles
        last_page_link = pagination_div.find_all("a")[-2]  # El penúltimo enlace es el último número de página
        total_pages = int(last_page_link.text)

        # Encontrar el número de libros en la última página
        last_page_url = f"{base_url}&page={total_pages}"
        last_page_response = requests.get(last_page_url, headers=headers)
        last_page_soup = BeautifulSoup(last_page_response.text, 'html.parser')
        last_page_reviews = last_page_soup.find_all('tr', class_='bookalike review')
        total_books = (total_pages - 1) * 20 + len(last_page_reviews)

        # Contar la cantidad de libros en la base de datos
        db_book_count = Book.objects.count()

        # Verificar si el número de libros en la página web ha cambiado
        if total_books != db_book_count:
            print("El número de libros en la página web ha cambiado. Actualizando la base de datos...")

            book_counter = 0

            for page_number in range(total_pages, 0, -1):
                page_url = f"{base_url}&page={page_number}"
                response = requests.get(page_url, headers=headers)
                soup = BeautifulSoup(response.text, 'html.parser')
                reviews = soup.find_all('tr', class_='bookalike review')

                for review in reversed(reviews):
                    book_counter += 1
                    
                    cover_info = review.find('td', class_='field cover')
                    if cover_info:
                        cover_link = cover_info.find('img')['src']
                        if cover_link.endswith('.jpg'):
                            modified_cover_url = modify_cover_url(cover_link)
                            file_name = f"{book_counter}.jpg"
                            if not os.path.exists(os.path.join(folder_path, file_name)):
                                with open(os.path.join(folder_path, file_name), 'wb') as f:
                                    response = requests.get(modified_cover_url)
                                    f.write(response.content)
                            else:
                                print(f"File {file_name} already exists in the destination folder.")
                    title_info = review.find('td', class_='field title')
                    if title_info:
                        title_element = title_info.find('a')
                        if title_element:
                            title = title_element.get_text(strip=True)
                        else:
                            title = "N/A"
                    else:
                        title = "N/A"
                        
                    author_info = review.find('td', class_='field author')
                    if author_info:
                        author_element = author_info.find('a')
                        if author_element:
                            author = author_element.get_text(strip=True)
                        else:
                            author = "N/A"
                    else:
                        author = "N/A"
    
                    rating_element = review.find('td', class_='field rating')
                    if rating_element:
                        rating_title = rating_element.find('span', class_='staticStars').get('title', '')
                        if 'did not like it' in rating_title:
                            my_rating = 1
                        elif 'it was ok' in rating_title:
                            my_rating = 2
                        elif 'liked it' in rating_title:
                            my_rating = 3
                        elif 'really liked it' in rating_title:
                            my_rating = 4
                        elif 'it was amazing' in rating_title:
                            my_rating = 5
                        else:
                            my_rating = "N/A"
                    else:
                        my_rating = "N/A"
                                    
                    date_read_str = review.find('td', class_='field date_read').find('div', class_='value').find('span', class_='date_read_value').get_text(strip=True)

                    # Verificar si la fecha tiene el día especificado o no
                    if ',' in date_read_str:
                        # Si la fecha incluye el día, usa el formato '%b %d, %Y'
                        date_read = datetime.strptime(date_read_str, '%b %d, %Y').date()
                    else:
                        # Si la fecha solo incluye el mes y el año, agrega '01' como día y usa el formato '%b %Y %d'
                        date_read = datetime.strptime(date_read_str + ' 01', '%b %Y %d').date()

                    public_rating = review.find('td', class_='field avg_rating').find('div', class_='value').get_text(strip=True)                
                    book_link = review.find('td', class_='field title').find('a')['href']

                    # Verificar si el enlace del libro ya existe en la base de datos
                    existing_book = Book.objects.filter(book_link=book_link).first()

                    if existing_book:
                        # El libro ya existe, omitirlo
                        print(f"El libro '{title}' ya existe en la base de datos.")
                    else:
                        # El libro no existe, insertarlo en la base de datos
                        new_book = Book(
                            title=title,
                            author=author,
                            cover_link=cover_link,
                            my_rating=my_rating,
                            public_rating=public_rating,
                            date_read=date_read,
                            book_link=book_link
                        )
                        new_book.save()

                    print(f"Consecutivo de libro: {book_counter}")
                    print("Nombre del libro:", title)
                    print("Autor:", author)
                    print("Enlace del libro:", book_link)
                    print("Mis estrellas:", my_rating)
                    print("Nota del público:", public_rating)
                    print("Fecha de leído:", date_read)
                    print("----------------------------------")

            print(f"Se insertaron {book_counter} libros en la base de datos.")
        else:
            print("El número de libros en la página web es el mismo que en la base de datos. No es necesario actualizar.")


class Book(models.Model):
    class Meta:
        db_table = 'books'

    title = models.CharField(max_length=200)
    author = models.CharField(max_length=200)
    cover_link = models.TextField()  
    my_rating = models.IntegerField()
    public_rating = models.CharField(max_length=20)
    date_read = models.DateField()
    book_link = models.TextField(unique=True) 

    def __str__(self):
        return self.title
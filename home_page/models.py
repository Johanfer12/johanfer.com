from django.db import models
from bs4 import BeautifulSoup
import requests
import os
import re
import sqlite3

def modify_cover_url(cover_url):
    return re.sub(r'(_SX\d+_SY\d+_|_SY\d+_SX\d+_|_SX\d+_|_SY\d+_)', '_SY700_', cover_url)

def scrap_books():
    folder_path = "home_page/Img/Covers"
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

                title_info = review.find('td', class_='field title')
                if title_info:
                    title_element = title_info.find('a')
                    if title_element:
                        title = title_element.get_text(strip=True)
                    else:
                        title = "N/A"
                else:
                    title = "N/A"
                    
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
                    
                public_rating = review.find('td', class_='field avg_rating').find('div', class_='value').get_text(strip=True)
                date_read = review.find('td', class_='field date_read').find('div', class_='value').find('span', class_='date_read_value').get_text(strip=True)
                book_link = review.find('td', class_='field title').find('a')['href']

                # Insertar los datos en la base de datos si el enlace del libro no está duplicado
                try:
                    Book.objects.get_or_create(
                        title=title,
                        cover_link=cover_link,
                        my_rating=my_rating,
                        public_rating=public_rating,
                        date_read=date_read,
                        book_link=book_link
                    )
                except sqlite3.IntegrityError:
                    print(f"El libro '{title}' ya existe en la base de datos. No se insertará duplicado.")

                print(f"Consecutivo de libro: {book_counter}")
                print("Nombre del libro:", title)
                print("Enlace del libro:", book_link)
                print("Mis estrellas:", my_rating)
                print("Nota del público:", public_rating)
                print("Fecha de leído:", date_read)
                print("----------------------------------")

        print(f"Se insertaron {book_counter} libros en la base de datos.")

class Book(models.Model):
    class Meta:
        db_table = 'books'

    title = models.CharField(max_length=200)
    cover_link = models.TextField()  # Puedes usar TextField para enlaces largos
    my_rating = models.IntegerField()
    public_rating = models.CharField(max_length=20)
    date_read = models.DateField()
    book_link = models.TextField(unique=True)  # Puedes usar TextField para enlaces largos

    def __str__(self):
        return self.title
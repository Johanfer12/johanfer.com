from bs4 import BeautifulSoup
import requests
import os
import re
import sqlite3

# Función para modificar el enlace de la imagen
def modify_cover_url(cover_url):
    # Utilizar expresiones regulares para encontrar y reemplazar el número aleatorio después de SY o SX
    return re.sub(r'(_SX\d+_SY\d+_|_SY\d+_SX\d+_|_SX\d+_|_SY\d+_)', '_SY700_', cover_url)

# Crear una conexión a la base de datos
conn = sqlite3.connect('Home/bookshelf.db')

# Crear un cursor
c = conn.cursor()

# Crear la carpeta si no existe
folder_path = "Home/Img/Covers"
if not os.path.exists(folder_path):
    os.makedirs(folder_path)

# URL base
base_url = "https://www.goodreads.com/review/list/27786474-johan-gonzalez?print=true&ref=nav_mybooks&shelf=read&utf8=%E2%9C%93"

headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.3'
}

# Realizar la solicitud GET a la última página
response = requests.get(base_url, headers=headers)

# Verificar si la solicitud fue exitosa
if response.status_code == 200:
    # Parsear el contenido HTML de la página web
    soup = BeautifulSoup(response.text, 'html.parser')

    # Encontrar el último enlace de paginación para obtener el número total de páginas disponibles
    pagination_div = soup.find("div", id="reviewPagination")
    last_page_link = pagination_div.find_all("a")[-2]  # El penúltimo enlace es el último número de página
    total_pages = int(last_page_link.text)

    # Encontrar el número de libros en la última página
    last_page_url = f"{base_url}&page={total_pages}"
    last_page_response = requests.get(last_page_url, headers=headers)
    last_page_soup = BeautifulSoup(last_page_response.text, 'html.parser')
    last_page_reviews = last_page_soup.find_all('tr', class_='bookalike review')
    last_page_book_count = len(last_page_reviews)
    # Calcular el contador de libros
    book_counter = 0

    # Crear la tabla si no existe
    c.execute('''CREATE TABLE IF NOT EXISTS books
                (id INTEGER PRIMARY KEY,
                title TEXT,
                cover_link TEXT,
                my_rating INTEGER,
                public_rating TEXT,
                date_read TEXT,
                book_link TEXT UNIQUE)''')

    # Iterar sobre todas las páginas de revisión en orden inverso
    for page_number in range(total_pages, 0, -1):
        # Construir la URL de la página actual
        page_url = f"{base_url}&page={page_number}"
        
        # Realizar la solicitud GET a la página actual
        response = requests.get(page_url, headers=headers)
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Encontrar todas las revisiones en la página actual
        reviews = soup.find_all('tr', class_='bookalike review')
        
        # Contar el número de libros en esta página
        page_book_count = len(reviews)
        
        # Iterar sobre cada revisión para extraer la información
        for review in reversed(reviews):  # Iterar en orden inverso para empezar desde abajo hacia arriba
            # Incrementar el contador de libros
            book_counter += 1
            
            # Extraer el enlace de la portada del libro con extensión .jpg
            cover_info = review.find('td', class_='field cover')
            if cover_info:
                cover_link = cover_info.find('img')['src']
                if cover_link.endswith('.jpg'):
                    # Modificar el enlace de la portada
                    modified_cover_url = modify_cover_url(cover_link)
                    
                    # Obtener el nombre del archivo de la portada
                    file_name = f"{book_counter}.jpg"
                    
                    # Verificar si el archivo ya existe en la carpeta de destino
                    if not os.path.exists(os.path.join(folder_path, file_name)):
                        # Descargar la imagen de la portada
                        with open(os.path.join(folder_path, file_name), 'wb') as f:
                            response = requests.get(modified_cover_url)
                            f.write(response.content)


            # Extraer el título del libro
            title_info = review.find('td', class_='field title')
            if title_info:
                title_element = title_info.find('a')
                if title_element:
                    title = title_element.get_text(strip=True)
                else:
                    title = "N/A"
            else:
                title = "N/A"
                
            # Buscar el elemento que contiene las estrellas y el título
            rating_element = review.find('td', class_='field rating')
            if rating_element:
                # Obtener el título del elemento que indica la cantidad de estrellas seleccionadas
                rating_title = rating_element.find('span', class_='staticStars').get('title', '')
                
                # Extraer la cantidad de estrellas basada en el título
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
                    my_rating = "N/A"  # Si no se encuentra ninguna de las frases, asignamos "N/A"
            else:
                my_rating = "N/A"
                
            # Extraer la nota pública
            public_rating = review.find('td', class_='field avg_rating').find('div', class_='value').get_text(strip=True)

            # Extraer la fecha de leído
            date_read = review.find('td', class_='field date_read').find('div', class_='value').find('span', class_='date_read_value').get_text(strip=True)

            # Extraer enlace del libro
            book_link = review.find('td', class_='field title').find('a')['href']

            # Insertar los datos en la base de datos si el enlace del libro no está duplicado
            try:
                c.execute("INSERT INTO books (title, cover_link, my_rating, public_rating, date_read, book_link) VALUES (?, ?, ?, ?, ?, ?)",
                        (title, cover_link, my_rating, public_rating, date_read, book_link))
            except sqlite3.IntegrityError:
                print(f"El libro '{title}' ya existe en la base de datos. No se insertará duplicado.")

            # Imprimir la información extraída
            print(f"Consecutivo de libro: {book_counter}")
            print("Nombre del libro:", title)
            print("Enlace del libro:", book_link)
            print("Mis estrellas:", my_rating)
            print("Nota del público:", public_rating)
            print("Fecha de leído:", date_read)
            print("----------------------------------")

    # Guardar los cambios en la base de datos
    conn.commit()

    # Cerrar la conexión a la base de datos
    conn.close()

    print(f"Se insertaron {book_counter} libros en la base de datos.")

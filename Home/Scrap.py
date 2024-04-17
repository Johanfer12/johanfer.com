from bs4 import BeautifulSoup
import requests

# URL de la página web
url = 'https://www.goodreads.com/review/list/27786474-johan-gonzalez?utf8=%E2%9C%93&print=true&ref=nav_mybooks&shelf=read&title=johan-gonzalez&per_page=1000'  # Reemplaza 'https://www.example.com' con la URL real

headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.3'
}

# Realizar la solicitud GET a la página web
response = requests.get(url, headers=headers)

# Verificar si la solicitud fue exitosa
if response.status_code == 200:
    # Parsear el contenido HTML de la página web
    soup = BeautifulSoup(response.text, 'html.parser')

    # Encontrar todos los elementos 'tr' que tienen la clase 'bookalike review'
    reviews = soup.find_all('tr', class_='bookalike review')

    # Iterar sobre cada revisión para extraer la información
    for review in reviews:

        # Extraer el enlace de la portada del libro con extensión .jpg
        cover_info = review.find('td', class_='field cover')
        if cover_info:
            cover_link = cover_info.find('img')['src']
            if cover_link.endswith('.jpg'):
                cover_url = cover_link
            else:
                cover_url = "N/A"
        else:
            cover_url = "N/A"

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
            
        # Extraer la nota publica
        public_rating = review.find('td', class_='field avg_rating').find('div', class_='value').get_text(strip=True)

        # Extraer la fecha de leído
        date_read = review.find('td', class_='field date_read').find('div', class_='value').find('span', class_='date_read_value').get_text(strip=True)

        # Imprimir la información extraída
        print("Nombre del libro:", title)
        print("Enlace de la portada:", cover_url)
        print("Mis estrellas:", my_rating)
        print("Nota del público:", public_rating)
        print("Fecha de leído:", date_read)
        print("----------------------------------")
else:
    print("Error al realizar la solicitud GET a la página web")

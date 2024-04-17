from bs4 import BeautifulSoup
import requests

# URL base
base_url = "https://www.goodreads.com/review/list/27786474-johan-gonzalez?print=true&ref=nav_mybooks&shelf=read&utf8=%E2%9C%93"

headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.3'
}

# Realizar la solicitud GET a la primera página
response = requests.get(base_url, headers=headers)

# Verificar si la solicitud fue exitosa
if response.status_code == 200:
    # Parsear el contenido HTML de la página web
    soup = BeautifulSoup(response.text, 'html.parser')

    # Encontrar el último enlace de paginación para obtener el número total de páginas disponibles
    pagination_div = soup.find("div", id="reviewPagination")
    last_page_link = pagination_div.find_all("a")[-2]  # El penúltimo enlace es el último número de página
    total_pages = int(last_page_link.text)

    # Iterar sobre todas las páginas de revisión
    for page_number in range(1, total_pages + 1):
        # Construir la URL de la página actual
        page_url = f"{base_url}&page={page_number}"
        
        # Realizar la solicitud GET a la página actual
        response = requests.get(page_url, headers=headers)
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Encontrar todas las revisiones en la página actual
        reviews = soup.find_all('tr', class_='bookalike review')
        
        # Iterar sobre cada revisión para extraer la información
        for review in reviews:
            # Tu código de extracción de información aquí
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
                
            # Extraer la nota pública
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



# Mi Biblioteca: Scraper de Libros de Goodreads con Django

Este proyecto Django se enfoca en desarrollar un scraper web que extrae información de libros de mi lista de lectura en Goodreads y la almacena en una base de datos SQLite3. La aplicación también maneja la descarga y almacenamiento de las portadas de los libros.

## Características

- Extrae información de libros como título, autor, enlace de la portada, calificación personal, calificación pública, fecha de lectura y enlace del libro.
- Descarga y almacena las portadas de los libros en la carpeta `static/Img/Covers`.
- Utiliza la biblioteca `BeautifulSoup` para analizar el HTML de Goodreads.
- Emplea la librería `requests` para realizar solicitudes HTTP y descargar las portadas.
- Implementa una función para modificar los enlaces de las portadas y obtener una resolución más alta.
- Utiliza SQLite3 como base de datos y crea una tabla `books` para almacenar la información de los libros.
- Verifica si el número de libros en Goodreads ha cambiado antes de actualizar la base de datos.
- Evita la duplicación de libros al verificar si el enlace del libro ya existe en la base de datos.

## Instalación

1. Clona el repositorio:

```
git clone https://github.com/tu-usuario/tu-repositorio.git
```

2. Crea un entorno virtual e instala las dependencias:

```
python -m venv env
source env/bin/activate  # En Windows, usa `env\Scripts\activate`
pip install -r requirements.txt
```

3. Aplica las migraciones de Django:

```
python manage.py migrate
```

4. Ejecuta el scraper:

```
python manage.py scrap_books
```

## Explicación del Código

El código principal se encuentra en el archivo `paste.txt`. A continuación, se explica cada sección:

1. **Importación de módulos**: Se importan los módulos necesarios, como `models` de Django, `BeautifulSoup`, `requests`, `os`, `re`, `sqlite3` y `datetime`.

2. **Función `modify_cover_url`**: Esta función modifica el enlace de la portada del libro para obtener una resolución más alta (700 píxeles).

3. **Función `scrap_books`**: Esta es la función principal que realiza el scraping de los libros. Aquí se destacan las siguientes acciones:
   - Crea la carpeta `static/Img/Covers` si no existe.
   - Establece una conexión a la base de datos SQLite3 y crea la tabla `books` si no existe.
   - Obtiene el número total de páginas en la lista de libros de Goodreads.
   - Itera sobre cada página y extrae la información de cada libro.
   - Descarga y almacena las portadas de los libros en la carpeta correspondiente.
   - Inserta los datos de los libros en la base de datos, evitando duplicados.

4. **Modelo `Book`**: Esta es la clase que define el modelo de datos `Book` en Django. Contiene campos como `title`, `author`, `cover_link`, `my_rating`, `public_rating`, `date_read` y `book_link`.

## Uso

1. Asegúrate de tener un entorno virtual activado y las dependencias instaladas.
2. Aplica las migraciones de Django: `python manage.py migrate`.
3. Ejecuta el scraper: `python manage.py scrap_books`.
4. El scraper comenzará a extraer la información de los libros de Goodreads y a descargar las portadas correspondientes.
5. Los datos de los libros se almacenarán en la base de datos SQLite3 `database.db`.
6. Las portadas de los libros se guardarán en la carpeta `static/Img/Covers`.

Siéntete libre de personalizar y adaptar este proyecto según tus necesidades. Si tienes alguna pregunta o sugerencia, no dudes en abrir un issue en el repositorio.
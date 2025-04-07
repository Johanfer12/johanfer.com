# Mi Biblioteca, Noticias y Música: Aplicaciones Django para Libros, Noticias RSS y Spotify

Este proyecto Django incluye tres aplicaciones principales: un scraper web que extrae información de libros de Goodreads, una aplicación de noticias que recopila artículos de fuentes RSS y una aplicación que muestra datos de Spotify.

## Aplicación de Libros

Esta aplicación implementa un scraper web que extrae información detallada de libros de mi lista de lectura en Goodreads y la almacena en una base de datos, incluyendo procesamiento avanzado de imágenes y seguimiento de cambios.

### Características

- Sistema de scraping inteligente:
  - Extrae datos completos: título, autor, portada, calificaciones, fecha de lectura, enlaces y descripciones.
  - Compara el número de libros en Goodreads con la base de datos para determinar si hay actualizaciones.
  - Optimiza el proceso según sea una carga inicial (todas las páginas) o una actualización (solo primera página).
  - Evita duplicados verificando los enlaces de libros existentes.

- Procesamiento avanzado de imágenes:
  - Modifica los enlaces de portadas para obtener la máxima resolución disponible (700px).
  - Convierte automáticamente las imágenes JPG a formato WebP para optimizar almacenamiento y rendimiento.
  - Redimensiona las portadas a un tamaño óptimo (300x450) conservando la calidad.
  - Organiza las imágenes por ID en la carpeta `static/Img/Covers`.

- Extracción de contenido enriquecido:
  - Obtiene descripciones HTML completas de cada libro mediante peticiones adicionales.
  - Procesa y preserva el formato HTML de las descripciones para su visualización.
  - Maneja diferentes formatos de calificación (1-5 estrellas) con interpretación de texto.
  - Normaliza diferentes formatos de fecha (con/sin día específico).

- Seguimiento de cambios:
  - Registra libros eliminados de la lista de lectura para análisis histórico.
  - Mantiene metadatos completos de los libros incluso después de eliminarlos.

- Optimización técnica:
  - Implementa manejo de excepciones robusto para cada fase del proceso.
  - Utiliza peticiones HTTP con headers personalizados para evitar restricciones.
  - Emplea BeautifulSoup para un análisis preciso del HTML de Goodreads.
  - Realiza procesamiento por lotes para mejorar el rendimiento.

### Modelos principales

- **Book**: Almacena la información completa de cada libro (título, autor, portada, calificaciones, fecha, enlaces, descripción).
- **DeletedBook**: Registra libros que fueron eliminados de la lista de lectura en Goodreads.

## Aplicación de Noticias (my_news)

Esta aplicación permite recopilar, filtrar y visualizar noticias de diferentes fuentes RSS con capacidades avanzadas de procesamiento mediante IA.

### Características

- Recopila noticias de múltiples fuentes RSS configurables con priorización automática de contenido reciente.
- Sistema de filtrado multicapa:
  - Filtrado automático basado en palabras clave personalizables.
  - Filtrado inteligente mediante instrucciones de IA configurables.
  - Detección de noticias redundantes mediante análisis de similitud vectorial (embeddings).
- Procesamiento con IA avanzada (Google Gemini):
  - Generación de resúmenes concisos y objetivos de noticias.
  - Extracción de respuestas cortas para titulares tipo pregunta o clickbait.
  - Análisis automático de relevancia y calidad del contenido.
- Capacidad de extracción profunda de contenido:
  - Recuperación del texto completo de artículos cuando es necesario.
  - Extracción de imágenes de alta calidad de los artículos originales.
  - Limpieza y formateo automático del contenido HTML.
- Interfaz de usuario responsiva con:
  - Sistema de paginación para navegación eficiente.
  - Actualización en tiempo real del feed de noticias.
  - Notificaciones de nuevo contenido disponible.
- Optimización de rendimiento:
  - Sistema de reintentos inteligentes para APIs externas.
  - Procesamiento por lotes para mejorar velocidad.
  - Backoff exponencial para gestionar límites de API.

### Modelos principales

- **FeedSource**: Almacena información sobre las fuentes de noticias (nombre, URL, estado, umbral de similitud, configuración de búsqueda profunda).
- **News**: Contiene los detalles de cada noticia (título, descripción, enlace, fecha de publicación, imagen, embedding vectorial, puntuación de similitud, etc.).
- **FilterWord**: Define palabras clave para filtrado automático de noticias.
- **AIFilterInstruction**: Configura instrucciones personalizadas para el filtrado basado en IA.

## Aplicación de Música (spotify)

Esta aplicación integra con la API de Spotify para mostrar, analizar y gestionar los datos musicales del usuario.

### Características

- Sincronización completa con biblioteca de Spotify:
  - Obtiene todas las canciones favoritas guardadas en la cuenta.
  - Almacena metadatos completos: título, artista, álbum, género, duración y fecha de adición.
  - Actualiza automáticamente la biblioteca cuando hay cambios (adiciones o eliminaciones).
- Análisis de tendencias de escucha:
  - Visualiza el top 5 de canciones más escuchadas en el último mes.
  - Analiza evolución de géneros y artistas preferidos.
  - Muestra distribución temporal de adiciones a la biblioteca.
- Experiencia multimedia mejorada:
  - Reproductor de previsualizaciones de 30 segundos integrado en la interfaz.
  - Extracción automática de URLs de previsualizaciones desde la API de Spotify.
  - Visualización de portadas de álbumes en alta resolución.
- Estadísticas visuales interactivas mediante gráficos:
  - Top 5 géneros musicales con distribución porcentual.
  - Top 5 artistas con conteo de canciones.
  - Gráfico temporal de canciones añadidas por mes.
- Seguimiento histórico de cambios:
  - Registro detallado de canciones eliminadas de favoritos.
  - Almacenamiento de fechas exactas de eliminación.
  - Interfaz dedicada para visualizar historial de cambios.
- Optimización técnica:
  - Sistema de caché para información de artistas y géneros.
  - Procesamiento eficiente de grandes bibliotecas musicales.
  - Manejo inteligente de la autenticación OAuth con Spotify.

### Modelos principales

- **SpotifyFavorites**: Almacena las canciones favoritas del usuario con todos sus metadatos asociados.
- **SpotifyTopSongs**: Guarda las canciones más escuchadas recientemente con enlaces a previsualizaciones.
- **DeletedSongs**: Registra un historial completo de las canciones que fueron eliminadas de favoritos.

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

4. Para ejecutar el scraper de libros:

```
python manage.py scrap_books
```

5. Para actualizar el feed de noticias:

```
python manage.py update_news_feed
```

6. Para actualizar los datos de Spotify (requiere configurar las credenciales de la API):

```
python manage.py refresh_spotify_data
```

7. Instala los cronjobs en el servidor (necesario solo en producción):

```
python manage.py crontab add
```

## Uso

### Tareas Automatizadas con django-crontab

El proyecto utiliza `django-crontab` para gestionar tareas programadas que actualizan automáticamente los datos. Estas tareas están definidas en los archivos `tasks.py` de cada aplicación y configuradas en `settings.py`:

```python
CRONJOBS = [
    # Actualiza las noticias cada 30 minutos
    ('*/30 * * * *', 'my_news.tasks.update_news_feed'),
    
    # Actualiza los libros una vez al día a las 2:00 AM
    ('0 2 * * *', 'home_page.tasks.refresh_books_data'),
    
    # Actualiza los datos de Spotify una vez al día a las 3:00 AM
    ('0 3 * * *', 'spotify.tasks.refresh_spotify_data')
]
```

#### Gestión de Tareas Programadas

- **Ver tareas programadas activas**:
  ```
  python manage.py crontab show
  ```

- **Añadir todas las tareas**:
  ```
  python manage.py crontab add
  ```

- **Eliminar todas las tareas**:
  ```
  python manage.py crontab remove
  ```

- **Reiniciar todas las tareas** (útil después de modificar la configuración):
  ```
  python manage.py crontab remove
  python manage.py crontab add
  ```

Las tareas se ejecutan automáticamente en segundo plano según su programación:

- **Libros**: Se actualizan una vez al día (a las 2:00 AM) para obtener nuevas lecturas de Goodreads.
- **Noticias**: Se actualizan cada 30 minutos para mantener el feed de noticias actualizado.
- **Música**: Se actualizan una vez al día (a las 3:00 AM) para sincronizar con la biblioteca de Spotify.

En ambientes de desarrollo local, puede ser más conveniente ejecutar estos comandos manualmente en lugar de configurar los cronjobs.

### Aplicación de Libros

1. Asegúrate de tener un entorno virtual activado y las dependencias instaladas.
2. Ejecuta el scraper: `python manage.py scrap_books`.
3. El scraper comenzará a extraer la información de los libros de Goodreads y a descargar las portadas correspondientes.
4. Los datos de los libros se almacenarán en la base de datos.
5. Las portadas de los libros se guardarán en la carpeta `static/Img/Covers`.

### Aplicación de Noticias

1. Configura tus fuentes de noticias RSS en el panel de administración.
2. Configura palabras de filtrado e instrucciones de IA según tus preferencias.
3. Accede a la ruta `/noticias/` en tu navegador para ver el feed de noticias.
4. Utiliza el botón de actualización para obtener las noticias más recientes.
5. Navega entre las páginas utilizando los controles de paginación.

### Aplicación de Spotify

1. Configura tus credenciales de la API de Spotify (CLIENT_ID, CLIENT_SECRET) en el archivo de configuración.
2. Accede a la ruta `/spotify/` para ver el dashboard con tus canciones favoritas y top 5.
3. Utiliza el reproductor integrado para escuchar previsualizaciones de 30 segundos.
4. Visita `/spotify/stats/` para ver las estadísticas y gráficos de tu música.
5. Consulta `/spotify/deleted/` para ver un historial de las canciones eliminadas.
6. Actualiza los datos haciendo clic en el botón de actualización en el dashboard.

Siéntete libre de personalizar y adaptar este proyecto según tus necesidades. Si tienes alguna pregunta o sugerencia, no dudes en abrir un issue en el repositorio.
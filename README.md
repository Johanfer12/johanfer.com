# Mi Bitácora: Libros, Series, Noticias y Música en Django

Este proyecto Django incluye cuatro aplicaciones principales: una biblioteca que se sincroniza con la lista de lectura de Goodreads vía RSS, una sección de series y películas que se sincroniza con el historial de Trakt, una aplicación de noticias que recopila artículos de fuentes RSS con procesamiento IA, y una aplicación que muestra datos archivados de Spotify.

## Aplicación de Libros

Esta aplicación sincroniza la lista de lectura de Goodreads a través de su feed RSS oficial y la almacena en una base de datos, incluyendo procesamiento de imágenes y seguimiento de cambios.

### Características

- Sincronización vía RSS de Goodreads:
  - Extrae datos completos: título, autor, portada, calificaciones, fecha de lectura, enlaces, descripción, ISBN, páginas y año de publicación.
  - Pagina el feed RSS automáticamente para cargas iniciales grandes.
  - Evita duplicados identificando los libros por su ID de Goodreads.
  - No requiere cookies de sesión ni scraping de HTML.
  - Lee también la estantería `currently-reading`: el libro en curso aparece primero en la biblioteca con un listón diagonal "Leyendo", sin calificación ni fecha hasta terminarlo.

- Procesamiento avanzado de imágenes:
  - Modifica los enlaces de portadas para obtener la máxima resolución disponible (700px).
  - Convierte automáticamente las imágenes JPG a formato WebP para optimizar almacenamiento y rendimiento.
  - Redimensiona las portadas a un tamaño óptimo (300x450) conservando la calidad.
  - Organiza las imágenes por ID en la carpeta `media/Covers`.

- Seguimiento de cambios:
  - Registra libros eliminados de la lista de lectura para análisis histórico.
  - Mantiene metadatos completos de los libros incluso después de eliminarlos.

### Modelos principales

- **Book**: Almacena la información completa de cada libro (título, autor, portada, calificaciones, fecha, enlaces, descripción, flag de lectura en curso).
- **DeletedBook**: Registra libros que fueron eliminados de la lista de lectura en Goodreads.

## Aplicación de Series y Películas (watching)

Sección "Mi TV": sincroniza el historial de visualización desde la API pública de Trakt (v2, sin OAuth para perfiles públicos) y muestra las series y películas vistas con sus pósters.

### Características

- Sincronización con la API de Trakt:
  - Historial completo de películas y episodios con deduplicación por evento.
  - Calificaciones personales y totales de episodios vistos por serie.
  - Corta la paginación al llegar a eventos ya guardados.
- Pósters y metadatos desde TMDB (calificación pública, episodios disponibles, sinopsis en español), convertidos a WebP en `media/Posters` (un póster por obra; los episodios comparten el de su serie).
- Una tarjeta por obra: los episodios de una serie se agrupan mostrando cuántos llevas y el último visto (ej. `T01E08`).
- Listón diagonal "Viendo" en series con actividad reciente que aún tienen episodios pendientes.
- Botones flotantes para alternar entre series y películas (`/viendo/?tipo=...`).

### Modelos principales

- **WatchedItem**: Un evento del historial (película o episodio) con temporada/episodio, calificaciones, fecha y IDs de Trakt/TMDB.

## Aplicación de Noticias (my_news)

Esta aplicación permite recopilar, filtrar y visualizar noticias de diferentes fuentes RSS con capacidades avanzadas de procesamiento mediante IA.

### Características

- Recopila noticias de múltiples fuentes RSS configurables con priorización automática de contenido reciente.
- Sistema de filtrado multicapa:
  - Filtrado automático basado en palabras clave personalizables.
  - Filtrado inteligente mediante instrucciones de IA configurables.
  - Detección de noticias redundantes mediante análisis de similitud vectorial (embeddings).
- Procesamiento con IA (Cerebras para resúmenes, Gemini para embeddings):
  - Generación de resúmenes concisos y objetivos de noticias.
  - Extracción de respuestas cortas para titulares tipo pregunta o clickbait.
  - Análisis automático de relevancia y calidad del contenido.
  - El modelo activo se configura en la BD (AIModelSetting, editable desde el admin) con nombre neutral de proveedor.
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

Esta aplicación muestra los datos musicales del usuario. La sincronización con la API de Spotify fue retirada (los cambios en la API la dejaron detrás de un plan de pago), por lo que los datos guardados son un archivo histórico que ya no se actualiza. La playlist actual se muestra mediante un iframe embebido de Spotify.

### Características

- Dashboard con la playlist actual embebida vía iframe oficial de Spotify (siempre al día, sin API).
- Estadísticas visuales sobre el histórico de favoritos guardado:
  - Top 5 géneros musicales con distribución porcentual.
  - Top 5 artistas con conteo de canciones.
  - Gráfico temporal de canciones añadidas por mes.
- Historial de canciones que fueron eliminadas de favoritos mientras la sincronización estuvo activa.

### Modelos principales

- **SpotifyFavorites**: Archivo histórico de las canciones favoritas con sus metadatos (ya no se actualiza).
- **DeletedSongs**: Historial de las canciones que fueron eliminadas de favoritos.

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

4. Para actualizar los libros desde el RSS de Goodreads manualmente:

```
python manage.py shell -c "from home_page.utils import refresh_books_data; refresh_books_data()"
```

5. Para actualizar el feed de noticias manualmente:

```
python manage.py shell -c "from my_news.tasks import update_news_cron; update_news_cron()"
```

6. Instala los cronjobs en el servidor (necesario solo en producción):

```
python manage.py crontab add
```

## Variables de entorno recomendadas

Para abrir `/visitas/` sin iniciar sesión durante el desarrollo local:

```
DEBUG=true
VISITS_ALLOW_LOCAL_WITHOUT_LOGIN=true
```

La excepción solo se aplica cuando ambas variables están activas. En producción,
mantén `DEBUG=false`; los usuarios seguirán necesitando una cuenta de superusuario.

Para la sincronización de libros con Goodreads (vía RSS, sin cookies):

```
GOODREADS_RSS_URL=https://www.goodreads.com/review/list_rss/27786474?shelf=read
GOODREADS_RSS_PER_PAGE=200
```

Para la sección de series y películas (Trakt + TMDB):

```
TRAKT_CLIENT_ID=...   # Client ID de una app creada en https://trakt.tv/oauth/applications
TRAKT_USERNAME=...    # Usuario de Trakt (el perfil y el historial deben ser públicos)
TMDB_API_KEY=...      # API key gratuita de https://www.themoviedb.org/settings/api
```

## Uso

### Tareas Automatizadas con django-crontab

El proyecto utiliza `django-crontab` para gestionar tareas programadas que actualizan automáticamente los datos. Estas tareas están definidas en los archivos `tasks.py` de cada aplicación y configuradas en `settings.py`:

```python
CRONJOBS = [
    # Actualiza los libros una vez al día a las 12:55 PM
    ('55 12 * * *', 'home_page.tasks.update_books_cron'),

    # Actualiza las noticias cada 30 minutos
    ('*/30 * * * *', 'my_news.tasks.update_news_cron'),

    # Actualiza series y películas desde Trakt una vez al día
    ('25 13 * * *', 'watching.tasks.update_watching_cron'),
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

- **Libros**: Se actualizan una vez al día (12:55 PM) leyendo el feed RSS de Goodreads.
- **Noticias**: Se actualizan cada 30 minutos para mantener el feed de noticias actualizado.
- **Series y películas**: Se actualizan una vez al día (1:25 PM) desde la API de Trakt.

Nota de producción (Raspberry):

- Actualmente la tarea de noticias se limita a la franja `08:00` a `22:00` (hora del servidor):
  - `*/30 8-21 * * * ... #News`
  - `0 22 * * * ... #News`

En ambientes de desarrollo local, puede ser más conveniente ejecutar estos comandos manualmente en lugar de configurar los cronjobs.

### Aplicación de Libros

1. Asegúrate de tener un entorno virtual activado y las dependencias instaladas.
2. La sincronización corre automáticamente por cron, o puedes lanzarla manualmente:
   `python manage.py shell -c "from home_page.utils import refresh_books_data; refresh_books_data()"`
3. Los datos se leen del feed RSS de Goodreads y se almacenan en la base de datos.
4. Las portadas de los libros se guardarán en la carpeta `media/Covers`.

### Aplicación de Series y Películas

1. Crea una app en Trakt y configura las variables de entorno (ver arriba).
2. La sincronización corre automáticamente por cron, o puedes lanzarla manualmente:
   `python manage.py shell -c "from watching.utils import refresh_watching_data; refresh_watching_data()"`
3. Accede a la ruta `/viendo/` para ver la sección "Mi TV"; los botones flotantes alternan entre series y películas.
4. Los pósters se guardan en la carpeta `media/Posters`.

### Aplicación de Noticias

1. Configura tus fuentes de noticias RSS en el panel de administración.
2. Configura palabras de filtrado e instrucciones de IA según tus preferencias.
3. Accede a la ruta `/noticias/` en tu navegador para ver el feed de noticias.
4. Utiliza el botón de actualización para obtener las noticias más recientes.
5. Navega entre las páginas utilizando los controles de paginación.

### Aplicación de Spotify

La sincronización con la API de Spotify fue retirada; no requiere credenciales. Las vistas muestran el archivo histórico guardado en la base de datos y la playlist actual vía iframe.

1. Accede a la ruta `/spotify/` para ver el dashboard con la playlist embebida.
2. Visita `/spotify/stats/` para ver las estadísticas y gráficos del histórico de música.
3. Consulta `/spotify/deleted/` para ver el historial de canciones eliminadas.

Siéntete libre de personalizar y adaptar este proyecto según tus necesidades. Si tienes alguna pregunta o sugerencia, no dudes en abrir un issue en el repositorio.

import feedparser
from datetime import datetime, timedelta
from django.utils import timezone
from .models import News, FeedSource
import re
import google.generativeai as genai
from config import GOOGLE_API_KEY
import time
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin

class FeedService:
    @staticmethod
    def initialize_gemini():
        genai.configure(api_key=GOOGLE_API_KEY)
        return genai.GenerativeModel('gemini-2.0-flash-thinking-exp-01-21')

    @staticmethod
    def process_description_with_gemini(description, model, max_retries=4):
        prompt = """
        Resume el siguiente texto de noticia, eliminando cualquier clickbait y manteniendo 
        solo la información relevante. El resumen debe ser conciso y objetivo:

        {text}
        """.format(text=description)

        for attempt in range(max_retries):
            try:
                response = model.generate_content(prompt)
                return response.text.strip()
            except Exception as e:
                if "429" in str(e):
                    print(f"Límite de peticiones alcanzado (intento {attempt + 1}/{max_retries}). Esperando 15 segundos...")
                    time.sleep(15)  # Esperar 15 segundos antes de reintentar
                    continue
                print(f"Error procesando con Gemini: {str(e)}")
                return description
        
        print("Se agotaron los reintentos. Usando descripción original.")
        return description

    @staticmethod
    def extract_image_from_description(description):
        # Buscar una URL de imagen en el HTML de la descripción
        img_pattern = r'<img[^>]+src="([^">]+)"'
        match = re.search(img_pattern, description)
        return match.group(1) if match else None

    @staticmethod
    def get_full_article_content(url):
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
            }
            response = requests.get(url, headers=headers, timeout=10)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Eliminar elementos no deseados
            for element in soup.find_all(['script', 'style', 'nav', 'header', 'footer', 'iframe']):
                element.decompose()
            
            # Buscar el contenido principal con diferentes selectores
            content = (
                soup.find('div', {'itemprop': 'articleBody'}) or  # Nuevo selector específico
                soup.find('article') or 
                soup.find(class_=['content', 'article-content', 'post-content', 'entry-content'])
            )
            
            if content:
                # Procesar imágenes para obtener URLs absolutas
                for img in content.find_all('img'):
                    if img.get('src'):
                        img['src'] = urljoin(url, img['src'])
                
                return content.get_text(separator=' ', strip=True)
            
            return None
        except Exception as e:
            print(f"Error obteniendo contenido completo: {str(e)}")
            return None

    @staticmethod
    def fetch_and_save_news():
        print("Iniciando proceso de obtención de noticias...")
        start_time = time.time()
        
        print("Inicializando modelo Gemini...")
        model = FeedService.initialize_gemini()
        sources = FeedSource.objects.filter(active=True)
        print(f"Procesando {sources.count()} fuentes activas")
        new_articles_count = 0
        
        # Calcular la fecha límite (1 mes atrás)
        one_month_ago = timezone.now() - timedelta(days=30)
        
        for source in sources:
            print(f"\nProcesando fuente: {source.name}")
            
            # Obtener la fecha de la última noticia para esta fuente
            latest_news = News.objects.filter(
                source=source,
                is_deleted=False
            ).order_by('-published_date').first()
            
            latest_date = latest_news.published_date if latest_news else one_month_ago
            
            # Usar la fecha más reciente entre la última noticia y hace un mes
            cutoff_date = max(latest_date, one_month_ago)
            
            feed = feedparser.parse(source.url)
            print(f"Encontradas {len(feed.entries)} entradas en el feed")
            
            # Ordenar entradas por fecha más reciente primero
            sorted_entries = []
            for entry in feed.entries:
                if hasattr(entry, 'published_parsed') and entry.published_parsed:
                    published = datetime(*entry.published_parsed[:6])
                    if timezone.is_naive(published):
                        published = timezone.make_aware(published)
                    sorted_entries.append((published, entry))
            
            sorted_entries.sort(reverse=True)
            
            # Procesar entradas ordenadas hasta encontrar una antigua
            for published, entry in sorted_entries:
                # Si la noticia es más antigua que el límite, saltamos el resto
                if published < cutoff_date:
                    print(f"Saltando {len(sorted_entries)} entradas restantes por ser más antiguas que {cutoff_date}")
                    break
                
                print(f"\nProcesando entrada: {entry.title}")
                
                # Verificar si la noticia ya existe
                guid = entry.get('id', entry.link)
                if News.objects.filter(guid=guid).exists():
                    print("Noticia ya existe, continuando con siguiente entrada")
                    continue
                
                # Convertir la fecha de publicación
                if hasattr(entry, 'published_parsed') and entry.published_parsed:
                    published = datetime(*entry.published_parsed[:6])
                    if timezone.is_naive(published):
                        published = timezone.make_aware(published)
                else:
                    published = timezone.now()
                
                # Si la noticia es más antigua que el límite, la saltamos
                if published < cutoff_date:
                    continue
                
                # Procesar la descripción con Gemini
                original_description = entry.get('description', '')
                
                # Si deep_search está activado, intentar obtener el contenido completo
                if source.deep_search:
                    full_content = FeedService.get_full_article_content(entry.link)
                    if full_content:
                        original_description = full_content
                
                processed_description = FeedService.process_description_with_gemini(
                    original_description, 
                    model
                )

                # Buscar imagen en diferentes lugares posibles del feed
                image_url = None
                
                # 1. Buscar en media_content
                if hasattr(entry, 'media_content') and entry.media_content:
                    image_url = entry.media_content[0].get('url')
                
                # 2. Buscar en enclosures
                if not image_url and hasattr(entry, 'enclosures') and entry.enclosures:
                    for enclosure in entry.enclosures:
                        if enclosure.get('type', '').startswith('image/'):
                            image_url = enclosure.get('href')
                            break

                # 3. Buscar en la descripción
                if not image_url and hasattr(entry, 'description'):
                    image_url = FeedService.extract_image_from_description(entry.description)

                # 4. Buscar en content
                if not image_url and hasattr(entry, 'content'):
                    for content in entry.content:
                        if 'value' in content:
                            found_image = FeedService.extract_image_from_description(content['value'])
                            if found_image:
                                image_url = found_image
                                break

                # Crear la nueva noticia
                News.objects.create(
                    guid=guid,
                    title=entry.title,
                    description=processed_description,
                    link=entry.link,
                    published_date=published,
                    source=source,
                    image_url=image_url
                )
                new_articles_count += 1
            
            source.last_fetch = timezone.now()
            source.save()
            print(f"Actualizada fecha de última obtención para {source.name}")
        
        total_time = time.time() - start_time
        print(f"\nProceso completado en {total_time:.2f} segundos")
        print(f"Total de nuevas noticias: {new_articles_count}")
        
        return new_articles_count 
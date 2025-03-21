import feedparser
from datetime import datetime, timedelta
from django.utils import timezone
import pytz
from .models import News, FeedSource, FilterWord
import re
import google.generativeai as genai
from config import GOOGLE_API_KEY
import time
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin
import numpy as np
from django.db.models import Q

class EmbeddingService:
    @staticmethod
    def initialize_embedding_model():
        """Inicializa la configuración de la API de Gemini para embeddings"""
        genai.configure(api_key=GOOGLE_API_KEY)
        return "models/text-embedding-004"  # Retorna el nombre del modelo en lugar de una instancia

    @staticmethod
    def generate_embedding(text, model_name=None, max_retries=3):
        """Genera embeddings para un texto usando la API de Gemini"""
        if model_name is None:
            model_name = EmbeddingService.initialize_embedding_model()
        
        # Preprocesar el texto para tener un contenido más limpio
        clean_text = re.sub(r'<.*?>', ' ', text)  # Eliminar etiquetas HTML
        clean_text = re.sub(r'\s+', ' ', clean_text).strip()  # Normalizar espacios
        
        # Asegurar que el texto no sea demasiado largo
        if len(clean_text) > 8000:
            clean_text = clean_text[:8000]
        
        for attempt in range(max_retries):
            try:
                # Usar directamente genai.embed_content en lugar de model.embed_content
                result = genai.embed_content(
                    model=model_name,
                    content=clean_text,
                    task_type="retrieval_document",
                )
                
                # Acceder al embedding según la estructura retornada por la API
                return result['embedding']
            except Exception as e:
                if "429" in str(e) and attempt < max_retries - 1:
                    wait_time = (attempt + 1) * 5  # Backoff exponencial
                    print(f"Límite de peticiones alcanzado. Esperando {wait_time} segundos...")
                    time.sleep(wait_time)
                    continue
                print(f"Error generando embedding: {str(e)}")
                return None
        
        print("Se agotaron los reintentos para generar embedding.")
        return None

    @staticmethod
    def cosine_similarity(embedding1, embedding2):
        """Calcula la similitud del coseno entre dos embeddings"""
        if not embedding1 or not embedding2:
            return 0.0
            
        # Convertir a numpy arrays para cálculos eficientes
        vec1 = np.array(embedding1)
        vec2 = np.array(embedding2)
        
        # Normalizar los vectores
        norm_vec1 = vec1 / np.linalg.norm(vec1)
        norm_vec2 = vec2 / np.linalg.norm(vec2)
        
        # Calcular similitud del coseno
        similarity = np.dot(norm_vec1, norm_vec2)
        
        return float(similarity)
    
    @staticmethod
    def check_redundancy(news_item, model_name=None, threshold=0.92):
        """
        Verifica si una noticia es redundante comparando con las existentes
        
        Args:
            news_item: Objeto News que se quiere verificar
            model_name: Nombre del modelo de embeddings (opcional)
            threshold: Umbral de similitud para considerar redundante (0-1)
            
        Returns:
            tuple: (es_redundante, noticia_similar, puntuación_similitud)
        """
        # Inicializar el modelo si no se proporciona
        if model_name is None:
            model_name = EmbeddingService.initialize_embedding_model()
        
        # Generar embedding para la noticia actual
        if not news_item.embedding:
            # Combinar título y descripción para un mejor embedding
            content_for_embedding = f"{news_item.title} {news_item.description}"
            news_item.embedding = EmbeddingService.generate_embedding(content_for_embedding, model_name)
            news_item.save(update_fields=['embedding'])
        
        # No continuar si no se pudo generar el embedding
        if not news_item.embedding:
            return False, None, 0.0
        
        # Buscar noticias de los últimos 7 días
        time_threshold = timezone.now() - timedelta(days=7)
        
        # Buscar todas las noticias recientes, eliminadas o no, pero excluyendo las redundantes y filtradas
        recent_news = News.objects.filter(
            created_at__gte=time_threshold,
            is_redundant=False,  # No comparamos con noticias redundantes
            is_filtered=False,  # No comparamos con noticias filtradas
            embedding__isnull=False
        ).exclude(id=news_item.id)
        
        highest_similarity = 0.0
        most_similar_news = None
        
        # Comparar con cada noticia reciente
        for existing_news in recent_news:
            similarity = EmbeddingService.cosine_similarity(
                news_item.embedding, existing_news.embedding
            )
            
            if similarity > highest_similarity:
                highest_similarity = similarity
                most_similar_news = existing_news
        
        # Determinar si es redundante basándose en el umbral
        is_redundant = highest_similarity >= threshold
        
        return is_redundant, most_similar_news, highest_similarity


class FeedService:
    @staticmethod
    def initialize_gemini():
        genai.configure(api_key=GOOGLE_API_KEY)
        #return genai.GenerativeModel('gemini-2.0-flash-thinking-exp-01-21')
        return genai.GenerativeModel('gemini-2.0-flash')

    @staticmethod
    def process_description_with_gemini(description, model, max_retries=4):
        prompt = """
        Resume el siguiente texto de noticia, eliminando cualquier clickbait y relleno, manteniendo 
        solo la información relevante. El resumen debe ser conciso y objetivo, manteniendo los puntos clave:

        {text}
        """.format(text=description)

        for attempt in range(max_retries):
            try:
                response = model.generate_content(prompt)
                text = response.text.strip()
                
                # Procesar el texto para mantener formato
                processed_text = text
                
                # 1. Convertir asteriscos en bulletpoints HTML con negrita
                processed_text = re.sub(r'^\* (.+?)$', r'• <strong>\1</strong>', processed_text, flags=re.MULTILINE)
                
                # 2. Convertir otros **texto** en <strong>
                processed_text = re.sub(r'\*\*(.*?)\*\*', r'<strong>\1</strong>', processed_text)
                
                # 3. Convertir saltos de línea dobles en <br><br> y simples en <br>
                processed_text = processed_text.replace('\n\n', '<br><br>')
                processed_text = processed_text.replace('\n', '<br>')
                
                # 4. Asegurar que los bulletpoints tengan espacio
                processed_text = processed_text.replace('•', '<br>•')
                
                return processed_text
                
            except Exception as e:
                if "429" in str(e):
                    print(f"Límite de peticiones alcanzado (intento {attempt + 1}/{max_retries}). Esperando 15 segundos...")
                    time.sleep(15)
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
                soup.find('div', {'itemprop': 'articleBody'}) or
                soup.find('article') or 
                soup.find(class_=['content', 'article-content', 'post-content', 'entry-content'])
            )
            
            # Inicializar variables para el retorno
            text_content = None
            image_url = None
            
            if content:
                # Buscar la primera imagen relevante
                img_tag = content.find('img')
                if img_tag and img_tag.get('src'):
                    image_url = urljoin(url, img_tag['src'])
                
                # Si no encontramos imagen en el contenido principal, buscar en todo el artículo
                if not image_url:
                    img_tag = soup.find('img', {'class': ['featured-image', 'wp-post-image', 'article-image']})
                    if img_tag and img_tag.get('src'):
                        image_url = urljoin(url, img_tag['src'])
                
                # Obtener el texto del contenido
                text_content = content.get_text(separator=' ', strip=True)
            
            return {
                'text': text_content,
                'image_url': image_url
            }
        except Exception as e:
            print(f"Error obteniendo contenido completo: {str(e)}")
            return {'text': None, 'image_url': None}

    @staticmethod
    def should_filter_news(title, description):
        filter_words = FilterWord.objects.filter(active=True).values_list('word', flat=True)
        text_to_check = f"{title} {description}".lower()
        
        for word in filter_words:
            if word.lower().strip() in text_to_check:
                return True
        return False

    @staticmethod
    def fetch_and_save_news():
        print("Iniciando proceso de obtención de noticias...")
        start_time = time.time()
        
        print("Inicializando modelos...")
        gemini_model = FeedService.initialize_gemini()
        embedding_model_name = EmbeddingService.initialize_embedding_model()
        
        sources = FeedSource.objects.filter(active=True)
        print(f"Procesando {sources.count()} fuentes activas")
        new_articles_count = 0
        
        # Calcular la fecha límite (1 mes atrás)
        one_month_ago = timezone.now() - timedelta(days=30)
        
        # Lista para almacenar todas las entradas de todas las fuentes
        all_entries = []
        
        # Primero, recolectar todas las entradas de todas las fuentes
        for source in sources:
            print(f"\nRecolectando entradas de fuente: {source.name}")
            
            # Obtener la fecha de la última noticia para esta fuente
            latest_news = News.objects.filter(
                source=source,
                is_deleted=False,
                is_filtered=False
            ).order_by('-published_date').first()
            
            latest_date = latest_news.published_date if latest_news else one_month_ago
            
            # Usar la fecha más reciente entre la última noticia y hace un mes
            cutoff_date = max(latest_date, one_month_ago)
            
            feed = feedparser.parse(source.url)
            print(f"Encontradas {len(feed.entries)} entradas en el feed")
            
            # Recolectar entradas válidas
            for entry in feed.entries:
                # Convertir la fecha de publicación
                if hasattr(entry, 'published_parsed') and entry.published_parsed:
                    # Crear fecha en UTC (los feeds generalmente usan UTC como estándar)
                    published_utc = datetime(*entry.published_parsed[:6])
                    if timezone.is_naive(published_utc):
                        published_utc = timezone.make_aware(published_utc, timezone=pytz.UTC)
                    
                    # Convertir a la zona horaria del proyecto
                    published = published_utc.astimezone(timezone.get_current_timezone())
                else:
                    published = timezone.now()
                
                # Si la noticia es más antigua que el límite, la saltamos
                if published < cutoff_date:
                    continue
                
                # Verificar si la noticia ya existe
                guid = entry.get('id', entry.link)
                if News.objects.filter(guid=guid).exists():
                    continue
                
                # Agregar la entrada a la lista con su fuente y fecha
                all_entries.append({
                    'entry': entry,
                    'source': source,
                    'published': published,
                    'guid': guid
                })
        
        # Ordenar todas las entradas por fecha de más reciente a más antigua
        all_entries.sort(key=lambda x: x['published'], reverse=True)
        print(f"\nSe recolectaron {len(all_entries)} nuevas entradas de todas las fuentes")
        
        # Ordenar todas las entradas por fecha de más antigua a más reciente para procesamiento
        all_entries.sort(key=lambda x: x['published'], reverse=False)
        print(f"\nSe recolectaron {len(all_entries)} nuevas entradas de todas las fuentes")
        
        # Contador para noticias redundantes
        redundant_count = 0
        
        # Procesar todas las entradas en orden (de más antigua a más reciente)
        for item in all_entries:
            entry = item['entry']
            source = item['source']
            published = item['published']
            guid = item['guid']
            
            print(f"\nProcesando entrada: {entry.title} ({published})")
            
            # Verificar si la noticia debe ser filtrada
            if FeedService.should_filter_news(entry.title, entry.get('description', '')):
                print(f"Noticia filtrada por palabras prohibidas: {entry.title}")
                News.objects.create(
                    guid=guid,
                    title=entry.title,
                    description=entry.get('description', ''),
                    link=entry.link,
                    published_date=published,
                    source=source,
                    is_filtered=True  # Marcamos como filtrada en lugar de eliminada
                )
                new_articles_count += 1
                continue
            
            # Primero intentar obtener la imagen del feed
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

            # Obtener el contenido original para procesar
            original_description = entry.get('description', '')
            
            # Si deep_search está activado, obtener el contenido completo independientemente de la imagen
            if source.deep_search:
                full_content = FeedService.get_full_article_content(entry.link)
                if full_content['text']:
                    original_description = full_content['text']
                # Solo usar la imagen del contenido si no se encontró una en el feed
                if not image_url and full_content['image_url']:
                    image_url = full_content['image_url']

            processed_description = FeedService.process_description_with_gemini(
                original_description, 
                gemini_model
            )

            # Crear la nueva noticia
            news_item = News.objects.create(
                guid=guid,
                title=entry.title,
                description=processed_description,
                link=entry.link,
                published_date=published,
                source=source,
                image_url=image_url
            )
            new_articles_count += 1
            
            # Generar embedding para la noticia
            content_for_embedding = f"{entry.title} {processed_description}"
            embedding = EmbeddingService.generate_embedding(content_for_embedding, embedding_model_name)
            if embedding:
                news_item.embedding = embedding
                news_item.save(update_fields=['embedding'])
                
                # Verificar redundancia
                is_redundant, similar_news, similarity_score = EmbeddingService.check_redundancy(
                    news_item, embedding_model_name
                )
                
                if is_redundant and similar_news:
                    print(f"¡Noticia redundante detectada! Similar a: {similar_news.title}")
                    print(f"Puntuación de similitud: {similarity_score:.4f}")
                    
                    # Marcar como redundante y filtrada
                    news_item.is_redundant = True
                    news_item.is_filtered = True  # Usamos is_filtered en lugar de is_deleted
                    news_item.similar_to = similar_news
                    news_item.similarity_score = similarity_score
                    news_item.save()
                    
                    redundant_count += 1
        
        # Actualizar la fecha de última obtención para todas las fuentes
        for source in sources:
            source.last_fetch = timezone.now()
            source.save()
            print(f"Actualizada fecha de última obtención para {source.name}")
        
        total_time = time.time() - start_time
        print(f"\nProceso completado en {total_time:.2f} segundos")
        print(f"Total de nuevas noticias: {new_articles_count}")
        print(f"Noticias redundantes eliminadas: {redundant_count}")
        
        return new_articles_count 
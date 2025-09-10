import feedparser
from datetime import datetime, timedelta
from django.utils import timezone
import pytz
from .models import News, FeedSource, FilterWord, AIFilterInstruction, GeminiGlobalSetting
import re
from google import genai
from google.genai import types
import time
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin
import numpy as np
from django.db.models import Q
import json

class EmbeddingService:
    @staticmethod
    def initialize_embedding_model():
        """Crea un cliente genai para usar en embeddings."""
        # Cambiado: Devolver un cliente en lugar del nombre del modelo
        return genai.Client()

    @staticmethod
    # Cambiado: Aceptar client en lugar de model_name
    def generate_embedding(text, client, max_retries=3):
        """Genera embeddings para un texto usando la API de Gemini a través del cliente."""
        
        # Preprocesar el texto para tener un contenido más limpio
        clean_text = re.sub(r'<.*?>', ' ', text)  # Eliminar etiquetas HTML
        clean_text = re.sub(r'\s+', ' ', clean_text).strip()  # Normalizar espacios
        
        # Asegurar que el texto no sea demasiado largo
        if len(clean_text) > 8000:
            clean_text = clean_text[:8000]
        
        for attempt in range(max_retries):
            try:
                # Cambiado: Usar client.models.embed_content y pasar task_type en config
                result = client.models.embed_content(
                    model="models/text-embedding-004",
                    contents=clean_text,
                    # Corregido: Mover task_type a un objeto EmbedContentConfig
                    config=types.EmbedContentConfig(task_type="retrieval_document") 
                )
                
                # Extraer los valores del embedding
                try:
                    if hasattr(result, 'embeddings') and result.embeddings:
                        first_embedding = result.embeddings[0]
                        if hasattr(first_embedding, 'values'):
                            return list(map(float, first_embedding.values))
                    
                    # Fallback seguro
                    return []
                except Exception as e:
                    print(f"Error al extraer valores del embedding: {str(e)}")
                    return []
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
    def check_redundancy(news_item, client):
        """
        Verifica si una noticia es redundante comparando con las existentes
        
        Args:
            news_item: Objeto News que se quiere verificar
            client: Cliente genai para generar embeddings
            
        Returns:
            tuple: (es_redundante, noticia_similar, puntuación_similitud)
        """
        # Obtener el umbral de la fuente de la noticia
        threshold = news_item.source.similarity_threshold

        # Generar embedding para la noticia actual si no lo tiene
        if not news_item.embedding:
            # Combinar título y descripción para un mejor embedding
            content_for_embedding = f"{news_item.title} {news_item.description}"
            news_item.embedding = EmbeddingService.generate_embedding(content_for_embedding, client)
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
        
        # Determinar si es redundante basándose en el umbral de la fuente
        is_redundant = highest_similarity >= threshold
        
        return is_redundant, most_similar_news, highest_similarity


class FeedService:
    @staticmethod
    def initialize_gemini():
        # Cambiado: Crear y devolver un cliente genai
        return genai.Client()

    @staticmethod
    def process_content_with_gemini(title, original_content, client, global_gemini_model_name, max_retries=3):
        """Genera el resumen principal, la respuesta corta y determina si debe filtrarse por IA."""

        # Obtener instrucciones de filtro IA activas
        ai_filter_instructions = AIFilterInstruction.objects.filter(active=True)
        filter_instructions_text = "\n".join([f"- {inst.instruction}" for inst in ai_filter_instructions])

        # Limitar longitud del contenido para el prompt
        content_limit = 4000
        content_for_prompt = original_content[:content_limit]

        prompt = f"""
        Analiza el siguiente titular y contenido de noticia:
        Titular: '{title}'
        Contenido: '{content_for_prompt}...' 

        Realiza las siguientes tareas y devuelve el resultado EXACTAMENTE en formato JSON:
        1.  **summary**: Genera un resumen conciso y objetivo del contenido completo, en español, de aproximadamente 60 a 70 palabras, eliminando clickbait y relleno, manteniendo los puntos clave. NO apliques formato HTML aquí, solo texto plano.
        2.  **short_answer**: Analiza el titular. Si el titular:
            (a) Es una pregunta directa (ej: '¿Por qué deberías...?', '¿Cuál es...?').
            O (b) NO es una pregunta directa PERO crea una fuerte expectativa de una respuesta concreta, revelación, explicación, lista, o 'secreto' que se encuentra en el contenido (ej: 'El truco definitivo para...', 'Así es como funciona X cosa...', 'La razón por la que Y sucede...', 'Descubren el motivo de Z...', 'Cinco claves para entender...', 'Lo que nadie te contó sobre...').
            Si se cumple (a) o (b), extrae o resume la respuesta/punto clave del contenido original de forma EXTREMADAMENTE CONCISA (máximo 15 palabras) y DIRECTA. No uses introducciones ni parafrasees. Si el titular NO cumple estas condiciones (es decir, es un titular informativo estándar que no genera esa expectativa específica), el valor de 'short_answer' debe ser null (JSON null).
        3.  **ai_filter**: Basándote en las siguientes instrucciones de filtrado, determina si esta noticia DEBE SER ELIMINADA. Si coincide con ALGUNA instrucción, el valor debe ser EXACTAMENTE EL TEXTO LITERAL de la instrucción que coincidió (solo una, la primera que coincida si hay varias). Si NO coincide con ninguna, el valor debe ser null (JSON null).
            Instrucciones de Filtrado:
            {filter_instructions_text if filter_instructions_text else "(No hay instrucciones de filtro IA activas)"}

        Ejemplo de JSON de salida esperado (sin filtro IA):
        {{
          "summary": "Texto del resumen principal aquí.",
          "short_answer": null,
          "ai_filter": null
        }}
        Ejemplo de JSON de salida esperado (con filtro IA):
        {{
          "summary": "Resumen de la noticia sobre horóscopos.",
          "short_answer": null,
          "ai_filter": "Noticias sobre horóscopos"
        }}
        Ejemplo de JSON de salida esperado (clickbait pregunta directa):
        {{
          "summary": "Resumen conciso del artículo aquí.",
          "short_answer": "La clave fue [respuesta directa].",
          "ai_filter": null
        }}
        Ejemplo de JSON de salida esperado (clickbait implícito):
        {{
          "summary": "Resumen del artículo sobre productividad.",
          "short_answer": "El truco es usar la técnica Pomodoro.",
          "ai_filter": null
        }}

        IMPORTANTE: Responde únicamente con el objeto JSON válido, sin texto adicional antes o después.
        """

        # Definir generation_config aquí
        generation_config = types.GenerationConfig(response_mime_type="application/json")

        for attempt in range(max_retries):
            try:
                # Cambiado: Usar client.models.generate_content y pasar config
                response = client.models.generate_content(
                    # Cambiado: Usar el modelo global de Gemini
                    model=global_gemini_model_name,
                    contents=prompt,
                    # Corregido: Pasar generation_config dentro de config
                    config=types.GenerateContentConfig(
                        response_mime_type="application/json",
                        # Añadido: Configuración de pensamiento
                        thinking_config=types.ThinkingConfig(thinking_budget=4096) 
                    )
                )
                try:
                    result_json = json.loads(response.text)
                    summary_text = result_json.get('summary')
                    short_answer = result_json.get('short_answer') # Puede ser None o null
                    ai_filter_reason = result_json.get('ai_filter') # Puede ser string o null

                    # Validar que obtuvimos al menos el resumen
                    if not summary_text:
                        print("Error: JSON recibido no contiene 'summary' o está vacío.")
                        continue # Reintentar si el formato no es correcto

                    # Aplicar formato HTML al resumen recuperado
                    processed_summary = summary_text
                    processed_summary = re.sub(r'^\* (.+?)$', r'• <strong>\1</strong>', processed_summary, flags=re.MULTILINE)
                    processed_summary = re.sub(r'\*\*(.*?)\*\*', r'<strong>\1</strong>', processed_summary)
                    processed_summary = processed_summary.replace('\n\n', '<br><br>').replace('\n', '<br>')
                    processed_summary = processed_summary.replace('•', '<br>•')

                    # Devolver los tres resultados
                    return processed_summary, short_answer, ai_filter_reason

                except json.JSONDecodeError as json_e:
                    print(f"Error decodificando JSON de Gemini (intento {attempt + 1}): {json_e}")
                    print(f"Texto recibido: {response.text[:200]}...") # Loguear inicio de respuesta
                    if attempt == max_retries - 1:
                        print("Fallo de JSON en último intento, usando texto como resumen simple.")
                        fallback_summary = response.text.strip().replace('\n\n', '<br><br>').replace('\n', '<br>')
                        return fallback_summary, None, None # Sin filtro IA en caso de fallback
                    time.sleep(5)
                    continue

            except Exception as e:
                if ("429" in str(e) or "Resource has been exhausted" in str(e)) and attempt < max_retries - 1:
                    wait_time = (attempt + 1) * 10
                    print(f"Límite de peticiones/Recurso agotado (intento {attempt + 1}/{max_retries}). Esperando {wait_time} segundos...")
                    time.sleep(wait_time)
                    continue
                # Nuevo: Manejo específico para errores 500 INTERNAL con reintentos
                elif "500 INTERNAL" in str(e) and attempt < max_retries - 1:
                    wait_time = (attempt + 1) * 5  # Backoff exponencial, podrías ajustar el factor
                    print(f"Error interno de Gemini (500) (intento {attempt + 1}/{max_retries}). Esperando {wait_time} segundos para reintentar...")
                    time.sleep(wait_time)
                    continue
                print(f"Error procesando contenido con Gemini: {str(e)}")
                return original_content, None, None # Fallback

        print("Se agotaron los reintentos para procesar contenido.")
        return original_content, None, None # Fallback

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
            
            # Intentar decodificar explícitamente como UTF-8
            try:
                content_text = response.content.decode('utf-8')
            except UnicodeDecodeError:
                # Si UTF-8 falla, intentar con la codificación detectada por requests
                content_text = response.text 

            soup = BeautifulSoup(content_text, 'html.parser')
            
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
        # Modificamos la función para que devuelva (bool, FilterWord)
        filter_words = FilterWord.objects.filter(active=True)
        
        for filter_word in filter_words:
            # Escapar la palabra para usarla de forma segura en regex
            # No convertimos a minúsculas aquí, usamos re.IGNORECASE
            word_to_find = filter_word.word.strip()
            if not word_to_find: # Saltar si la palabra está vacía después de strip
                continue
                
            escaped_word = re.escape(word_to_find)
            # Crear el patrón regex para palabra completa, ignorando mayúsculas/minúsculas
            pattern = r'\b' + escaped_word + r'\b'
            
            # Comprobar según configuración si buscar solo en título o en todo el contenido
            if filter_word.title_only:
                # Buscar solo en el título usando regex
                if re.search(pattern, title, re.IGNORECASE):
                    return True, filter_word
            else:
                # Buscar en título y descripción usando regex
                text_to_check = f"{title} {description}"
                if re.search(pattern, text_to_check, re.IGNORECASE):
                    return True, filter_word
                    
        # Si no hay coincidencias, devolver (False, None)
        return False, None

    @staticmethod
    def fetch_and_save_news():
        print("Iniciando proceso de obtención de noticias...")
        start_time = time.time()
        
        print("Inicializando modelos...")
        # Cambiado: obtener el cliente
        gemini_client = FeedService.initialize_gemini()
        # Eliminado: Reutilizamos gemini_client para embeddings
        # embedding_model_name = EmbeddingService.initialize_embedding_model()
        
        # Obtener la configuración global del modelo Gemini
        try:
            global_gemini_setting = GeminiGlobalSetting.objects.first()
            if not global_gemini_setting:
                # Si no hay configuración, usar un valor predeterminado y crear uno
                print("Advertencia: No se encontró configuración global de Gemini. Creando una con el modelo predeterminado 'gemini-2.0-flash'.")
                global_gemini_setting = GeminiGlobalSetting.objects.create(model_name='gemini-2.0-flash')
            global_model_name = global_gemini_setting.model_name
        except Exception as e:
            print(f"Error al obtener la configuración global de Gemini: {e}. Usando 'gemini-2.0-flash' como fallback.")
            global_model_name = 'gemini-2.0-flash'
        
        sources = FeedSource.objects.filter(active=True)
        print(f"Procesando {sources.count()} fuentes activas con el modelo Gemini: {global_model_name}")
        new_articles_count = 0
        
        # Calcular la fecha límite (15 días atrás)
        fifteen_days_ago = timezone.now() - timedelta(days=15)
        
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
            
            latest_date = latest_news.published_date if latest_news else fifteen_days_ago
            
            # Usar la fecha más reciente entre la última noticia y hace 15 días
            cutoff_date = max(latest_date, fifteen_days_ago)
            
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
            
            # Validación: Saltar noticias con títulos anormalmente largos
            if len(entry.title) > 200:
                print(f"SALTANDO noticia con título muy largo ({len(entry.title)} caracteres): {entry.title[:100]}...")
                continue
                
            # Validación: Saltar noticias con GUID muy largo
            if len(guid) > 400:
                print(f"SALTANDO noticia con GUID muy largo ({len(guid)} caracteres)")
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
            # Intentar obtener descripción del feed, asegurando UTF-8 si es posible
            original_description = entry.get('description', '')
            if isinstance(original_description, bytes):
                try:
                    original_description = original_description.decode('utf-8')
                except UnicodeDecodeError:
                     # Si falla, usar una decodificación con reemplazo
                    original_description = original_description.decode('utf-8', 'replace')
            
            # Si deep_search está activado, obtener el contenido completo independientemente de la imagen
            if source.deep_search:
                full_content = FeedService.get_full_article_content(entry.link)
                if full_content['text']:
                    original_description = full_content['text']
                # Solo usar la imagen del contenido si no se encontró una en el feed
                if not image_url and full_content['image_url']:
                    image_url = full_content['image_url']

            # >>>>> ORDEN CAMBIADO: Primero filtro por PALABRA CLAVE <<<<<
            should_filter, filter_word = FeedService.should_filter_news(entry.title, original_description)
            if should_filter:
                print(f"Noticia FILTRADA por palabra clave: {filter_word.word}")
                
                # Validaciones adicionales para campos que podrían ser muy largos
                print(f"DEBUG - Longitudes: título={len(entry.title)}, guid={len(guid)}, link={len(entry.link)}")
                if hasattr(entry, 'description') and entry.description:
                    print(f"DEBUG - descripción original: {len(entry.description)} caracteres")
                print(f"DEBUG - descripción procesada: {len(original_description)} caracteres")
                
                try:
                    News.objects.create(
                        guid=guid,
                        title=entry.title,
                        short_answer=None,
                        description=original_description,
                        link=entry.link,
                        published_date=published,
                        source=source,
                        is_filtered=True,
                        filtered_by=filter_word,
                        image_url=image_url,
                        is_ai_processed=True
                    )
                    new_articles_count += 1
                except Exception as e:
                    print(f"ERROR al guardar noticia filtrada por keyword: {str(e)}")
                    print(f"Datos problemáticos:")
                    print(f"  - GUID: {guid[:100]}... (longitud: {len(guid)})")
                    print(f"  - Título: {entry.title[:100]}... (longitud: {len(entry.title)})")
                    print(f"  - Link: {entry.link[:100]}... (longitud: {len(entry.link)})")
                    print(f"  - Descripción: {original_description[:100] if original_description else 'None'}... (longitud: {len(original_description) if original_description else 0})")
                    print("SALTANDO esta noticia problemática...")
                    continue
                    
                continue # Pasar a la siguiente noticia
            # <<<<< FIN FILTRO PALABRA CLAVE >>>>>

            # Si no se filtró por palabra clave, procesar con IA
            processed_description, short_answer, ai_filter_reason = FeedService.process_content_with_gemini(
                entry.title,
                original_description,
                gemini_client,
                global_model_name # Pasar el nombre del modelo global
            )

            # >>>>> LÓGICA DE FILTRADO IA (después de palabra clave) <<<<<
            # Asegurarnos que ai_filter_reason es un string no vacío antes de usarlo
            if ai_filter_reason and isinstance(ai_filter_reason, str) and ai_filter_reason.strip():
                print(f"Noticia marcada para FILTRAR por IA. Razón: {ai_filter_reason}")
                
                try:
                    News.objects.create(
                        guid=guid,
                        title=entry.title,
                        short_answer=short_answer,
                        description=processed_description,
                        link=entry.link,
                        published_date=published,
                        source=source,
                        image_url=image_url,
                        is_filtered=True,
                        is_ai_filtered=True,
                        ai_filter_reason=ai_filter_reason.strip(),
                        is_ai_processed=True
                    )
                    new_articles_count += 1
                except Exception as e:
                    print(f"ERROR al guardar noticia filtrada por IA: {str(e)}")
                    print(f"Datos problemáticos:")
                    print(f"  - GUID: {guid[:100]}... (longitud: {len(guid)})")
                    print(f"  - Título: {entry.title[:100]}... (longitud: {len(entry.title)})")
                    print(f"  - Link: {entry.link[:100]}... (longitud: {len(entry.link)})")
                    print(f"  - AI Filter Reason: {ai_filter_reason[:100]}... (longitud: {len(ai_filter_reason)})")
                    print("SALTANDO esta noticia problemática...")
                    continue
                    
                continue # Pasar a la siguiente noticia
            elif ai_filter_reason: # Si Gemini devolvió algo pero no es un string válido
                print(f"Advertencia: Gemini devolvió un valor para ai_filter ({ai_filter_reason}) pero no es la instrucción esperada. No se filtrará.")
            # <<<<< FIN LÓGICA FILTRADO IA >>>>>

            # Guard extra: nunca crear noticias anteriores a 15 días
            if published < fifteen_days_ago:
                continue

            # Crear la nueva noticia (si no fue filtrada por IA ni por palabra)
            try:
                news_item = News.objects.create(
                    guid=guid,
                    title=entry.title,
                    short_answer=short_answer,
                    description=processed_description,
                    link=entry.link,
                    published_date=published,
                    source=source,
                    image_url=image_url,
                    is_ai_processed=bool(processed_description and processed_description != original_description)
                )
                new_articles_count += 1
            except Exception as e:
                print(f"ERROR al guardar noticia normal: {str(e)}")
                print(f"Datos problemáticos:")
                print(f"  - GUID: {guid[:100]}... (longitud: {len(guid)})")
                print(f"  - Título: {entry.title[:100]}... (longitud: {len(entry.title)})")
                print(f"  - Link: {entry.link[:100]}... (longitud: {len(entry.link)})")
                print("SALTANDO esta noticia problemática...")
                continue
            
            # Verificar redundancia (esto generará el embedding internamente si no existe)
            is_redundant, similar_news, similarity_score = EmbeddingService.check_redundancy(
                news_item, gemini_client
            )
            
            # Siempre guardar la información de similitud si se encontró una noticia similar
            if similar_news:
                news_item.similar_to = similar_news
                news_item.similarity_score = similarity_score
                # Guardamos estos campos ahora, por si no resulta redundante pero queremos la info
                news_item.save(update_fields=['similar_to', 'similarity_score']) 

            if is_redundant and similar_news:
                print(f"¡Noticia redundante detectada! Similar a: {similar_news.title}")
                print(f"Puntuación de similitud: {similarity_score:.4f} (Umbral: {news_item.source.similarity_threshold})")
                
                # Marcar como redundante y filtrada (ya hemos guardado similar_to y score)
                news_item.is_redundant = True
                news_item.is_filtered = True  # Usamos is_filtered en lugar de is_deleted
                # Guardamos todos los campos relevantes al marcar como redundante
                news_item.save(update_fields=['is_redundant', 'is_filtered'])
                
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
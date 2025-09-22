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
import textwrap
from django.conf import settings

try:
    from .vector_index import VectorIndexService, VectorIndexUnavailable
except Exception:
    VectorIndexService = None  # type: ignore
    VectorIndexUnavailable = Exception  # type: ignore

class EmbeddingService:
    @staticmethod
    def initialize_embedding_model():
        """Crea un cliente genai para usar en embeddings."""
        # Cambiado: reutilizar el cliente de FeedService para embeddings
        return FeedService.initialize_gemini()

    @staticmethod
    # Cambiado: Aceptar client en lugar de model_name
    def generate_embedding(text, client, max_retries=3):
        """Genera embeddings para un texto usando la API de Gemini a travÃ©s del cliente."""
        
        # Preprocesar el texto para tener un contenido mÃ¡s limpio
        clean_text = re.sub(r'<.*?>', ' ', text)  # Eliminar etiquetas HTML
        clean_text = re.sub(r'\s+', ' ', clean_text).strip()  # Normalizar espacios
        
        # Asegurar que el texto no sea demasiado largo
        if len(clean_text) > 8000:
            clean_text = clean_text[:8000]

        # Config por defecto para embeddings (modelo y dimensión)
        embedding_model = getattr(settings, 'GEMINI_EMBEDDING_MODEL', 'gemini-embedding-001')
        output_dim = int(getattr(settings, 'GEMINI_EMBEDDING_DIM', 768))
        
        for attempt in range(max_retries):
            try:
                # Cambiado: Usar client.models.embed_content y pasar task_type en config
                result = client.models.embed_content(
                    model=embedding_model,
                    contents=clean_text,
                    config=types.EmbedContentConfig(
                        task_type="SEMANTIC_SIMILARITY",
                        output_dimensionality=output_dim,
                    ) 
                )
                
                # Extraer los valores del embedding
                try:
                    if hasattr(result, 'embeddings') and result.embeddings:
                        first_embedding = result.embeddings[0]
                        if hasattr(first_embedding, 'values'):
                            # Normalizar L2 (recomendado para dims != 3072)
                            vec = np.array(first_embedding.values, dtype=np.float32)
                            norm = np.linalg.norm(vec)
                            if norm > 0:
                                vec = vec / norm
                            return list(map(float, vec.tolist()))
                    
                    # Fallback seguro
                    return []
                except Exception as e:
                    print(f"Error al extraer valores del embedding: {str(e)}")
                    return []
            except Exception as e:
                if "429" in str(e) and attempt < max_retries - 1:
                    wait_time = (attempt + 1) * 5  # Backoff exponencial
                    print(f"LÃ­mite de peticiones alcanzado. Esperando {wait_time} segundos...")
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
            
        # Convertir a numpy arrays para cÃ¡lculos eficientes
        vec1 = np.array(embedding1, dtype=np.float32)
        vec2 = np.array(embedding2, dtype=np.float32)
        
        # Normalizar los vectores con protección de norma 0
        n1 = np.linalg.norm(vec1)
        n2 = np.linalg.norm(vec2)
        if n1 == 0 or n2 == 0:
            return 0.0
        norm_vec1 = vec1 / n1
        norm_vec2 = vec2 / n2
        
        # Calcular similitud del coseno
        similarity = np.dot(norm_vec1, norm_vec2)
        
        return float(similarity)
    
    @staticmethod
    def check_redundancy(news_item, client, recent_news_cache=None, vector_index=None):
        """
        Verifica si una noticia es redundante comparando con las existentes

        Args:
            news_item: Objeto News que se quiere verificar
            client: Cliente genai para generar embeddings
            recent_news_cache: Lista opcional de noticias recientes ya cargadas

        Returns:
            tuple: (es_redundante, noticia_similar, puntuación_similitud)
        """
        threshold = news_item.source.similarity_threshold

        if not news_item.embedding:
            content_for_embedding = f"{news_item.title} {news_item.description}"
            news_item.embedding = EmbeddingService.generate_embedding(content_for_embedding, client)
            news_item.save(update_fields=['embedding'])

        if not news_item.embedding:
            return False, None, 0.0

        # Intentar vector DB (Qdrant) con ventana de 14 días
        try:
            if vector_index is not None and hasattr(vector_index, 'search'):
                vector_index.ensure_collection(len(news_item.embedding))
                now_ts = int(time.time())
                min_ts = now_ts - 14 * 24 * 3600
                hits = vector_index.search(
                    vector=news_item.embedding,
                    top_k=5,
                    min_published_ts=min_ts,
                    exclude_guid=getattr(news_item, 'guid', None),
                )
                if hits:
                    best = hits[0]
                    score = float(getattr(best, 'score', 0.0) or 0.0)
                    payload = getattr(best, 'payload', {}) or {}
                    similar = None
                    similar_id = payload.get('news_id')
                    if similar_id:
                        similar = News.objects.filter(id=similar_id).first()
                    if similar is None:
                        similar_guid = payload.get('guid')
                        if similar_guid:
                            similar = News.objects.filter(guid=similar_guid).first()
                    is_redundant = score >= threshold and similar is not None
                    return is_redundant, similar, score
        except Exception:
            pass

        if recent_news_cache is not None:
            candidates = [
                cached_news
                for cached_news in recent_news_cache
                if cached_news.id != getattr(news_item, 'id', None) and cached_news.embedding
            ]
        else:
            time_threshold = timezone.now() - timedelta(days=14)
            candidates = list(News.objects.filter(
                created_at__gte=time_threshold,
                is_redundant=False,
                is_filtered=False,
                embedding__isnull=False
            ).exclude(id=news_item.id))
        highest_similarity = 0.0
        most_similar_news = None

        for existing_news in candidates:
            similarity = EmbeddingService.cosine_similarity(
                news_item.embedding, existing_news.embedding
            )
            if similarity > highest_similarity:
                highest_similarity = similarity
                most_similar_news = existing_news

        is_redundant = highest_similarity >= threshold

        return is_redundant, most_similar_news, highest_similarity





class FeedService:
    _PROMPT_TEMPLATE = textwrap.dedent("""\
        Analiza el siguiente titular y contenido de noticia:
        Titular: '{title}'
        Contenido: '{content}...'

        Realiza las siguientes tareas y devuelve el resultado EXACTAMENTE en formato JSON:
        1.  **summary**: Genera un resumen conciso y objetivo del contenido completo, en español, de aproximadamente 60 a 70 palabras, eliminando clickbait y relleno, manteniendo los puntos clave. NO apliques formato HTML aquí, solo texto plano.
        2.  **short_answer**: Analiza el titular. Si el titular:
            (a) Es una pregunta directa (ej: '¿Por qué deberías...?', '¿Cuál es...?').
            O (b) NO es una pregunta directa PERO crea una fuerte expectativa de una respuesta concreta, revelación, explicación, lista, o 'secreto' que se encuentra en el contenido (ej: 'El truco definitivo para...', 'Así es como funciona X cosa...', 'La razón por la que Y sucede...', 'Descubren el motivo de Z...', 'Cinco claves para entender...', 'Lo que nadie te contó sobre...').
            Si se cumple (a) o (b), extrae o resume la respuesta/punto clave del contenido original de forma EXTREMADAMENTE CONCISA (máximo 15 palabras) y DIRECTA. No uses introducciones ni parafrasees. Si el titular NO cumple estas condiciones (es decir, es un titular informativo estándar que no genera esa expectativa específica), el valor de 'short_answer' debe ser null (JSON null).
        3.  **ai_filter**: Basándote en las siguientes instrucciones de filtrado, determina si esta noticia DEBE SER ELIMINADA. Si coincide con ALGUNA instrucción, el valor debe ser EXACTAMENTE EL TEXTO LITERAL de la instrucción que coincidió (solo una, la primera que coincida si hay varias). Si NO coincide con ninguna, el valor debe ser null (JSON null).
            Instrucciones de Filtrado:
            {instructions}

        REGLAS CRÍTICAS PARA EVITAR REDUNDANCIA:
        - Si generaste un short_answer, el summary DEBE contener información ADICIONAL y DIFERENTE que no esté en el short_answer
        - Si el short_answer ya responde la pregunta principal del titular, el summary debe profundizar en contexto, causas, consecuencias, o detalles adicionales
        - NUNCA repitas la misma información en ambos campos
        - Si toda la información relevante está en el short_answer y no hay contexto adicional útil, usa frases como: "Esta noticia no aporta información adicional más allá de lo indicado", "El contenido no aborda detalles adicionales al titular", "La noticia se limita a confirmar lo expresado en el título", etc.
        - El summary NUNCA debe ser null - siempre debe contener algún texto explicativo

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
        Ejemplo de JSON de salida esperado (clickbait pregunta directa CON contexto adicional):
        {{
          "summary": "El estudio analizó 1000 casos durante 5 años y encontró correlaciones con factores genéticos y ambientales específicos.",
          "short_answer": "La clave fue la combinación de ejercicio y dieta mediterránea.",
          "ai_filter": null
        }}
        Ejemplo de JSON de salida esperado (clickbait sin contexto adicional útil):
        {{
          "summary": "Esta noticia no aporta información adicional más allá de lo indicado en la respuesta.",
          "short_answer": "El truco es usar la técnica Pomodoro.",
          "ai_filter": null
        }}

        IMPORTANTE: Responde únicamente con el objeto JSON válido, sin texto adicional antes o después.
        """)
    _DEFAULT_FILTER_INSTRUCTIONS = "(No hay instrucciones de filtro IA activas)"

    _GEMINI_CLIENT = None
    _VECTOR_INDEX = None

    @staticmethod
    def initialize_gemini():
        if FeedService._GEMINI_CLIENT is None:
            FeedService._GEMINI_CLIENT = genai.Client()
        return FeedService._GEMINI_CLIENT

    @staticmethod
    def initialize_vector_index():
        if VectorIndexService is None:
            return None
        if FeedService._VECTOR_INDEX is not None:
            return FeedService._VECTOR_INDEX
        try:
            url = getattr(settings, 'QDRANT_URL', 'http://localhost:6333')
            collection = getattr(settings, 'QDRANT_COLLECTION', 'news_embeddings_gemini001_d768_v1')
            api_key = getattr(settings, 'QDRANT_API_KEY', None)
            FeedService._VECTOR_INDEX = VectorIndexService(url=url, collection=collection, api_key=api_key)
        except Exception:
            FeedService._VECTOR_INDEX = None
        return FeedService._VECTOR_INDEX

    @staticmethod
    def detect_redundancy(summary_text, short_answer, threshold=0.7):
        """
        Detecta si el summary y short_answer son redundantes

        Args:
            summary_text: Texto del resumen
            short_answer: Texto de la respuesta corta
            threshold: Umbral de superposición para considerar redundante (default: 0.7)

        Returns:
            bool: True si son redundantes, False si no
        """
        if not summary_text or not short_answer:
            return False

        # Normalizar y dividir en palabras
        summary_words = set(summary_text.lower().split())
        answer_words = set(short_answer.lower().split())

        # Calcular superposición
        if len(answer_words) == 0:
            return False

        overlap = len(summary_words.intersection(answer_words))
        overlap_ratio = overlap / len(answer_words)

        return overlap_ratio > threshold

    @staticmethod
    def build_filter_instructions_text(instructions):
        instructions_list = list(instructions or [])
        lines = []
        for inst in instructions_list:
            text = getattr(inst, 'instruction', None)
            if text:
                stripped = text.strip()
                if stripped:
                    lines.append(f"- {stripped}")
        return "\n".join(lines) if lines else FeedService._DEFAULT_FILTER_INSTRUCTIONS

    @staticmethod
    def build_filter_word_patterns(filter_words):
        patterns = []
        for filter_word in filter_words:
            raw_word = getattr(filter_word, 'word', '')
            cleaned_word = raw_word.strip() if raw_word else ''
            if not cleaned_word:
                continue
            compiled = re.compile(r'\b' + re.escape(cleaned_word) + r'\b', re.IGNORECASE)
            patterns.append((filter_word, compiled, bool(getattr(filter_word, 'title_only', False))))
        return patterns

    @staticmethod
    def process_content_with_gemini(title, original_content, client, global_gemini_model_name, filter_instructions_text, max_retries=3):
        """Genera el resumen principal, la respuesta corta y determina si debe filtrarse por IA."""

        instructions_section = (filter_instructions_text or FeedService._DEFAULT_FILTER_INSTRUCTIONS)
        content_limit = 4000
        base_content = (original_content or "")[:content_limit]

        safe_title = (title or "").replace("{", "{{").replace("}", "}}")
        safe_content = base_content.replace("{", "{{").replace("}", "}}")
        safe_instructions = instructions_section.replace("{", "{{").replace("}", "}}")

        prompt = FeedService._PROMPT_TEMPLATE.format(
            title=safe_title,
            content=safe_content,
            instructions=safe_instructions
        )

        for attempt in range(max_retries):
            try:
                response = client.models.generate_content(
                    model=global_gemini_model_name,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        response_mime_type="application/json",
                        thinking_config=types.ThinkingConfig(thinking_budget=4096)
                    )
                )
                try:
                    result_json = json.loads(response.text)
                    summary_text = result_json.get('summary')
                    short_answer = result_json.get('short_answer')
                    ai_filter_reason = result_json.get('ai_filter')

                    # Validación de redundancia post-procesamiento
                    if FeedService.detect_redundancy(summary_text, short_answer):
                        print("Detectada redundancia entre summary y short_answer. Reemplazando con mensaje explicativo.")
                        summary_text = "Esta noticia no aporta información adicional más allá de lo indicado en la respuesta anterior."

                    # Si no hay summary pero sí hay short_answer, generar mensaje explicativo
                    if not summary_text and short_answer:
                        summary_text = "El contenido no aborda detalles adicionales al titular."
                    elif not summary_text and not short_answer:
                        print("Error: JSON recibido no contiene 'summary' ni 'short_answer' válidos.")
                        continue

                    processed_summary = summary_text
                    processed_summary = re.sub(r'^\* (.+?)$', r' <strong>\1</strong>', processed_summary, flags=re.MULTILINE)
                    processed_summary = re.sub(r'\*\*(.*?)\*\*', r'<strong>\1</strong>', processed_summary)
                    processed_summary = processed_summary.replace('\n\n', '<br><br>').replace('\n', '<br>')
                    processed_summary = processed_summary.replace('', '<br>')

                    return processed_summary, short_answer, ai_filter_reason

                except json.JSONDecodeError as json_e:
                    print(f"Error decodificando JSON de Gemini (intento {attempt + 1}): {json_e}")
                    print(f"Texto recibido: {response.text[:200]}...")
                    if attempt == max_retries - 1:
                        print("Fallo de JSON en ï¿½ltimo intento, usando texto como resumen simple.")
                        fallback_summary = response.text.strip().replace('\n\n', '<br><br>').replace('\n', '<br>')
                        return fallback_summary, None, None
                    time.sleep(5)
                    continue

            except Exception as e:
                if ("429" in str(e) or "Resource has been exhausted" in str(e)) and attempt < max_retries - 1:
                    wait_time = (attempt + 1) * 10
                    print(f"Lï¿½mite de peticiones/Recurso agotado (intento {attempt + 1}/{max_retries}). Esperando {wait_time} segundos...")
                    time.sleep(wait_time)
                    continue
                elif "500 INTERNAL" in str(e) and attempt < max_retries - 1:
                    wait_time = (attempt + 1) * 5
                    print(f"Error interno de Gemini (500) (intento {attempt + 1}/{max_retries}). Esperando {wait_time} segundos para reintentar...")
                    time.sleep(wait_time)
                    continue
                print(f"Error procesando contenido con Gemini: {str(e)}")
                return original_content, None, None

        print("Se agotaron los reintentos para procesar contenido.")
        return original_content, None, None

    @staticmethod
    def extract_image_from_description(description):
        # Buscar una URL de imagen en el HTML de la descripciÃ³n
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
            
            # Intentar decodificar explÃ­citamente como UTF-8
            try:
                content_text = response.content.decode('utf-8')
            except UnicodeDecodeError:
                # Si UTF-8 falla, intentar con la codificaciÃ³n detectada por requests
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
                
                # Si no encontramos imagen en el contenido principal, buscar en todo el artÃ­culo
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
    def should_filter_news(title, description, filter_word_patterns):
        if not filter_word_patterns:
            return False, None

        safe_title = title or ""
        safe_description = description or ""

        for filter_word, pattern, title_only in filter_word_patterns:
            if title_only:
                if pattern.search(safe_title):
                    return True, filter_word
            else:
                if pattern.search(safe_title) or pattern.search(safe_description):
                    return True, filter_word

        return False, None

    @staticmethod
    def fetch_and_save_news():
        print("Iniciando proceso de obtenciÃ³n de noticias...")
        start_time = time.time()
        
        print("Inicializando modelos...")
        # Cambiado: obtener el cliente
        gemini_client = FeedService.initialize_gemini()
        vector_index = FeedService.initialize_vector_index()
        # Eliminado: Reutilizamos gemini_client para embeddings
        # embedding_model_name = EmbeddingService.initialize_embedding_model()
        
        # Obtener la configuraciÃ³n global del modelo Gemini
        try:
            global_gemini_setting = GeminiGlobalSetting.objects.first()
            if not global_gemini_setting:
                # Si no hay configuraciÃ³n, usar un valor predeterminado y crear uno
                print("Advertencia: No se encontrÃ³ configuraciÃ³n global de Gemini. Creando una con el modelo predeterminado 'gemini-2.0-flash'.")
                global_gemini_setting = GeminiGlobalSetting.objects.create(model_name='gemini-2.0-flash')
            global_model_name = global_gemini_setting.model_name
        except Exception as e:
            print(f"Error al obtener la configuraciÃ³n global de Gemini: {e}. Usando 'gemini-2.0-flash' como fallback.")
            global_model_name = 'gemini-2.0-flash'
        
        filter_word_patterns = FeedService.build_filter_word_patterns(
            FilterWord.objects.filter(active=True)
        )
        filter_instructions_text = FeedService.build_filter_instructions_text(
            AIFilterInstruction.objects.filter(active=True)
        )

        sources = FeedSource.objects.filter(active=True)
        print(f"Procesando {sources.count()} fuentes activas con el modelo Gemini: {global_model_name}")
        new_articles_count = 0
        
        # Calcular la fecha lÃ­mite (15 dÃ­as atrÃ¡s)
        fifteen_days_ago = timezone.now() - timedelta(days=15)
        redundancy_window = timezone.now() - timedelta(days=14)
        recent_news_cache = list(
            News.objects.filter(
                created_at__gte=redundancy_window,
                is_redundant=False,
                is_filtered=False,
                embedding__isnull=False
            ).select_related('source')
        )

        existing_guids = set(
            News.objects.filter(published_date__gte=fifteen_days_ago).values_list('guid', flat=True)
        )

        
        # Lista para almacenar todas las entradas de todas las fuentes
        all_entries = []
        
        # Primero, recolectar todas las entradas de todas las fuentes
        for source in sources:
            print(f"\nRecolectando entradas de fuente: {source.name}")
            
            # Obtener la fecha de la Ãºltima noticia para esta fuente
            latest_news = News.objects.filter(
                source=source,
                is_deleted=False,
                is_filtered=False
            ).order_by('-published_date').first()
            
            latest_date = latest_news.published_date if latest_news else fifteen_days_ago
            
            # Usar la fecha mÃ¡s reciente entre la Ãºltima noticia y hace 15 dÃ­as
            cutoff_date = max(latest_date, fifteen_days_ago)
            
            feed = feedparser.parse(source.url)
            print(f"Encontradas {len(feed.entries)} entradas en el feed")
            
            # Recolectar entradas vÃ¡lidas
            for entry in feed.entries:
                # Convertir la fecha de publicaciÃ³n
                if hasattr(entry, 'published_parsed') and entry.published_parsed:
                    # Crear fecha en UTC (los feeds generalmente usan UTC como estÃ¡ndar)
                    published_utc = datetime(*entry.published_parsed[:6])
                    if timezone.is_naive(published_utc):
                        published_utc = timezone.make_aware(published_utc, timezone=pytz.UTC)
                    
                    # Convertir a la zona horaria del proyecto
                    published = published_utc.astimezone(timezone.get_current_timezone())
                else:
                    published = timezone.now()
                
                # Si la noticia es mÃ¡s antigua que el lÃ­mite, la saltamos
                if published < cutoff_date:
                    continue
                
                # Verificar si la noticia ya existe
                guid = entry.get('id', entry.link)
                if guid in existing_guids:
                    continue

                existing_guids.add(guid)

                # Agregar la entrada a la lista con su fuente y fecha
                all_entries.append({
                    'entry': entry,
                    'source': source,
                    'published': published,
                    'guid': guid
                })
        
                # Ordenar todas las entradas de más antigua a más reciente para procesamiento estable
        all_entries.sort(key=lambda x: x['published'])
        print(f"\nSe recolectaron {len(all_entries)} nuevas entradas de todas las fuentes")

        # Contador para noticias redundantes
        redundant_count = 0
        
        # Procesar todas las entradas en orden (de mÃ¡s antigua a mÃ¡s reciente)
        for item in all_entries:
            entry = item['entry']
            source = item['source']
            published = item['published']
            guid = item['guid']
            
            print(f"\nProcesando entrada: {entry.title} ({published})")
            
            # ValidaciÃ³n: Saltar noticias con tÃ­tulos anormalmente largos
            if len(entry.title) > 200:
                print(f"SALTANDO noticia con tÃ­tulo muy largo ({len(entry.title)} caracteres): {entry.title[:100]}...")
                continue
                
            # ValidaciÃ³n: Saltar noticias con GUID muy largo
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

            # 3. Buscar en la descripciÃ³n
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
            # Intentar obtener descripciÃ³n del feed, asegurando UTF-8 si es posible
            original_description = entry.get('description', '')
            if isinstance(original_description, bytes):
                try:
                    original_description = original_description.decode('utf-8')
                except UnicodeDecodeError:
                     # Si falla, usar una decodificaciÃ³n con reemplazo
                    original_description = original_description.decode('utf-8', 'replace')
            
            # Si deep_search estÃ¡ activado, obtener el contenido completo independientemente de la imagen
            if source.deep_search:
                full_content = FeedService.get_full_article_content(entry.link)
                if full_content['text']:
                    original_description = full_content['text']
                # Solo usar la imagen del contenido si no se encontrÃ³ una en el feed
                if not image_url and full_content['image_url']:
                    image_url = full_content['image_url']

            # >>>>> ORDEN CAMBIADO: Primero filtro por PALABRA CLAVE <<<<<
            should_filter, filter_word = FeedService.should_filter_news(entry.title, original_description, filter_word_patterns)
            if should_filter:
                print(f"Noticia FILTRADA por palabra clave: {filter_word.word}")
                
                # Validaciones adicionales para campos que podrÃ­an ser muy largos
                print(f"DEBUG - Longitudes: tÃ­tulo={len(entry.title)}, guid={len(guid)}, link={len(entry.link)}")
                if hasattr(entry, 'description') and entry.description:
                    print(f"DEBUG - descripciÃ³n original: {len(entry.description)} caracteres")
                print(f"DEBUG - descripciÃ³n procesada: {len(original_description)} caracteres")
                
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
                    print(f"Datos problemÃ¡ticos:")
                    print(f"  - GUID: {guid[:100]}... (longitud: {len(guid)})")
                    print(f"  - TÃ­tulo: {entry.title[:100]}... (longitud: {len(entry.title)})")
                    print(f"  - Link: {entry.link[:100]}... (longitud: {len(entry.link)})")
                    print(f"  - DescripciÃ³n: {original_description[:100] if original_description else 'None'}... (longitud: {len(original_description) if original_description else 0})")
                    print("SALTANDO esta noticia problemÃ¡tica...")
                    continue
                    
                continue # Pasar a la siguiente noticia
            # <<<<< FIN FILTRO PALABRA CLAVE >>>>>

            # Si no se filtrÃ³ por palabra clave, procesar con IA
            processed_description, short_answer, ai_filter_reason = FeedService.process_content_with_gemini(
                entry.title,
                original_description,
                gemini_client,
                global_model_name,
                filter_instructions_text # Pasar las instrucciones ya precargadas
            )

            # >>>>> LÃGICA DE FILTRADO IA (despuÃ©s de palabra clave) <<<<<
            # Asegurarnos que ai_filter_reason es un string no vacÃ­o antes de usarlo
            if ai_filter_reason and isinstance(ai_filter_reason, str) and ai_filter_reason.strip():
                print(f"Noticia marcada para FILTRAR por IA. RazÃ³n: {ai_filter_reason}")
                
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
                    print(f"Datos problemÃ¡ticos:")
                    print(f"  - GUID: {guid[:100]}... (longitud: {len(guid)})")
                    print(f"  - TÃ­tulo: {entry.title[:100]}... (longitud: {len(entry.title)})")
                    print(f"  - Link: {entry.link[:100]}... (longitud: {len(entry.link)})")
                    print(f"  - AI Filter Reason: {ai_filter_reason[:100]}... (longitud: {len(ai_filter_reason)})")
                    print("SALTANDO esta noticia problemÃ¡tica...")
                    continue
                    
                continue # Pasar a la siguiente noticia
            elif ai_filter_reason: # Si Gemini devolviÃ³ algo pero no es un string vÃ¡lido
                print(f"Advertencia: Gemini devolviÃ³ un valor para ai_filter ({ai_filter_reason}) pero no es la instrucciÃ³n esperada. No se filtrarÃ¡.")
            # <<<<< FIN LÃGICA FILTRADO IA >>>>>

            # Guard extra: nunca crear noticias anteriores a 15 dÃ­as
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
                print(f"Datos problemÃ¡ticos:")
                print(f"  - GUID: {guid[:100]}... (longitud: {len(guid)})")
                print(f"  - TÃ­tulo: {entry.title[:100]}... (longitud: {len(entry.title)})")
                print(f"  - Link: {entry.link[:100]}... (longitud: {len(entry.link)})")
                print("SALTANDO esta noticia problemÃ¡tica...")
                continue
            
            # Verificar redundancia (esto generarÃ¡ el embedding internamente si no existe)
            is_redundant, similar_news, similarity_score = EmbeddingService.check_redundancy(
                news_item, gemini_client, recent_news_cache, vector_index
            )
            
            # Siempre guardar la informaciÃ³n de similitud si se encontrÃ³ una noticia similar
            if similar_news:
                news_item.similar_to = similar_news
                news_item.similarity_score = similarity_score
                # Guardamos estos campos ahora, por si no resulta redundante pero queremos la info
                news_item.save(update_fields=['similar_to', 'similarity_score']) 

            if is_redundant and similar_news:
                print(f"Â¡Noticia redundante detectada! Similar a: {similar_news.title}")
                print(f"PuntuaciÃ³n de similitud: {similarity_score:.4f} (Umbral: {news_item.source.similarity_threshold})")
                
                # Marcar como redundante y filtrada (ya hemos guardado similar_to y score)
                news_item.is_redundant = True
                news_item.is_filtered = True  # Usamos is_filtered en lugar de is_deleted
                # Guardamos todos los campos relevantes al marcar como redundante
                news_item.save(update_fields=['is_redundant', 'is_filtered'])
                
                redundant_count += 1
            if not is_redundant and news_item.embedding:
                recent_news_cache.append(news_item)
                # Indexar en Qdrant (si está disponible) para futuras búsquedas
                if vector_index is not None:
                    try:
                        vector_index.ensure_collection(len(news_item.embedding))
                        published_ts = int(news_item.published_date.timestamp()) if news_item.published_date else int(time.time())
                        payload = {
                            'news_id': news_item.id,
                            'source_id': news_item.source_id,
                            'published_ts': published_ts,
                            'is_filtered': False,
                            'is_redundant': False,
                            'model_version': getattr(settings, 'GEMINI_EMBEDDING_MODEL', 'gemini-embedding-001'),
                        }
                        vector_index.upsert(news_item.guid, news_item.embedding, payload)
                    except Exception:
                        pass

        
        # Actualizar la fecha de Ãºltima obtenciÃ³n para todas las fuentes
        for source in sources:
            source.last_fetch = timezone.now()
            source.save()
            print(f"Actualizada fecha de Ãºltima obtenciÃ³n para {source.name}")
        
        total_time = time.time() - start_time
        print(f"\nProceso completado en {total_time:.2f} segundos")
        print(f"Total de nuevas noticias: {new_articles_count}")
        print(f"Noticias redundantes eliminadas: {redundant_count}")
        
        return new_articles_count 

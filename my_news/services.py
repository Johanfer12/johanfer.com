import feedparser
from datetime import datetime, timedelta, timezone as dt_timezone
from django.utils import timezone
import pytz
from .models import News, FeedSource, FilterWord, AIFilterInstruction, AIModelSetting
import re
# google-genai y qdrant se importan dentro de las funciones que los usan:
# entre los dos son ~10 s y ~155 MB en la Pi, y el proceso web que sirve el feed
# no llama a ninguno. Solo los necesitan la ingesta y los comandos.
import time
import requests
import os
from bs4 import BeautifulSoup
from urllib.parse import urljoin
import numpy as np
from django.db.models import Max
import hashlib
import json
import textwrap
import html
import logging
from django.conf import settings
from Bookshelf.html_sanitizer import sanitize_html
from .ingestion_status import report_ok, report_paused
from .ai_providers import (
    AIProviderError,
    DEFAULT_MODELS,
    DEFAULT_PROVIDER,
    cadena_de_proveedores,
)

try:
    from .vector_index import VectorIndexService, VectorIndexUnavailable
except Exception:
    VectorIndexService = None  # type: ignore
    VectorIndexUnavailable = Exception  # type: ignore


logger = logging.getLogger(__name__)

# Modelo de IA por defecto para resúmenes; el valor activo vive en la BD
# (AIModelSetting, editable desde el admin) y este es solo el fallback.
DEFAULT_AI_MODEL = DEFAULT_MODELS[DEFAULT_PROVIDER]
DEFAULT_AI_CONTENT_LIMIT = 10_000

# Cuánto atrás se busca un duplicado. Los vectores viven esta ventana completa
# aunque la noticia se purgue a los 15 días: comparar sale barato (medido en la
# Pi, 28.000 puntos cuestan 25 ms por búsqueda con el índice puesto) y guardar
# 55.000 filas de noticias en SQLite, no.
REDUNDANCY_WINDOW_DAYS = 365

# Dentro de estos días vale el umbral de la fuente (0,85), que es donde se
# calibró. Más atrás se exige LONG_WINDOW_THRESHOLD.
RECENT_WINDOW_DAYS = 15

# Umbral para el tramo largo. Medido sobre republicaciones reales de Gizmodo:
# los duplicados de verdad puntúan entre 0,93 y 0,95, mientras que el percentil
# 99,9 del ruido entre noticias distintas es 0,82. Con 0,85 y un año de
# candidatos, el 29% de las noticias tendría algún vecino por encima por puro
# azar; con 0,92 se queda en el 3% y sigue cazando las republicaciones.
LONG_WINDOW_THRESHOLD = 0.92


class EmbeddingService:
    # Cuántos textos van en cada petición de embeddings. La API los acepta en
    # lista; el límite práctico lo pone el tamaño de la petición, no la cuota.
    EMBEDDING_BATCH_SIZE = 32

    @staticmethod
    def _clean_for_embedding(text):
        """Limpia y recorta un texto igual para la vía unitaria y la de lote."""
        clean_text = re.sub(r'<.*?>', ' ', text or '')  # Eliminar etiquetas HTML
        clean_text = re.sub(r'\s+', ' ', clean_text).strip()  # Normalizar espacios
        if len(clean_text) > 8000:
            clean_text = clean_text[:8000]
        return clean_text

    @staticmethod
    def _normalize(values):
        """Normaliza L2 (recomendado para dims != 3072)."""
        vec = np.array(values, dtype=np.float32)
        norm = np.linalg.norm(vec)
        if norm > 0:
            vec = vec / norm
        return list(map(float, vec.tolist()))

    @staticmethod
    def generate_embeddings_batch(texts, client, max_retries=3):
        """Genera los embeddings de varios textos en una sola petición.

        Pedirlos de uno en uno costaba 0,31 s por noticia medidos en la Pi;
        en lote son 0,05 s, o sea 10,8 s frente a 1,7 s en una pasada de 35
        noticias. Y lo que más pesa no es el tiempo: gasta **una** petición de
        cuota en lugar de 35.

        Devuelve una lista del mismo largo que ``texts``; cada hueco lleva el
        vector o ``None`` si esa posición no se pudo resolver. Si el lote
        entero falla se cae a la vía de uno en uno, para que un solo texto
        problemático no tumbe a los demás.
        """
        if not texts:
            return []

        from google.genai import types

        embedding_model = getattr(settings, 'GEMINI_EMBEDDING_MODEL', 'gemini-embedding-001')
        output_dim = int(getattr(settings, 'GEMINI_EMBEDDING_DIM', 768))
        config = types.EmbedContentConfig(
            task_type="SEMANTIC_SIMILARITY",
            output_dimensionality=output_dim,
        )

        limpios = [EmbeddingService._clean_for_embedding(t) for t in texts]
        resultados = [None] * len(limpios)
        tam = EmbeddingService.EMBEDDING_BATCH_SIZE

        for inicio in range(0, len(limpios), tam):
            trozo = limpios[inicio:inicio + tam]
            posiciones = [
                i for i, texto in enumerate(trozo, start=inicio) if limpios[i]
            ]
            contenidos = [limpios[i] for i in posiciones]
            if not contenidos:
                continue

            vectores = None
            for attempt in range(max_retries):
                try:
                    respuesta = client.models.embed_content(
                        model=embedding_model,
                        contents=contenidos,
                        config=config,
                    )
                    devueltos = getattr(respuesta, 'embeddings', None) or []
                    if len(devueltos) != len(contenidos):
                        # Sin correspondencia posición a posición no se puede
                        # saber qué vector es de qué noticia: mejor rehacerlo
                        # de uno en uno que arriesgarse a cruzarlos.
                        logger.warning(
                            "El lote de embeddings devolvió %s vectores para %s textos.",
                            len(devueltos), len(contenidos),
                        )
                        break
                    vectores = [
                        EmbeddingService._normalize(e.values)
                        if getattr(e, 'values', None) else None
                        for e in devueltos
                    ]
                    break
                except Exception as exc:
                    if "429" in str(exc) and attempt < max_retries - 1:
                        wait_time = (attempt + 1) * 5
                        logger.warning(
                            "Límite de peticiones alcanzado en el lote de embeddings. "
                            "Esperando %s segundos...", wait_time
                        )
                        time.sleep(wait_time)
                        continue
                    logger.exception("Error generando el lote de embeddings")
                    break

            if vectores is None:
                # Respaldo: uno a uno, que es lo que se hacía siempre.
                for i in posiciones:
                    resultados[i] = EmbeddingService.generate_embedding(
                        limpios[i], client, max_retries=max_retries
                    )
                continue

            for i, vector in zip(posiciones, vectores):
                resultados[i] = vector

        return resultados

    @staticmethod
    # Cambiado: Aceptar client en lugar de model_name
    def generate_embedding(text, client, max_retries=3):
        """Genera embeddings para un texto usando la API de Gemini a través del cliente."""

        clean_text = EmbeddingService._clean_for_embedding(text)

        # Config por defecto para embeddings (modelo y dimensión)
        # El import va aqui por lo mismo que en initialize_gemini: fuera de la
        # ingesta nadie pide embeddings, y arriba lo pagaba cada arranque web.
        from google.genai import types

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
                            return EmbeddingService._normalize(first_embedding.values)


                    # Fallback seguro
                    return []
                except Exception:
                    logger.exception("Error al extraer valores del embedding")
                    return []
            except Exception as e:
                if "429" in str(e) and attempt < max_retries - 1:
                    wait_time = (attempt + 1) * 5  # Backoff exponencial
                    logger.warning(f"Límite de peticiones alcanzado. Esperando {wait_time} segundos...")
                    time.sleep(wait_time)
                    continue
                logger.exception("Error generando embedding")
                return None
        
        logger.warning("Se agotaron los reintentos para generar embedding.")
        return None

    @staticmethod
    def cosine_similarity(embedding1, embedding2):
        """Calcula la similitud del coseno entre dos embeddings"""
        if not embedding1 or not embedding2:
            return 0.0
            
        # Convertir a numpy arrays para cálculos eficientes
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

        embedding = getattr(news_item, "_embedding_vector", None)
        if embedding is None and getattr(news_item, "_embedding_attempted", False):
            # Ya se intentó (en el lote previo) y no salió: no reintentarlo por
            # noticia, que es justo lo que el lote venía a evitar.
            return False, None, 0.0
        if not embedding:
            content_for_embedding = f"{news_item.title} {news_item.description}"
            embedding = EmbeddingService.generate_embedding(content_for_embedding, client)
            news_item._embedding_vector = embedding

        if not embedding:
            return False, None, 0.0

        # Vector DB (Qdrant) con la ventana larga y umbral por tramo.
        try:
            if vector_index is not None and hasattr(vector_index, 'search'):
                vector_index.ensure_collection(len(embedding))
                now_ts = int(time.time())
                min_ts = now_ts - REDUNDANCY_WINDOW_DAYS * 24 * 3600
                frontera_reciente = now_ts - RECENT_WINDOW_DAYS * 24 * 3600
                hits = vector_index.search(
                    vector=embedding,
                    top_k=5,
                    min_published_ts=min_ts,
                    exclude_guid=getattr(news_item, 'guid', None),
                    # Solo vectores del mismo modelo. El payload guardaba
                    # `model_version` desde siempre y nadie lo miraba: dos
                    # modelos de las mismas dimensiones producen vectores
                    # incomparables, y compararlos da puntuaciones sin
                    # sentido sin que nada falle. Con la ventana en 15 días
                    # la mezcla se limpiaba sola; con un año se arrastraría
                    # doce meses.
                    extra_must=vector_index.same_model_condition(),
                )
                if hits:
                    mejor_puntuacion = 0.0
                    mejor_similar = None
                    mejor_payload = None
                    duplicado = None

                    # Se recorren todos los aciertos y no solo el primero: cada
                    # uno se juzga con el umbral de SU tramo, así que el más
                    # parecido no tiene por qué ser el que cruza su listón.
                    for hit in hits:
                        score = float(getattr(hit, 'score', 0.0) or 0.0)
                        payload = getattr(hit, 'payload', {}) or {}
                        publicado = payload.get('published_ts') or 0
                        umbral_hit = (
                            threshold if publicado >= frontera_reciente
                            else LONG_WINDOW_THRESHOLD
                        )
                        if score > mejor_puntuacion:
                            mejor_puntuacion = score
                            mejor_payload = payload
                        if score >= umbral_hit and duplicado is None:
                            duplicado = (score, payload)

                    elegido = duplicado[1] if duplicado else mejor_payload
                    puntuacion = duplicado[0] if duplicado else mejor_puntuacion

                    similar = None
                    if elegido:
                        similar_id = elegido.get('news_id')
                        if similar_id:
                            similar = News.objects.filter(id=similar_id).first()
                        if similar is None:
                            similar_guid = elegido.get('guid')
                            if similar_guid:
                                similar = News.objects.filter(guid=similar_guid).first()
                        mejor_similar = similar

                    # Con la ventana a un año el vector sobrevive a la noticia,
                    # que se purga a los 15 días. Que la fila ya no exista no
                    # hace menos duplicada a la nueva: se marca igual y el
                    # titular del original queda anotado desde el payload para
                    # poder revisarlo en el admin.
                    if duplicado:
                        news_item._similar_ref = FeedService.describe_vector_payload(elegido)
                        return True, mejor_similar, puntuacion

                    return False, mejor_similar, puntuacion
        except Exception:
            logger.exception("Error consultando Qdrant en check_redundancy; se usa el fallback en memoria.")

        if recent_news_cache is not None:
            candidates = [
                cached_news
                for cached_news in recent_news_cache
                if cached_news.id != getattr(news_item, 'id', None)
                and getattr(cached_news, "_embedding_vector", None)
            ]
        else:
            candidates = []
        highest_similarity = 0.0
        most_similar_news = None

        for existing_news in candidates:
            similarity = EmbeddingService.cosine_similarity(
                embedding, getattr(existing_news, "_embedding_vector", None)
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
        1.  **summary**: Genera un resumen conciso y objetivo del contenido completo, en español, de aproximadamente 60 a 70 palabras. Explica qué ocurrió, quiénes participaron, dónde/cuándo, causas, consecuencias o cifras relevantes. El summary debe añadir contexto nuevo respecto al titular y al short_answer, evitando cualquier tono de clickbait. NO apliques formato HTML aquí, solo texto plano.
        2.  **short_answer**: Analiza el titular. Este campo NO es un resumen decorativo; es una respuesta anti-clickbait. Si el titular:
            (a) Es una pregunta directa (ej: '¿Por qué deberías...?', '¿Cuál es...?').
            O (b) NO es una pregunta directa PERO crea una fuerte expectativa de una respuesta concreta, revelación, explicación, lista, o 'secreto' que se encuentra en el contenido (ej: 'El truco definitivo para...', 'Así es como funciona X cosa...', 'La razón por la que Y sucede...', 'Descubren el motivo de Z...', 'Cinco claves para entender...', 'Lo que nadie te contó sobre...', 'Este juego me envició todo el día').
            Si se cumple (a) o (b), extrae la respuesta/punto clave del contenido original de forma EXTREMADAMENTE CONCISA (máximo 15 palabras) y DIRECTA. Menciona explícitamente el dato, nombre, lugar o cifra que el titular deja sin revelar. Nunca repitas ni parafrasees el titular; revela la información concreta (por ejemplo: "Terraria se convirtió en el juego favorito del autor"). Si el titular ya entrega el hecho principal, lugar, cifra o conclusión, el valor de 'short_answer' debe ser null (JSON null). Si solo puedes escribir una frase que repite, resume o reordena el titular, el valor de 'short_answer' debe ser null.
        3.  **ai_filter**: Basándote en las siguientes instrucciones de filtrado, determina si esta noticia DEBE SER ELIMINADA. Si coincide con ALGUNA instrucción, el valor debe ser EXACTAMENTE EL TEXTO LITERAL de la instrucción que coincidió (solo una, la primera que coincida si hay varias). Si NO coincide con ninguna, el valor debe ser null (JSON null).
            Instrucciones de Filtrado:
            {instructions}

        REGLAS CLAVE PARA RESUMEN Y SHORT_ANSWER:
        - Ni el summary ni el short_answer pueden repetir literal el titular; cada uno debe aportar información nueva.
        - Genera short_answer SOLO cuando el titular oculte una respuesta concreta. Titulares descriptivos o informativos NO deben tener short_answer.
        - No uses short_answer para añadir un dato menor si el titular no es clickbait. En ese caso debe ser null.
        - Si generas un short_answer, el summary DEBE contener información adicional y diferente (contexto, causas, efectos, antecedentes, reacciones, cifras, etc.).
        - El short_answer siempre debe revelar el elemento que el titular oculta o promete, mencionando explícitamente nombres, resultados o respuestas concretas.
        - Ambos campos deben ser complementarios y libres de relleno o frases ambiguas; evita cualquier forma de clickbait.
        - El summary NUNCA debe ser null: describe lo ocurrido incluso si el short_answer ya dio el dato principal.

        Ejemplo del formato de salida:
        {{"summary": "Texto del resumen aquí.", "short_answer": null, "ai_filter": null}}

        IMPORTANTE: Responde únicamente con el objeto JSON válido, sin texto adicional antes o después.
        """)
    _DEFAULT_FILTER_INSTRUCTIONS = "(No hay instrucciones de filtro IA activas)"
    _NEWS_ANALYSIS_RESPONSE_FORMAT = {
        "type": "json_schema",
        "json_schema": {
            "name": "news_analysis",
            "strict": True,
            "schema": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "summary": {"type": "string"},
                    "short_answer": {"type": ["string", "null"]},
                    "ai_filter": {"type": ["string", "null"]},
                },
                "required": ["summary", "short_answer", "ai_filter"],
            },
        },
    }

    _GEMINI_CLIENT = None
    # Último fallo al hablar con la IA, para poder explicarlo en el feed en vez
    # de dejar solo un feed que no crece. Lo consume fetch_and_save_news al
    # pausar la ingesta; se limpia en cuanto una llamada vuelve a funcionar.
    _LAST_AI_FAILURE = None
    _VECTOR_INDEX = None

    @staticmethod
    def initialize_gemini():
        """Cliente Gemini - solo para embeddings"""
        if FeedService._GEMINI_CLIENT is None:
            api_key = getattr(settings, 'GOOGLE_API_KEY', None) or os.environ.get('GOOGLE_API_KEY')
            if not api_key:
                raise ValueError("GOOGLE_API_KEY no configurada. Agrégala en settings.py o como variable de entorno.")
            from google import genai
            FeedService._GEMINI_CLIENT = genai.Client(api_key=api_key)
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
    def build_vector_payload(news_item):
        """Payload de Qdrant para una noticia indexable.

        Los flags van a False a propósito: solo se indexan noticias que pasaron
        los filtros, y ``VectorIndexService.search`` los exige así.
        """
        published_ts = (
            int(news_item.published_date.timestamp())
            if news_item.published_date
            else int(time.time())
        )
        return {
            'news_id': news_item.id,
            'source_id': news_item.source_id,
            'published_ts': published_ts,
            'is_filtered': False,
            'is_redundant': False,
            'model_version': getattr(settings, 'GEMINI_EMBEDDING_MODEL', 'gemini-embedding-001'),
            # El titular viaja en el payload porque el vector sobrevive a la
            # fila: sin esto, un duplicado de hace meses se marcaría sin poder
            # decir de qué es duplicado. Va en disco (on_disk_payload), así que
            # no ocupa memoria.
            'title': (news_item.title or '')[:300],
            'link': (news_item.link or '')[:500],
        }

    @staticmethod
    def describe_vector_payload(payload):
        """Texto legible del original de un duplicado, para el admin.

        Se usa cuando la noticia original ya se purgó y no hay fila a la que
        apuntar con ``similar_to``.
        """
        if not payload:
            return ''
        titulo = (payload.get('title') or '').strip()
        enlace = (payload.get('link') or '').strip()
        publicado = payload.get('published_ts')
        fecha = ''
        if publicado:
            try:
                fecha = datetime.fromtimestamp(
                    int(publicado), tz=dt_timezone.utc
                ).strftime('%Y-%m-%d')
            except (TypeError, ValueError, OSError):
                fecha = ''
        partes = [p for p in (fecha, titulo) if p]
        descripcion = ' · '.join(partes) if partes else (payload.get('guid') or '')
        if enlace:
            descripcion = f"{descripcion} ({enlace})" if descripcion else enlace
        return descripcion[:600]

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
            escaped_terms = [re.escape(term) for term in cleaned_word.split()]
            escaped_phrase = r'\s+'.join(escaped_terms)
            compiled = re.compile(
                r'(?<![\w])' + escaped_phrase + r'(?![\w])',
                re.IGNORECASE,
            )
            patterns.append((filter_word, compiled, bool(getattr(filter_word, 'title_only', False))))
        return patterns

    @staticmethod
    def _note_ai_failure(kind, reason, detail='', retry_seconds=None):
        """Anota por qué falló la IA, en términos que se puedan leer en el feed."""
        FeedService._LAST_AI_FAILURE = {
            'kind': kind,
            'reason': reason,
            'detail': (detail or '')[:2000],
            'retry_seconds': retry_seconds,
        }

    @staticmethod
    def _clear_ai_failure():
        FeedService._LAST_AI_FAILURE = None

    @staticmethod
    def _parse_model_json(response_text):
        """Parsea JSON aunque el modelo haya agregado texto antes o despues."""
        def scan(text):
            try:
                result = json.loads(text)
                if isinstance(result, dict):
                    return [result]
            except json.JSONDecodeError:
                pass

            decoder = json.JSONDecoder()
            found = []
            for match in re.finditer(r'\{', text):
                try:
                    result, _ = decoder.raw_decode(text, match.start())
                except json.JSONDecodeError:
                    continue
                if isinstance(result, dict) and {'summary', 'short_answer', 'ai_filter'} & set(result):
                    found.append(result)
            return found

        text = response_text or ''
        candidates = scan(text)
        if not candidates and '<br' in text.lower():
            normalized = re.sub(r'<br\s*/?>', '\n', text, flags=re.IGNORECASE)
            normalized = re.sub(r'</?think>', '', normalized, flags=re.IGNORECASE)
            normalized = html.unescape(normalized)
            candidates = scan(normalized)

        if candidates:
            return candidates[-1]

        raise json.JSONDecodeError("No JSON object found in model response", text, 0)

    @staticmethod
    def _clean_optional_text(value):
        if not isinstance(value, str):
            return None
        cleaned = value.strip()
        return cleaned or None

    @staticmethod
    def prepare_content_for_ai(
        title,
        original_content,
        content_limit=DEFAULT_AI_CONTENT_LIMIT,
    ):
        """Convierte HTML/texto del feed en cuerpo compacto para el prompt.

        Con ``content_limit=None`` devuelve el texto limpio sin truncar.
        """
        raw_content = html.unescape(original_content or '')
        if not raw_content:
            return ''

        if '<' in raw_content and '>' in raw_content:
            soup = BeautifulSoup(raw_content, 'html.parser')
            for element in soup.find_all(['script', 'style', 'nav', 'header', 'footer', 'iframe', 'noscript']):
                element.decompose()
            clean_text = soup.get_text(' ', strip=True)
        else:
            clean_text = raw_content

        clean_text = html.unescape(clean_text)
        clean_text = re.sub(r'\s+', ' ', clean_text).strip()

        safe_title = re.sub(r'\s+', ' ', title or '').strip()
        if safe_title and clean_text.lower().startswith(safe_title.lower()):
            clean_text = clean_text[len(safe_title):].lstrip(' :-|')

        clean_text = re.sub(r'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z\s+', '', clean_text)
        clean_text = re.sub(r'\bLinkedin\s+twitter\s+instagram\b', ' ', clean_text, flags=re.IGNORECASE)
        clean_text = re.sub(r'\b\d+\s+publicaciones\s+de\s+', ' ', clean_text, flags=re.IGNORECASE)
        clean_text = re.sub(r'\s+', ' ', clean_text).strip()

        if content_limit and len(clean_text) > content_limit:
            truncated = clean_text[:content_limit]
            # Cortar en el final de la última frase completa para no partir
            # a mitad de oración justo el dato que el resumen necesita.
            sentence_end = max(
                truncated.rfind('. '),
                truncated.rfind('! '),
                truncated.rfind('? '),
            )
            if sentence_end > content_limit * 0.6:
                truncated = truncated[:sentence_end + 1]
            clean_text = truncated.strip()

        return clean_text

    @staticmethod
    def _formatear_resumen(texto):
        """Pasa el markdown ligero que a veces cuela el modelo a HTML seguro."""
        html_text = re.sub(r'^\* (.+?)$', r' <strong>\1</strong>', texto, flags=re.MULTILINE)
        html_text = re.sub(r'\*\*(.*?)\*\*', r'<strong>\1</strong>', html_text)
        html_text = html_text.replace('\n\n', '<br><br>').replace('\n', '<br>')
        return sanitize_html(html_text)

    @staticmethod
    def process_news_content(
        title,
        original_content,
        filter_instructions_text,
        content_limit=DEFAULT_AI_CONTENT_LIMIT,
        ai_model_setting=None,
    ):
        """Genera resumen, respuesta corta y motivo de filtro para una noticia.

        Prueba los proveedores en orden (primario y respaldo) y solo salta al
        siguiente cuando el fallo lo justifica: quedarse sin cuota si, una
        peticion mal construida no, porque fallaria igual en el otro.

        Devuelve ``(resumen_html, short_answer, ai_filter)`` o ``(None, None,
        None)`` si ninguno pudo, dejando el motivo en ``_LAST_AI_FAILURE`` para
        que el feed lo explique.
        """
        instructions_section = filter_instructions_text or FeedService._DEFAULT_FILTER_INSTRUCTIONS
        base_content = FeedService.prepare_content_for_ai(
            title, original_content, content_limit=content_limit
        )

        # Las llaves se escapan porque el prompt se arma con str.format y un
        # titular con '{' reventaria la plantilla.
        prompt = FeedService._PROMPT_TEMPLATE.format(
            title=(title or '').replace('{', '{{').replace('}', '}}'),
            content=base_content.replace('{', '{{').replace('}', '}}'),
            instructions=instructions_section.replace('{', '{{').replace('}', '}}'),
        )

        ultimo_fallo = None
        for proveedor in cadena_de_proveedores(ai_model_setting):
            try:
                respuesta = proveedor.complete(prompt)
            except AIProviderError as e:
                ultimo_fallo = e
                logger.warning('%s: %s', proveedor.nombre, e.reason)
                if not e.puede_reintentar_otro:
                    break
                continue
            except Exception as e:  # noqa: BLE001 - un proveedor no debe tumbar la pasada
                ultimo_fallo = AIProviderError(
                    'error', f'{proveedor.nombre} falló de forma inesperada.', str(e)
                )
                logger.exception('Fallo inesperado en %s', proveedor.nombre)
                continue

            resultado = FeedService._interpretar_respuesta(respuesta, base_content, proveedor)
            if resultado is not None:
                FeedService._clear_ai_failure()
                return resultado
            ultimo_fallo = AIProviderError(
                'error', f'{proveedor.nombre} no devolvió un JSON utilizable.', respuesta[:400]
            )

        if ultimo_fallo is not None:
            FeedService._note_ai_failure(
                ultimo_fallo.kind, ultimo_fallo.reason,
                ultimo_fallo.detail, ultimo_fallo.retry_seconds,
            )
        return None, None, None

    @staticmethod
    def _interpretar_respuesta(respuesta, base_content, proveedor):
        """Convierte el texto del modelo en la terna final, o None si no vale."""
        if not (respuesta or '').strip():
            logger.warning('%s devolvió contenido vacío.', proveedor.nombre)
            return None
        try:
            datos = FeedService._parse_model_json(respuesta)
        except json.JSONDecodeError as e:
            logger.warning('JSON inválido de %s: %s', proveedor.nombre, e)
            return None

        summary = FeedService._clean_optional_text(datos.get('summary'))
        short_answer = FeedService._clean_optional_text(datos.get('short_answer'))
        ai_filter = FeedService._clean_optional_text(datos.get('ai_filter'))

        if not summary:
            # Sin resumen la noticia se queda sin cuerpo: antes de descartarla
            # se cae al texto original recortado, que es peor pero es algo.
            summary = base_content[:600] or short_answer
        if not summary:
            logger.warning('%s no devolvió summary ni short_answer.', proveedor.nombre)
            return None

        return FeedService._formatear_resumen(summary), short_answer, ai_filter

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

            # Eliminar elementos no deseados (boilerplate que contamina el texto).
            # OJO: no eliminar <noscript>: en sitios renderizados por JS (p.ej.
            # foros Flarum como WOW Chakra) el cuerpo del artículo vive ahí.
            for element in soup.find_all([
                'script', 'style', 'nav', 'header', 'footer', 'iframe',
                'aside', 'form', 'button',
            ]):
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

                # Preferir solo los párrafos: evita pies de foto, bloques de
                # "relacionados", banners de cookies/suscripción, etc.
                paragraphs = [p.get_text(' ', strip=True) for p in content.find_all('p')]
                paragraph_text = ' '.join(part for part in paragraphs if part)
                if len(paragraph_text) >= 300:
                    text_content = paragraph_text
                else:
                    text_content = content.get_text(separator=' ', strip=True)
            
            return {
                'text': text_content,
                'image_url': image_url
            }
        except Exception:
            logger.exception("Error obteniendo contenido completo")
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
    def _preparar_entrada(item, filter_word_patterns, fifteen_days_ago):
        """Fase 1: todo lo que se puede resolver sin llamar a la IA.

        Separar esto del resto es lo que permite pedir los embeddings de una
        tanda entera en una sola petición: hasta que no se sabe el texto
        definitivo de cada noticia (que puede venir del artículo descargado, no
        del feed) no hay nada que agrupar.

        Devuelve ``(preparada, creadas)``. ``preparada`` es ``None`` cuando la
        entrada ya quedó resuelta aquí (guardada como filtrada) o descartada, y
        ``creadas`` cuenta las filas escritas para que el llamador sume.
        """
        creadas = 0
        entry = item['entry']
        source = item['source']
        published = item['published']
        guid = item['guid']
        
        logger.info(f"\nProcesando entrada: {entry.title} ({published})")
        
        # Validación: títulos anormalmente largos se guardan como filtradas
        # (registrando el guid) para no re-descargarlas en cada ciclo.
        if len(entry.title) > 200:
            logger.info(f"FILTRANDO noticia con título muy largo ({len(entry.title)} caracteres): {entry.title[:100]}...")
            try:
                News.objects.create(
                    guid=guid,
                    title=entry.title[:500],
                    # Fila oculta: guardar solo texto plano recortado
                    description=FeedService.prepare_content_for_ai(
                        entry.title, entry.get('description', '') or '', content_limit=2000
                    ),
                    link=entry.link,
                    published_date=published,
                    source=source,
                    is_filtered=True,
                    is_ai_processed=True,
                )
            except Exception:
                logger.exception(
                    "Error al guardar noticia con título largo. GUID=%s", guid[:100]
                )
            return None, creadas
        
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

        # Feeds Atom/WordPress suelen traer el cuerpo completo en
        # entry.content y solo un extracto (o nada) en description:
        # usar el bloque más largo para no resumir a ciegas.
        if hasattr(entry, 'content') and entry.content:
            for content_block in entry.content:
                try:
                    block_value = content_block.get('value')
                except AttributeError:
                    block_value = getattr(content_block, 'value', None)
                if block_value and len(block_value) > len(original_description):
                    original_description = block_value

        # Texto plano para filtrado y embeddings (sin markup, sin truncar)
        plain_description = FeedService.prepare_content_for_ai(
            entry.title, original_description, content_limit=None
        )

        # >>>>> ORDEN CAMBIADO: Primero filtro por PALABRA CLAVE <<<<<
        # Se filtra sobre texto plano para no matchear dentro de URLs o atributos HTML.
        should_filter, filter_word = FeedService.should_filter_news(entry.title, plain_description, filter_word_patterns)
        if should_filter:
            logger.info(f"Noticia FILTRADA por palabra clave: {filter_word.word}")
            
            # Validaciones adicionales para campos que podrían ser muy largos
            logger.debug(f"Longitudes: título={len(entry.title)}, guid={len(guid)}, link={len(entry.link)}")
            if hasattr(entry, 'description') and entry.description:
                logger.debug(f"Descripción original: {len(entry.description)} caracteres")
            logger.debug(f"Descripción procesada: {len(original_description)} caracteres")
            
            try:
                News.objects.create(
                    guid=guid,
                    title=entry.title,
                    short_answer=None,
                    # Fila oculta: texto plano recortado, no el HTML completo del feed
                    description=sanitize_html(plain_description[:2000]),
                    link=entry.link,
                    published_date=published,
                    source=source,
                    is_filtered=True,
                    filtered_by=filter_word,
                    image_url=image_url,
                    is_ai_processed=True
                )
                creadas += 1
            except Exception:
                logger.exception(
                    "Error al guardar noticia filtrada por keyword. GUID=%s título=%s link=%s descripción_len=%s",
                    guid[:100],
                    entry.title[:100],
                    entry.link[:100],
                    len(original_description) if original_description else 0,
                )
                return None, creadas

            return None, creadas
        # <<<<< FIN FILTRO PALABRA CLAVE >>>>>

        # Obtener contenido completo (solo noticias no filtradas por keyword) si:
        # - deep_search está activado para la fuente, o
        # - el feed trajo tan poco texto que la IA resumiría a ciegas.
        ai_content_limit = DEFAULT_AI_CONTENT_LIMIT
        if source.deep_search or len(plain_description) < 200:
            full_content = FeedService.get_full_article_content(entry.link)
            if full_content['text'] and (
                source.deep_search or len(full_content['text']) > len(plain_description)
            ):
                original_description = full_content['text']
                plain_description = FeedService.prepare_content_for_ai(
                    entry.title, original_description, content_limit=None
                )
                # El mismo límite amplio cubre tanto el RSS como el artículo
                # descargado sin penalizar a las fuentes que ya entregan el
                # cuerpo completo en el feed.
                ai_content_limit = DEFAULT_AI_CONTENT_LIMIT
            # Solo usar la imagen del contenido si no se encontró una en el feed
            if not image_url and full_content['image_url']:
                image_url = full_content['image_url']

        # Guard extra: nunca crear noticias anteriores a 15 días
        if published < fifteen_days_ago:
            return None, creadas
        return {
            'entry': entry,
            'source': source,
            'published': published,
            'guid': guid,
            'image_url': image_url,
            'original_description': original_description,
            'plain_description': plain_description,
            'ai_content_limit': ai_content_limit,
        }, creadas

    @staticmethod
    def fetch_and_save_news(max_ai_items=None):
        logger.info("Iniciando proceso de obtención de noticias...")
        start_time = time.time()
        # Motivo por el que la pasada se cortó antes de tiempo, si se corta.
        ai_failure = None

        logger.info("Inicializando modelos...")
        # Gemini solo para embeddings: los resúmenes los pide
        # process_news_content al proveedor que toque.
        gemini_client = FeedService.initialize_gemini()
        vector_index = FeedService.initialize_vector_index()

        # Obtener modelo de IA desde el admin (base de datos) o usar default
        try:
            ai_model_setting = AIModelSetting.objects.first()
            if not ai_model_setting:
                logger.warning("No se encontró configuración global de modelo IA. Creando con modelo predeterminado.")
                ai_model_setting = AIModelSetting.objects.create(model_name=DEFAULT_AI_MODEL)
            ai_model_name = ai_model_setting.model_name
        except Exception:
            logger.exception("Error al obtener configuración de modelo IA. Usando default.")
            ai_model_setting = None
            ai_model_name = DEFAULT_AI_MODEL
        
        filter_word_patterns = FeedService.build_filter_word_patterns(
            FilterWord.objects.filter(active=True)
        )
        filter_instructions_text = FeedService.build_filter_instructions_text(
            AIFilterInstruction.objects.filter(active=True)
        )

        sources = list(FeedSource.objects.filter(active=True))
        logger.info(f"Procesando {len(sources)} fuentes activas con {ai_model_name}")
        new_articles_count = 0
        
        # Calcular la fecha límite (15 días atrás)
        fifteen_days_ago = timezone.now() - timedelta(days=15)
        recent_news_cache = []

        existing_guids = set(
            News.objects.filter(published_date__gte=fifteen_days_ago).values_list('guid', flat=True)
        )

        # Obtener última fecha visible por fuente en una sola consulta (evita N+1)
        source_ids = [source.id for source in sources]
        latest_by_source = {}
        if source_ids:
            latest_by_source = dict(
                News.objects.filter(
                    source_id__in=source_ids,
                    is_deleted=False,
                    is_filtered=False
                ).values('source_id').annotate(
                    latest_date=Max('published_date')
                ).values_list('source_id', 'latest_date')
            )

        
        # Lista para almacenar todas las entradas de todas las fuentes
        all_entries = []
        
        # Primero, recolectar todas las entradas de todas las fuentes
        for source in sources:
            logger.info(f"\nRecolectando entradas de fuente: {source.name}")
            
            # Obtener la fecha de la última noticia visible por fuente (cacheada en memoria)
            latest_date = latest_by_source.get(source.id) or fifteen_days_ago
            
            # Usar la fecha más reciente entre la última noticia y hace 15 días
            cutoff_date = max(latest_date, fifteen_days_ago)
            
            try:
                feed_response = requests.get(
                    source.url,
                    timeout=15,
                    headers={'User-Agent': 'Mozilla/5.0 (compatible; johanfer-news-bot/1.0)'},
                )
                feed_response.raise_for_status()
                feed = feedparser.parse(feed_response.content)
            except requests.RequestException:
                logger.exception(f"Error descargando feed de {source.name}; se omite esta fuente en este ciclo.")
                continue
            logger.info(f"Encontradas {len(feed.entries)} entradas en el feed")
            
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
                # GUIDs desmesurados: usar un hash estable para poder
                # guardarlos y que la deduplicación siga funcionando.
                if len(guid) > 400:
                    guid = 'sha256:' + hashlib.sha256(guid.encode('utf-8')).hexdigest()
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
        logger.info(f"\nSe recolectaron {len(all_entries)} nuevas entradas de todas las fuentes")

        # Contador para noticias redundantes
        redundant_count = 0
        ai_attempts = 0
        # Fallos de vectorización: hasta ahora se perdían en silencio.
        embedding_failures = 0
        indexing_failures = 0
        
        # Procesar todas las entradas en orden (de más antigua a más reciente)
        # Se procesa por tandas y no de una: la tanda es lo que se pide a la
        # API de embeddings en una sola llamada, y acotarla evita descargar
        # artículos y gastar vectores de entradas que el presupuesto de IA no
        # va a llegar a resumir en esta pasada.
        tam_tanda = EmbeddingService.EMBEDDING_BATCH_SIZE
        if max_ai_items:
            # Sin esto, una tanda podría descargar 32 artículos para que el
            # presupuesto se agotase en el vigésimo y se tirasen doce descargas.
            tam_tanda = min(tam_tanda, max_ai_items)
        detener = False

        for inicio_tanda in range(0, len(all_entries), tam_tanda):
            if detener:
                break

            preparadas = []
            for item in all_entries[inicio_tanda:inicio_tanda + tam_tanda]:
                try:
                    preparada, creadas = FeedService._preparar_entrada(
                        item, filter_word_patterns, fifteen_days_ago
                    )
                except Exception:
                    logger.exception(
                        "Error preparando la entrada. GUID=%s", str(item.get('guid'))[:100]
                    )
                    continue
                new_articles_count += creadas
                if preparada is not None:
                    preparadas.append(preparada)

            if not preparadas:
                continue

            # Una sola petición de embeddings para toda la tanda.
            vectores = EmbeddingService.generate_embeddings_batch(
                [f"{p['entry'].title} {p['plain_description']}" for p in preparadas],
                gemini_client,
            )

            for preparada, vector in zip(preparadas, vectores):
                entry = preparada['entry']
                source = preparada['source']
                published = preparada['published']
                guid = preparada['guid']
                image_url = preparada['image_url']
                original_description = preparada['original_description']
                plain_description = preparada['plain_description']
                ai_content_limit = preparada['ai_content_limit']

                # Verificar redundancia ANTES de llamar a la IA: una noticia
                # redundante no debe consumir presupuesto de resúmenes. El
                # embedding se genera desde título + contenido original limpio.
                candidate = News(
                    guid=guid,
                    title=entry.title,
                    description=plain_description,
                    source=source,
                    published_date=published,
                )
                # El vector ya viene del lote de la tanda; se marca el intento
                # para que check_redundancy no vuelva a pedirlo de uno en uno.
                candidate._embedding_vector = vector
                candidate._embedding_attempted = True
                is_redundant, similar_news, similarity_score = EmbeddingService.check_redundancy(
                    candidate, gemini_client, recent_news_cache, vector_index
                )
                embedding = getattr(candidate, "_embedding_vector", None)
                similar_ref = getattr(candidate, "_similar_ref", '') or ''

                # El original puede haberse purgado hace meses y no tener fila:
                # sigue siendo un duplicado, así que basta con que Qdrant lo
                # haya reconocido (similar_ref) aunque similar_news sea None.
                if is_redundant and (similar_news or similar_ref):
                    referencia = similar_news.title if similar_news else similar_ref
                    logger.info(f"¡Noticia redundante detectada! Similar a: {referencia}")
                    logger.info(f"Puntuación de similitud: {similarity_score:.4f} (Umbral: {source.similarity_threshold})")
                    try:
                        News.objects.create(
                            guid=guid,
                            title=entry.title,
                            short_answer=None,
                            # Fila oculta: texto plano recortado, no el artículo completo
                            description=sanitize_html(plain_description[:2000]),
                            link=entry.link,
                            published_date=published,
                            source=source,
                            image_url=image_url,
                            is_redundant=True,
                            is_filtered=True,
                            similar_to=similar_news,
                            similar_ref=similar_ref,
                            similarity_score=similarity_score,
                            is_ai_processed=True,
                        )
                        new_articles_count += 1
                        redundant_count += 1
                    except Exception:
                        logger.exception(
                            "Error al guardar noticia redundante. GUID=%s título=%s",
                            guid[:100],
                            entry.title[:100],
                        )
                    continue

                ai_was_processed = False
                short_answer = None
                ai_filter_reason = None

                if max_ai_items is not None and ai_attempts >= max_ai_items:
                    logger.info(
                        f"Presupuesto de IA agotado ({max_ai_items}); "
                        "se pausa la ingesta para continuar en la próxima actualización."
                    )
                    detener = True
                    break

                ai_attempts += 1

                # Si no se filtró por palabra clave ni es redundante, procesar con IA
                processed_description, short_answer, ai_filter_reason = FeedService.process_news_content(
                    entry.title,
                    original_description,
                    filter_instructions_text,
                    content_limit=ai_content_limit,
                    ai_model_setting=ai_model_setting,
                )
                if processed_description:
                    ai_was_processed = True
                else:
                    logger.warning(
                        "La IA no generó resumen; se pausa la ingesta para reintentar luego."
                    )
                    ai_failure = FeedService._LAST_AI_FAILURE or {
                        'kind': 'error',
                        'reason': 'La IA no devolvió resumen y la ingesta se detuvo.',
                        'detail': '',
                        'retry_seconds': None,
                    }
                    detener = True
                    break

                # >>>>> LÓGICA DE FILTRADO IA (después de palabra clave) <<<<<
                # Asegurarnos que ai_filter_reason es un string no vacío antes de usarlo
                if ai_was_processed and ai_filter_reason and isinstance(ai_filter_reason, str) and ai_filter_reason.strip():
                    logger.info(f"Noticia marcada para FILTRAR por IA. Razón: {ai_filter_reason}")
                
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
                    except Exception:
                        logger.exception(
                            "Error al guardar noticia filtrada por IA. GUID=%s título=%s link=%s ai_filter_reason=%s",
                            guid[:100],
                            entry.title[:100],
                            entry.link[:100],
                            ai_filter_reason[:100],
                        )
                        continue
                    
                    continue # Pasar a la siguiente noticia
                elif ai_filter_reason: # Si Gemini devolvió algo pero no es un string válido
                    logger.warning(f"Gemini devolvió un valor para ai_filter ({ai_filter_reason}) pero no es la instrucción esperada. No se filtrará.")
                # <<<<< FIN LÓGICA FILTRADO IA >>>>>

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
                        is_ai_processed=ai_was_processed,
                        # Conservar la referencia a la más parecida aunque no supere el umbral
                        similar_to=similar_news,
                        similarity_score=similarity_score if similar_news else None,
                    )
                    new_articles_count += 1
                except Exception:
                    logger.exception(
                        "Error al guardar noticia normal. GUID=%s título=%s link=%s",
                        guid[:100],
                        entry.title[:100],
                        entry.link[:100],
                    )
                    continue

                if embedding:
                    news_item._embedding_vector = embedding
                    recent_news_cache.append(news_item)
                    # Indexar en Qdrant (si está disponible) para futuras búsquedas
                    if vector_index is not None:
                        try:
                            vector_index.ensure_collection(len(embedding))
                            vector_index.upsert(
                                news_item.guid,
                                embedding,
                                FeedService.build_vector_payload(news_item),
                            )
                        except Exception:
                            # No se silencia: una noticia sin indexar no participa en
                            # la detección de duplicados de las siguientes, y el fallo
                            # era invisible hasta ahora.
                            indexing_failures += 1
                            logger.exception(
                                "Error indexando en Qdrant. news_id=%s título=%s",
                                news_item.id,
                                news_item.title[:100],
                            )
                else:
                    # Sin embedding esta noticia no pasó por el control de duplicados
                    # y tampoco servirá para comparar las futuras.
                    embedding_failures += 1
                    logger.warning(
                        "Noticia guardada SIN embedding (se salta el control de duplicados). "
                        "news_id=%s título=%s",
                        news_item.id,
                        news_item.title[:100],
                    )

        
        # Actualizar la fecha de última obtención para todas las fuentes con una sola escritura
        fetched_at = timezone.now()
        for source in sources:
            source.last_fetch = fetched_at
        if sources:
            FeedSource.objects.bulk_update(sources, ['last_fetch'])
            for source in sources:
                logger.info(f"Actualizada fecha de última obtención para {source.name}")
        
        total_time = time.time() - start_time

        # Dejar anotado cómo fue la pasada: es lo único que verá la web, que
        # corre en otro proceso y no tiene acceso a este log.
        if ai_failure:
            retry_at = None
            if ai_failure.get('retry_seconds'):
                retry_at = timezone.now() + timedelta(seconds=ai_failure['retry_seconds'])
            report_paused(
                ai_failure['reason'],
                detail=ai_failure.get('detail', ''),
                new_count=new_articles_count,
                retry_at=retry_at,
            )
        else:
            report_ok(new_count=new_articles_count)

        logger.info(f"\nProceso completado en {total_time:.2f} segundos")
        logger.info(f"Total de nuevas noticias: {new_articles_count}")
        logger.info(f"Noticias redundantes eliminadas: {redundant_count}")
        if embedding_failures or indexing_failures:
            logger.warning(
                "Vectorización con fallos: %s sin embedding y %s sin indexar. "
                "Esas noticias no pasaron el control de duplicados; "
                "retry_missing_embeddings las recuperará.",
                embedding_failures,
                indexing_failures,
            )
        
        return new_articles_count 

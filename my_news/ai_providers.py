"""Proveedores de IA para los resumenes del feed.

Un solo sitio donde vive todo lo que depende del proveedor: como se pide el
JSON, como se leen sus limites y como se traduce un fallo suyo a algo que el
feed pueda explicar. ``services.py`` solo arma el prompt y usa el resultado.

Estado en septiembre de 2026, medido sobre el prompt real con 8 noticias:

+---------------------------+---------+----------+--------+---------+
| proveedor / modelo        | aciertos| latencia | tokens | limites |
+---------------------------+---------+----------+--------+---------+
| gemini-3.5-flash-lite     |   7/8   |  2,3 s   |  1.077 | 15 RPM / 500 RPD  |
| groq openai/gpt-oss-120b  |   6/6   |  1,0 s   |  1.355 | 8.000 TPM / 1.000 RPD |
+---------------------------+---------+----------+--------+---------+

Gemini va primero porque su cuello de botella (500 peticiones al dia, frente a
las ~140 que se gastan) deja mas holgura que los 8.000 tokens por minuto de
Groq, y porque su cliente ya estaba montado para los embeddings: cero
dependencias nuevas, que en una Pi con 1 GB y 24 s de imports importa.

Descartados y por que, para no volver a probarlos:
  - ``gemini-2.5-flash-lite``: 20 peticiones al dia. Inservible.
  - ``gemini-2.5-flash``: buena calidad pero 12,8 s por noticia.
  - ``gemma-4-31b`` en Google: 500 y 503 en 6 de 8 llamadas pese a sus
    14.400 RPD, y 22 s de latencia.
  - ``qwen3.8-27b`` en Groq: pide 4.096 tokens de presupuesto y no cabe en el
    limite de 8.000 por minuto ("request too large" en 7 de 8).
  - Cerebras entero: su prueba gratuita son 5 dolares que caducan a los 30
    dias, no hay plan gratuito. Se retiro en septiembre de 2026; el codigo
    esta en `git show <commit>:my_news/services.py` si alguna vez se recompra.
"""

import json
import logging
import os
import re
import time

import requests
from django.conf import settings

logger = logging.getLogger(__name__)


GEMINI = 'gemini'
GROQ = 'groq'

PROVIDER_CHOICES = [
    (GEMINI, 'Gemini (Google)'),
    (GROQ, 'Groq'),
]

# Modelo que usa cada proveedor si no se fija otro a mano en el admin.
DEFAULT_MODELS = {
    GEMINI: 'gemini-3.5-flash-lite',
    GROQ: 'openai/gpt-oss-120b',
}

DEFAULT_PROVIDER = GEMINI
DEFAULT_FALLBACK = GROQ


class AIProviderError(Exception):
    """Fallo de un proveedor, ya traducido a algo que el feed pueda contar.

    ``kind`` es lo que lee ``IngestionStatus``: 'quota', 'rate_limit' o
    'error'. ``puede_reintentar_otro`` distingue el fallo que justifica saltar
    al proveedor de respaldo (se quedo sin cuota) del que no lo justifica
    (la peticion iba mal construida y fallaria igual en el otro).
    """

    def __init__(self, kind, reason, detail='', retry_seconds=None,
                 puede_reintentar_otro=True):
        super().__init__(reason)
        self.kind = kind
        self.reason = reason
        self.detail = (detail or '')[:2000]
        self.retry_seconds = retry_seconds
        self.puede_reintentar_otro = puede_reintentar_otro


class AIRateLimiter:
    """Limitador por proceso guiado por las cabeceras ``x-ratelimit-*``.

    Groq las devuelve con los mismos nombres que usaba Cerebras, asi que la
    logica se reutiliza tal cual. Gemini no las manda: alli el freno es el 429,
    que se traduce en ``Deferred`` sin pasar por aqui.
    """

    DEFAULT_RPM = 300
    DEFAULT_TPM = 500_000
    SAFETY_FACTOR = 0.75
    SAFE_RPM_CAP = 250
    MAX_RETRY_SLEEP_SECONDS = 90
    MODEL_LIMITS = {
        # Valores de arranque, solo para la primera peticion de cada proceso:
        # a partir de la primera respuesta mandan las cabeceras. Solo Groq las
        # usa; Gemini no pasa por aqui.
        # Medidos en septiembre de 2026 con la cuenta en el plan gratuito.
        'openai/gpt-oss-120b': {'tpm': 8_000, 'rpm': 30},
    }

    def __init__(self):
        self.window_seconds = 60.0
        self.window_start = time.monotonic()
        self.used_tokens = 0
        self.used_requests = 0
        self.remaining_tokens = None
        self.remaining_requests = None
        self.reset_tokens_at = None
        self.reset_requests_at = None
        self.limit_tokens = None
        self.limit_requests = None
        # Cuál de las tres ventanas (minuto/hora/día) es la que va más justa.
        # Solo informativo, para que el aviso diga si lo agotado es la cuota
        # del día o un pico pasajero del minuto.
        self.tightest_tokens_window = None
        self.tightest_requests_window = None

    class Deferred(Exception):
        """Señal interna: conviene pausar esta corrida y reintentar luego."""
        pass

    def get_limits(self, model_name):
        model_limits = self.MODEL_LIMITS.get(model_name or '', {})
        # Lo que diga la API manda sobre la tabla escrita a mano: los topes
        # cambian al cambiar de plan y aquí se envejecen sin avisar. La tabla
        # queda como valor de arranque, para la primera petición de un proceso
        # nuevo, cuando todavía no ha llegado ninguna cabecera.
        #
        # Al valor medido no se le aplica el margen de seguridad: es exacto, y
        # además viene acompañado del margen restante, que es un segundo freno.
        # Recortar un 25% de un tope de 5 peticiones por minuto costaría casi la
        # mitad del ritmo sin comprar ninguna garantía.
        if self.limit_tokens:
            safe_tpm = max(1, int(self.limit_tokens))
        else:
            tpm = int(model_limits.get('tpm') or self.DEFAULT_TPM)
            safe_tpm = max(1, int(tpm * self.SAFETY_FACTOR))

        if self.limit_requests:
            safe_rpm = max(1, min(int(self.limit_requests), self.SAFE_RPM_CAP))
        else:
            rpm = int(model_limits.get('rpm') or self.DEFAULT_RPM)
            safe_rpm = max(1, min(int(rpm * self.SAFETY_FACTOR), self.SAFE_RPM_CAP))

        return safe_tpm, safe_rpm

    def estimate_tokens(self, prompt, max_completion_tokens=1024):
        prompt_text = prompt or ''
        prompt_tokens = max(1, len(prompt_text) // 4)
        return prompt_tokens + int(max_completion_tokens or 0)

    def seconds_until_next_window(self):
        elapsed = time.monotonic() - self.window_start
        return max(0.0, self.window_seconds - elapsed)

    def parse_reset_seconds(self, value):
        if not value:
            return None
        text = str(value).strip().lower()
        try:
            return max(0.0, float(text.rstrip('s')))
        except ValueError:
            pass

        match = re.fullmatch(r'(?:(\d+(?:\.\d+)?)m)?(?:(\d+(?:\.\d+)?)s)?', text)
        if not match:
            return None

        minutes = float(match.group(1) or 0)
        seconds = float(match.group(2) or 0)
        return max(0.0, minutes * 60 + seconds)

    def _read_header(self, headers, name):
        if not headers:
            return None
        return headers.get(name) or headers.get(name.title()) or headers.get(name.lower())

    def _read_number(self, headers, name):
        raw = self._read_header(headers, name)
        if raw is None:
            return None
        try:
            return int(float(raw))
        except (TypeError, ValueError):
            return None

    def tightest_window(self, headers, kind):
        """Ventana más apretada de las tres que publica el proveedor.

        Se miran minuto, hora y día y gana la que tenga menos margen. Antes solo
        se leía la del minuto para los tokens, así que agotar la cuota diaria no
        frenaba nada: se enviaba la petición y el límite se descubría al recibir
        el error. Cada margen viaja junto a SU reset, porque son de duraciones
        muy distintas — esperar el reset del minuto cuando lo agotado es el día
        haría reintentar en vano durante horas.

        Devuelve ``(margen, reset_en_segundos, ventana)`` o ``None``.
        """
        best = None
        for window in ('minute', 'hour', 'day'):
            remaining = self._read_number(headers, f'x-ratelimit-remaining-{kind}-{window}')
            if remaining is None:
                continue
            reset = self.parse_reset_seconds(
                self._read_header(headers, f'x-ratelimit-reset-{kind}-{window}')
            )
            if best is None or remaining < best[0]:
                best = (remaining, reset, window)

        if best is None:
            # Formato antiguo, sin sufijo de ventana.
            remaining = self._read_number(headers, f'x-ratelimit-remaining-{kind}')
            if remaining is None:
                return None
            reset = self.parse_reset_seconds(
                self._read_header(headers, f'x-ratelimit-reset-{kind}')
            )
            best = (remaining, reset, 'desconocida')

        return best

    def update_from_headers(self, headers):
        now = time.monotonic()

        tokens = self.tightest_window(headers, 'tokens')
        if tokens is None:
            self.remaining_tokens = None
            self.reset_tokens_at = None
            self.tightest_tokens_window = None
        else:
            remaining, reset, window = tokens
            self.remaining_tokens = remaining
            self.reset_tokens_at = now + reset if reset is not None else None
            self.tightest_tokens_window = window

        requests_left = self.tightest_window(headers, 'requests')
        if requests_left is None:
            self.remaining_requests = None
            self.reset_requests_at = None
            self.tightest_requests_window = None
        else:
            remaining, reset, window = requests_left
            self.remaining_requests = remaining
            self.reset_requests_at = now + reset if reset is not None else None
            self.tightest_requests_window = window

        # Los topes por minuto son los que alimentan el presupuesto local, que
        # razona en ventanas de 60 s. Los de hora y día no sirven ahí: tomar el
        # tope diario como si fuera por minuto permitiría una ráfaga enorme.
        self.limit_tokens = (
            self._read_number(headers, 'x-ratelimit-limit-tokens-minute')
            or self._read_number(headers, 'x-ratelimit-limit-tokens')
        )
        self.limit_requests = (
            self._read_number(headers, 'x-ratelimit-limit-requests-minute')
            or self._read_number(headers, 'x-ratelimit-limit-requests')
        )

    def _sleep_or_defer(self, wait_time, reason):
        if wait_time is None:
            return
        wait_time = max(0.0, float(wait_time))
        if wait_time > self.MAX_RETRY_SLEEP_SECONDS:
            raise AIRateLimiter.Deferred(
                f"Rate limit: {reason}; reset en {wait_time:.1f}s"
            )
        if wait_time > 0:
            logger.warning(f"Rate limit: esperando {wait_time:.1f}s ({reason}).")
            time.sleep(wait_time)

    def reset_if_needed(self):
        if time.monotonic() - self.window_start >= self.window_seconds:
            self.window_start = time.monotonic()
            self.used_tokens = 0
            self.used_requests = 0
            if self.reset_requests_at is None:
                self.remaining_requests = None
            if self.reset_tokens_at is None:
                self.remaining_tokens = None

    def acquire(self, model_name, prompt, max_completion_tokens=1024):
        estimated_tokens = self.estimate_tokens(prompt, max_completion_tokens)
        token_limit, request_limit = self.get_limits(model_name)

        while True:
            self.reset_if_needed()
            now = time.monotonic()
            if self.remaining_requests is not None and self.remaining_requests <= 0:
                wait_time = (self.reset_requests_at - now + 1) if self.reset_requests_at else self.seconds_until_next_window() + 1
                self._sleep_or_defer(wait_time, 'sin requests disponibles')
                self.remaining_requests = None
                continue
            if self.remaining_tokens is not None and estimated_tokens > self.remaining_tokens:
                wait_time = (self.reset_tokens_at - now + 1) if self.reset_tokens_at else self.seconds_until_next_window() + 1
                self._sleep_or_defer(wait_time, 'tokens insuficientes')
                self.remaining_tokens = None
                continue

            would_exceed_tokens = self.used_tokens + estimated_tokens > token_limit
            would_exceed_requests = self.used_requests + 1 > request_limit

            if not would_exceed_tokens and not would_exceed_requests:
                self.used_tokens += estimated_tokens
                self.used_requests += 1
                return estimated_tokens

            if estimated_tokens > token_limit and self.used_tokens == 0 and self.used_requests == 0:
                logger.warning(
                    f"Rate limit local: una petición estimada en {estimated_tokens} tokens "
                    f"supera el límite seguro de {token_limit}; se enviará una sola petición."
                )
                self.used_tokens = estimated_tokens
                self.used_requests = 1
                return estimated_tokens

            wait_time = self.seconds_until_next_window() + 1
            logger.warning(
                f"Rate limit local: esperando {wait_time:.1f}s "
                f"(modelo={model_name}, estimado={estimated_tokens} tokens, "
                f"usados={self.used_tokens}/{token_limit})."
            )
            time.sleep(wait_time)


# --- Esquema de la respuesta -------------------------------------------------
# Los tres campos que se le piden al modelo. Cada proveedor lo expresa a su
# manera pero la forma es la misma, asi que se declara una vez.
_CAMPOS = ('summary', 'short_answer', 'ai_filter')

# Formato de OpenAI, que es el que habla Groq.
OPENAI_RESPONSE_FORMAT = {
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
            "required": list(_CAMPOS),
        },
    },
}

# Gemini usa su propio dialecto: 'nullable' en vez de un tipo union.
GEMINI_RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "summary": {"type": "string"},
        "short_answer": {"type": "string", "nullable": True},
        "ai_filter": {"type": "string", "nullable": True},
    },
    "required": list(_CAMPOS),
}


class BaseProvider:
    """Interfaz comun: recibe un prompt y devuelve el texto JSON del modelo."""

    nombre = ''

    def __init__(self, model_name=None, setting=None):
        self.model_name = model_name or DEFAULT_MODELS[self.nombre]
        self.setting = setting

    def complete(self, prompt):
        raise NotImplementedError

    @staticmethod
    def _api_key(nombre_var):
        clave = getattr(settings, nombre_var, None) or os.environ.get(nombre_var)
        if not clave:
            raise AIProviderError(
                'error',
                f'Falta {nombre_var}; ese proveedor no puede usarse.',
                puede_reintentar_otro=True,
            )
        return clave


class GeminiProvider(BaseProvider):
    """Google AI Studio. Cliente compartido con los embeddings.

    Medido: ``gemini-3.5-flash-lite`` no gasta tokens de razonamiento
    (``thoughts_token_count`` = 0), asi que no hay ``thinking_config`` que
    ajustar; ponerlo a ``thinking_budget=0`` ademas da 400 en los modelos 3.x,
    que usan ``thinking_level``.
    """

    nombre = GEMINI
    _CLIENTE = None

    @classmethod
    def cliente(cls):
        if cls._CLIENTE is None:
            clave = cls._api_key('GOOGLE_API_KEY')
            # El import va aqui dentro y no arriba: google.genai cuesta 8,7 s y
            # 113 MB de RSS en la Pi, y el proceso web no lo necesita.
            from google import genai
            cls._CLIENTE = genai.Client(api_key=clave)
        return cls._CLIENTE

    def complete(self, prompt):
        from google.genai import types

        try:
            respuesta = self.cliente().models.generate_content(
                model=self.model_name,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type='application/json',
                    response_schema=GEMINI_RESPONSE_SCHEMA,
                    temperature=0.3,
                ),
            )
        except Exception as e:
            raise _traducir_error_gemini(e) from e

        return _texto_de_gemini(respuesta)


class GroqProvider(BaseProvider):
    """Groq por su endpoint compatible con OpenAI.

    Se llama con ``requests``, que ya es dependencia, en vez de anadir un SDK:
    la Pi tiene 1 GB y cada import se paga en cada arranque del cron.
    """

    nombre = GROQ
    URL = 'https://api.groq.com/openai/v1/chat/completions'
    TIMEOUT = 60
    _LIMITER = None

    @classmethod
    def limiter(cls):
        if cls._LIMITER is None:
            cls._LIMITER = AIRateLimiter()
        return cls._LIMITER

    def complete(self, prompt):
        esfuerzo, max_tokens = razonamiento_de(self.model_name, self.setting)
        limiter = self.limiter()
        try:
            limiter.acquire(self.model_name, prompt, max_tokens)
        except AIRateLimiter.Deferred as e:
            raise AIProviderError('rate_limit', str(e), str(e)) from e

        cuerpo = {
            'model': self.model_name,
            'messages': [
                {'role': 'system',
                 'content': 'Eres un asistente que analiza noticias y responde '
                            'ÚNICAMENTE con JSON válido.'},
                {'role': 'user', 'content': prompt},
            ],
            'temperature': 0.3,
            'max_completion_tokens': max_tokens,
            'response_format': OPENAI_RESPONSE_FORMAT,
        }
        if esfuerzo:
            cuerpo['reasoning_effort'] = esfuerzo

        try:
            r = requests.post(
                self.URL,
                headers={'Authorization': 'Bearer ' + self._api_key('GROQ_API_KEY'),
                         'Content-Type': 'application/json'},
                json=cuerpo,
                timeout=self.TIMEOUT,
            )
        except requests.RequestException as e:
            raise AIProviderError('error', 'No se pudo contactar con Groq.', str(e)) from e

        limiter.update_from_headers(r.headers)

        if r.status_code != 200:
            raise _traducir_error_groq(r, limiter)

        try:
            datos = r.json()
            eleccion = datos['choices'][0]
        except (ValueError, KeyError, IndexError) as e:
            raise AIProviderError('error', 'Groq devolvió una respuesta inesperada.',
                                  r.text[:400]) from e

        if eleccion.get('finish_reason') == 'length':
            # El presupuesto no le dio: con razonamiento activo la respuesta no
            # llega recortada, llega sin JSON. Es un fallo de configuracion, no
            # del proveedor, asi que el respaldo tampoco lo arreglaria.
            raise AIProviderError(
                'error',
                f'La respuesta de {self.model_name} se truncó: '
                f'max_completion_tokens ({max_tokens}) se queda corto.',
                puede_reintentar_otro=False,
            )
        return eleccion.get('message', {}).get('content') or ''


# --- Razonamiento ------------------------------------------------------------
# Solo aplica a los modelos de Groq: el bloque de razonamiento se cobra dentro
# de max_completion_tokens, asi que un presupuesto corto no recorta el
# razonamiento, deja la respuesta truncada y SIN JSON. Medido en septiembre de
# 2026 sobre el prompt real: gpt-oss razona breve (~650 caracteres) y le sobra
# con 512. Al subir el esfuerzo hay que subir el presupuesto.
REASONING_MODELS = {
    'openai/gpt-oss-120b': {'effort': 'low', 'max_completion_tokens': 512},
}
DEFAULT_MAX_COMPLETION_TOKENS = 512
# Presupuesto minimo que necesita una respuesta con razonamiento por encima de
# 'low'. Medido: con 2.048 falla el 12% de las llamadas y con 4.096 ninguna.
MIN_REASONING_TOKENS = 4096


def razonamiento_de(model_name, setting=None):
    """Devuelve (reasoning_effort, max_completion_tokens) para un modelo.

    Manda lo que se haya elegido a mano en el admin; si esta en automatico se
    usa la tabla. El esfuerzo es None en los modelos que no razonan.
    """
    config = REASONING_MODELS.get(model_name) or {}
    esfuerzo = config.get('effort')
    max_tokens = config.get('max_completion_tokens', DEFAULT_MAX_COMPLETION_TOKENS)

    elegido = (getattr(setting, 'reasoning_effort', '') or '').strip()
    if elegido:
        # 'none' es una eleccion explicita de no razonar, no un "sin dato".
        esfuerzo = None if elegido == 'none' else elegido
        if esfuerzo and esfuerzo != 'low':
            # Al subir el esfuerzo a mano sin fijar presupuesto, se garantiza
            # el minimo medido para que el razonamiento quepa.
            max_tokens = max(max_tokens, MIN_REASONING_TOKENS)

    propio = getattr(setting, 'max_completion_tokens', None)
    if propio:
        max_tokens = propio
    return esfuerzo, max_tokens


# --- Traduccion de errores ---------------------------------------------------

def _traducir_error_gemini(error):
    texto = str(error)
    if 'RESOURCE_EXHAUSTED' in texto or '429' in texto:
        return AIProviderError(
            'quota',
            'Gemini agotó su cuota diaria de peticiones.',
            texto,
            retry_seconds=_segundos_de_retry(texto),
        )
    if '503' in texto or 'UNAVAILABLE' in texto:
        return AIProviderError('error', 'Gemini no está disponible ahora mismo.', texto)
    if '400' in texto or 'INVALID_ARGUMENT' in texto:
        # La peticion va mal construida: en Groq fallaria igual.
        return AIProviderError('error', 'Gemini rechazó la petición.', texto,
                               puede_reintentar_otro=False)
    return AIProviderError('error', 'Gemini devolvió un error al generar el resumen.', texto)


def _traducir_error_groq(respuesta, limiter):
    texto = respuesta.text or ''
    codigo = respuesta.status_code
    if codigo == 402:
        return AIProviderError('quota', 'La cuenta de Groq se quedó sin cuota (error 402). '
                                        'Hay que revisar el plan o la facturación.', texto)
    if codigo == 429:
        espera = _segundos_de_retry(texto) or _espera_por_cabeceras(respuesta.headers, limiter)
        ventana = limiter.tightest_tokens_window or limiter.tightest_requests_window
        nombres = {'minute': 'del minuto', 'hour': 'de la hora', 'day': 'del día'}
        detalle = nombres.get(ventana, '')
        larga = espera is not None and espera > 600
        if detalle:
            return AIProviderError('quota' if larga else 'rate_limit',
                                   f'Se agotó la cuota {detalle} de Groq.', texto, espera)
        return AIProviderError('rate_limit', 'Groq está limitando las peticiones por ritmo.',
                               texto, espera)
    if codigo >= 500:
        return AIProviderError('error', 'Groq devolvió un error interno.', texto)
    return AIProviderError('error', 'Groq devolvió un error al generar el resumen.', texto)


def _segundos_de_retry(texto):
    """Lee la espera del mensaje de error del proveedor.

    Groq la escribe compuesta ('try again in 10m46.27s'), asi que el parseo lo
    hace el limitador, que ya sabe de ese formato.
    """
    match = re.search(
        r'try again in ((?:[0-9.]+m)?[0-9.]+m?s?)', texto or '', re.IGNORECASE
    )
    if not match:
        return None
    segundos = AIRateLimiter().parse_reset_seconds(match.group(1))
    return max(1, int(segundos) + 1) if segundos is not None else None


def _espera_por_cabeceras(headers, limiter):
    retry_after = (headers or {}).get('retry-after') or (headers or {}).get('Retry-After')
    if retry_after:
        try:
            return max(1, int(float(retry_after)))
        except (TypeError, ValueError):
            pass
    esperas = [
        reset_en - time.monotonic()
        for restante, reset_en in (
            (limiter.remaining_tokens, limiter.reset_tokens_at),
            (limiter.remaining_requests, limiter.reset_requests_at),
        )
        if restante is not None and restante <= 0 and reset_en is not None
    ]
    return max(1, int(max(esperas)) + 1) if esperas else None


def _texto_de_gemini(respuesta):
    """Saca el texto de la respuesta sin el aviso de 'non-text parts'.

    Los modelos 3.x devuelven ademas un ``thought_signature``; leer
    ``respuesta.text`` funciona pero emite un warning por cada noticia, y son
    ~140 al dia en el log del cron.
    """
    candidatos = getattr(respuesta, 'candidates', None) or []
    for candidato in candidatos:
        partes = getattr(getattr(candidato, 'content', None), 'parts', None) or []
        texto = ''.join(
            p.text for p in partes
            if getattr(p, 'text', None) and not getattr(p, 'thought', False)
        )
        if texto.strip():
            return texto
    return getattr(respuesta, 'text', '') or ''


# --- Cadena de proveedores ---------------------------------------------------

_CLASES = {GEMINI: GeminiProvider, GROQ: GroqProvider}


def cadena_de_proveedores(setting=None):
    """Devuelve los proveedores a probar, en orden: primario y luego respaldo.

    El respaldo solo se usa cuando el primario se queda sin cuota, que es
    justo el caso que dejaba el feed pausado.
    """
    primario = (getattr(setting, 'provider', '') or DEFAULT_PROVIDER).strip()
    if primario not in _CLASES:
        logger.warning("Proveedor '%s' desconocido; se usa %s.", primario, DEFAULT_PROVIDER)
        primario = DEFAULT_PROVIDER

    modelo = (getattr(setting, 'model_name', '') or '').strip()
    cadena = [_CLASES[primario](modelo or None, setting)]

    respaldo = getattr(setting, 'fallback_provider', DEFAULT_FALLBACK)
    if respaldo is None:
        respaldo = DEFAULT_FALLBACK
    respaldo = (respaldo or '').strip()
    if respaldo and respaldo != primario and respaldo in _CLASES:
        # El respaldo siempre usa su modelo por defecto: el model_name del
        # admin pertenece al primario y no significa nada en el otro.
        cadena.append(_CLASES[respaldo](None, setting))
    return cadena

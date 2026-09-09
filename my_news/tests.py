from datetime import timedelta
import time
import uuid
from unittest.mock import patch
from types import SimpleNamespace

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.test import SimpleTestCase
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .models import AIModelSetting, FeedSource, News
from .ai_providers import (
    AIProviderError,
    AIRateLimiter,
    GeminiProvider,
    GroqProvider,
    _espera_por_cabeceras,
    _segundos_de_retry,
    cadena_de_proveedores,
    razonamiento_de,
)
from .services import FeedService
from .tasks import purge_old_news
from .views import NEWS_NOTIFICATION_SETTLE_DELAY, PAGE_SIZE, _collapse_html_whitespace


class FeedEntry(dict):
    def __getattr__(self, key):
        try:
            return self[key]
        except KeyError as exc:
            raise AttributeError(key) from exc


class FilterWordPatternTests(SimpleTestCase):
    def build_patterns(self, *words):
        filter_words = [
            SimpleNamespace(word=word, title_only=title_only)
            for word, title_only in words
        ]
        return FeedService.build_filter_word_patterns(filter_words)

    def test_filter_word_does_not_match_inside_another_word(self):
        patterns = self.build_patterns(('Andor', False))

        should_filter, filter_word = FeedService.should_filter_news(
            'La Tierra ha perdido su resplandor ambar',
            'El resplandor nocturno cambio por los LED.',
            patterns,
        )

        self.assertFalse(should_filter)
        self.assertIsNone(filter_word)

    def test_filter_word_matches_standalone_word(self):
        patterns = self.build_patterns(('Andor', False))

        should_filter, filter_word = FeedService.should_filter_news(
            'Andor tendra una nueva temporada',
            '',
            patterns,
        )

        self.assertTrue(should_filter)
        self.assertEqual(filter_word.word, 'Andor')

    def test_filter_phrase_matches_complete_phrase_only(self):
        patterns = self.build_patterns(('Star Wars', True))

        self.assertEqual(
            FeedService.should_filter_news('Nueva serie de Star Wars', '', patterns)[0],
            True,
        )
        self.assertEqual(
            FeedService.should_filter_news('Star Warships llega al cine', '', patterns)[0],
            False,
        )


class ContentPreparationTests(SimpleTestCase):
    def test_html_feed_content_is_converted_to_plain_text(self):
        content = '<p>El <a href="https://example.com">WiFi 7</a> llega a casa.</p><script>bad()</script>'

        cleaned = FeedService.prepare_content_for_ai('Titulo', content)

        self.assertEqual(cleaned, 'El WiFi 7 llega a casa.')

    def test_repeated_title_and_feed_byline_noise_are_removed(self):
        title = 'AMD avisa a sus socios'
        content = (
            'AMD avisa a sus socios Por Borja Rodríguez 30/06/2026 Hardware '
            'Según los últimos rumores, AMD prepara una subida de precio.'
        )

        cleaned = FeedService.prepare_content_for_ai(title, content)

        self.assertNotIn(title, cleaned)
        self.assertIn('Según los últimos rumores', cleaned)

    def test_vidaextra_header_noise_is_compacted(self):
        content = (
            '2026-06-30T14:00:34Z Sergio Cejas Editor Sergio Cejas Editor '
            'Linkedin twitter instagram 17772 publicaciones de Sergio Cejas '
            'Este verano nos van a faltar horas para jugar.'
        )

        cleaned = FeedService.prepare_content_for_ai('Splatoon Raiders', content)

        self.assertNotIn('Linkedin twitter instagram', cleaned)
        self.assertNotIn('17772 publicaciones', cleaned)
        self.assertIn('Este verano', cleaned)

    def test_content_is_limited_before_prompting(self):
        cleaned = FeedService.prepare_content_for_ai('Titulo', 'a' * 3000, content_limit=120)

        self.assertEqual(len(cleaned), 120)

    def test_default_limit_keeps_information_after_legacy_cutoff(self):
        content = ('Contexto introductorio sin el dato principal. ' * 75) + (
            'Dato decisivo ubicado después del antiguo límite.'
        )

        cleaned = FeedService.prepare_content_for_ai('Titulo', content)

        self.assertGreater(len(cleaned), 2500)
        self.assertIn('Dato decisivo', cleaned)

    def test_default_limit_caps_content_at_10000_characters(self):
        cleaned = FeedService.prepare_content_for_ai('Titulo', 'a' * 12000)

        self.assertEqual(len(cleaned), 10000)


class AIRateLimiterTests(SimpleTestCase):
    def setUp(self):
        self.limiter = AIRateLimiter()
        self.limiter.SAFE_RPM_CAP = 500
        GroqProvider._LIMITER = self.limiter

    def test_starting_limits_come_from_the_measured_free_plan(self):
        """MODEL_LIMITS es solo el valor de arranque, y viene de una medida.

        Septiembre de 2026, plan gratuito de Groq: gpt-oss-120b da 8.000 tokens
        por minuto. Mientras no llegan cabeceras se les aplica SAFETY_FACTOR,
        de ahi 6.000 y 22.
        """
        limiter = AIRateLimiter()

        self.assertEqual(limiter.MODEL_LIMITS['openai/gpt-oss-120b'], {'tpm': 8_000, 'rpm': 30})
        self.assertEqual(limiter.get_limits('openai/gpt-oss-120b'), (6_000, 22))

    def test_reset_header_duration_is_parsed(self):
        limiter = AIRateLimiter()

        self.assertEqual(limiter.parse_reset_seconds('7.66s'), 7.66)
        self.assertEqual(limiter.parse_reset_seconds('2m59.56s'), 179.56)

    def test_response_headers_update_remaining_capacity(self):
        limiter = AIRateLimiter()

        limiter.update_from_headers({
            'x-ratelimit-remaining-tokens-minute': '1234',
            'x-ratelimit-remaining-requests-day': '42',
            'x-ratelimit-limit-tokens-minute': '500000',
            'x-ratelimit-limit-requests-day': '1000000000',
            'x-ratelimit-reset-tokens-minute': '7.66s',
            'x-ratelimit-reset-requests-day': '2m59.56s',
        })

        self.assertEqual(limiter.remaining_tokens, 1234)
        self.assertEqual(limiter.remaining_requests, 42)
        self.assertEqual(limiter.limit_tokens, 500000)
        self.assertIsNotNone(limiter.reset_tokens_at)
        self.assertIsNotNone(limiter.reset_requests_at)

    def test_a_daily_cap_is_not_taken_as_the_per_minute_budget(self):
        """El margen del dia frena; su tope no alimenta el presupuesto local.

        El presupuesto razona en ventanas de 60 s, asi que leer 1.000.000.000
        al dia como si fuera por minuto autorizaria una rafaga sin freno. Hasta
        agosto de 2026 limit_requests caia al valor del dia y este test exigia
        justo eso; el refactor de tightest_window lo corrigio y la expectativa
        se quedo atras.
        """
        limiter = AIRateLimiter()

        limiter.update_from_headers({
            'x-ratelimit-remaining-requests-day': '42',
            'x-ratelimit-limit-requests-day': '1000000000',
        })

        self.assertEqual(limiter.remaining_requests, 42)
        self.assertIsNone(limiter.limit_requests)

    def test_a_per_minute_cap_does_feed_the_budget(self):
        limiter = AIRateLimiter()

        limiter.update_from_headers({'x-ratelimit-limit-requests-minute': '5'})

        # Al tope medido no se le aplica SAFETY_FACTOR: es exacto.
        self.assertEqual(limiter.limit_requests, 5)
        self.assertEqual(limiter.get_limits('openai/gpt-oss-120b')[1], 5)

    def test_the_tightest_window_wins_and_carries_its_own_reset(self):
        """Con el dia agotado hay que esperar al reset del dia, no al del minuto."""
        limiter = AIRateLimiter()

        limiter.update_from_headers({
            'x-ratelimit-remaining-requests-minute': '4',
            'x-ratelimit-reset-requests-minute': '10s',
            'x-ratelimit-remaining-requests-day': '0',
            'x-ratelimit-reset-requests-day': '2m30s',
        })
        falta = limiter.reset_requests_at - time.monotonic()

        self.assertEqual(limiter.remaining_requests, 0)
        self.assertEqual(limiter.tightest_requests_window, 'day')
        self.assertAlmostEqual(falta, 150, delta=2)

    def test_long_header_reset_defers_processing(self):
        limiter = AIRateLimiter()
        limiter.remaining_tokens = 1
        limiter.reset_tokens_at = limiter.window_start + 120

        with self.assertRaises(AIRateLimiter.Deferred):
            limiter.acquire('openai/gpt-oss-120b', 'x' * 1000, 1024)

    def test_missing_reset_header_uses_local_window(self):
        limiter = AIRateLimiter()
        limiter.remaining_requests = 0
        waits = []

        def fake_sleep_or_defer(wait_time, reason):
            waits.append((wait_time, reason))
            limiter.remaining_requests = None

        limiter._sleep_or_defer = fake_sleep_or_defer
        limiter.acquire('openai/gpt-oss-120b', 'prompt', 8)

        self.assertEqual(waits[0][1], 'sin requests disponibles')
        self.assertGreater(waits[0][0], 0)

    def test_local_window_reset_clears_stale_header_capacity_without_reset_header(self):
        limiter = AIRateLimiter()
        limiter.remaining_requests = 0
        limiter.window_start -= limiter.window_seconds + 1

        limiter.reset_if_needed()

        self.assertIsNone(limiter.remaining_requests)

    def test_retry_after_is_read_from_response_headers(self):
        headers = {'Retry-After': '42'}

        self.assertEqual(_espera_por_cabeceras(headers, self.limiter), 42)

    def test_retry_delay_is_read_from_rate_limit_headers(self):
        headers = {
            'x-ratelimit-remaining-tokens-minute': '0',
            'x-ratelimit-reset-tokens-minute': '11.38',
        }
        self.limiter.update_from_headers(headers)

        self.assertEqual(_espera_por_cabeceras(headers, self.limiter), 12)

    def test_retry_after_is_read_from_error_message(self):
        self.assertEqual(
            _segundos_de_retry('Rate limit reached. Please try again in 12.4s.'), 13
        )

    def test_retry_after_reads_minute_duration_from_error_message(self):
        """Groq escribe la espera compuesta: minutos y segundos juntos."""
        self.assertEqual(
            _segundos_de_retry('Rate limit reached. Please try again in 10m46.271999999s.'),
            647,
        )


class ProveedorFalso:
    """Proveedor de mentira: devuelve lo que se le diga o lanza lo que se le diga."""

    def __init__(self, nombre='falso', respuesta=None, error=None):
        self.nombre = nombre
        self.respuesta = respuesta
        self.error = error
        self.llamadas = []

    def complete(self, prompt):
        self.llamadas.append(prompt)
        if self.error is not None:
            raise self.error
        return self.respuesta


RESPUESTA_OK = '{"summary": "Resumen procesado.", "short_answer": null, "ai_filter": null}'


def _procesar(cadena, titulo='Titulo', contenido='Descripcion original'):
    """Ejecuta process_news_content con una cadena de proveedores fija."""
    with patch('my_news.services.cadena_de_proveedores', return_value=cadena):
        return FeedService.process_news_content(
            titulo, contenido, FeedService._DEFAULT_FILTER_INSTRUCTIONS,
        )


class NewsContentProcessingTests(SimpleTestCase):
    """La ruta que convierte una noticia en resumen, con proveedores de mentira."""

    def setUp(self):
        FeedService._clear_ai_failure()

    def test_a_good_response_becomes_summary_and_fields(self):
        proveedor = ProveedorFalso(respuesta=(
            '{"summary": "Resumen **con negrita**.", '
            '"short_answer": "El dato oculto.", "ai_filter": "futbol"}'
        ))
        resumen, short, filtro = _procesar([proveedor])

        self.assertIn('<strong>con negrita</strong>', resumen)
        self.assertEqual(short, 'El dato oculto.')
        self.assertEqual(filtro, 'futbol')
        self.assertIsNone(FeedService._LAST_AI_FAILURE)

    def test_a_provider_failure_returns_nothing_instead_of_original_content(self):
        """Nunca guardar el texto original como si fuera un resumen."""
        proveedor = ProveedorFalso(error=AIProviderError('rate_limit', 'sin ritmo'))
        self.assertEqual(_procesar([proveedor]), (None, None, None))

    def test_the_fallback_provider_takes_over_when_the_first_runs_out_of_quota(self):
        """El caso que motivo todo esto: sin cuota, seguir en vez de pausar."""
        primero = ProveedorFalso('gemini', error=AIProviderError('quota', 'sin cuota'))
        segundo = ProveedorFalso('groq', respuesta=RESPUESTA_OK)

        resumen, _, _ = _procesar([primero, segundo])

        self.assertEqual(resumen, 'Resumen procesado.')
        self.assertEqual(len(segundo.llamadas), 1)
        self.assertIsNone(FeedService._LAST_AI_FAILURE)

    def test_a_badly_built_request_does_not_bother_the_fallback(self):
        """Si la peticion va mal construida, en el otro proveedor fallaria igual."""
        primero = ProveedorFalso('gemini', error=AIProviderError(
            'error', 'peticion invalida', puede_reintentar_otro=False))
        segundo = ProveedorFalso('groq', respuesta=RESPUESTA_OK)

        self.assertEqual(_procesar([primero, segundo]), (None, None, None))
        self.assertEqual(segundo.llamadas, [])

    def test_the_reported_failure_is_the_last_one(self):
        primero = ProveedorFalso('gemini', error=AIProviderError('quota', 'gemini sin cuota'))
        segundo = ProveedorFalso('groq', error=AIProviderError('quota', 'groq sin cuota'))

        _procesar([primero, segundo])

        self.assertEqual(FeedService._LAST_AI_FAILURE['kind'], 'quota')
        self.assertEqual(FeedService._LAST_AI_FAILURE['reason'], 'groq sin cuota')

    def test_an_unexpected_crash_in_one_provider_does_not_stop_the_chain(self):
        primero = ProveedorFalso('gemini', error=RuntimeError('algo raro'))
        segundo = ProveedorFalso('groq', respuesta=RESPUESTA_OK)

        resumen, _, _ = _procesar([primero, segundo])
        self.assertEqual(resumen, 'Resumen procesado.')

    def test_an_empty_response_is_not_saved_as_summary(self):
        self.assertEqual(_procesar([ProveedorFalso(respuesta='   ')]), (None, None, None))

    def test_a_non_json_response_is_not_saved_as_summary(self):
        proveedor = ProveedorFalso(respuesta='Lo siento, no puedo ayudarte con eso.')
        self.assertEqual(_procesar([proveedor]), (None, None, None))

    def test_json_wrapped_in_reasoning_text_is_extracted(self):
        """Algunos modelos anteponen su razonamiento al JSON."""
        proveedor = ProveedorFalso(
            respuesta='Vale, primero analizo el titular y luego respondo.\n' + RESPUESTA_OK)
        resumen, _, _ = _procesar([proveedor])
        self.assertEqual(resumen, 'Resumen procesado.')

    def test_a_missing_summary_falls_back_to_the_original_text(self):
        proveedor = ProveedorFalso(
            respuesta='{"summary": null, "short_answer": null, "ai_filter": null}')
        resumen, _, _ = _procesar([proveedor], contenido='Texto original de la noticia.')
        self.assertIn('Texto original', resumen)


class ReasoningConfigTests(SimpleTestCase):
    """El razonamiento y su presupuesto, que van juntos a la fuerza."""

    def test_reasoning_models_get_a_budget_that_fits_their_reasoning(self):
        """El razonamiento se cobra dentro de max_completion_tokens.

        Si el presupuesto no le da, la respuesta no llega recortada: llega
        truncada y SIN JSON, y la noticia se pierde. Medido en septiembre de
        2026 sobre el prompt real: gpt-oss razona ~650 caracteres y le sobra
        con 512.
        """
        self.assertEqual(razonamiento_de('openai/gpt-oss-120b'), ('low', 512))

        # Un modelo que no esta en la tabla no recibe reasoning_effort.
        self.assertEqual(razonamiento_de('gemini-3.5-flash-lite'), (None, 512))

    def test_admin_setting_overrides_the_table(self):
        # 'none' es una eleccion explicita de no razonar, no un "sin dato".
        ajuste = AIModelSetting(reasoning_effort='none')
        self.assertEqual(razonamiento_de('openai/gpt-oss-120b', ajuste), (None, 512))

        # Al subir el esfuerzo sin fijar presupuesto se garantiza el minimo.
        ajuste = AIModelSetting(reasoning_effort='high')
        esfuerzo, tokens = razonamiento_de('openai/gpt-oss-120b', ajuste)
        self.assertEqual(esfuerzo, 'high')
        self.assertGreaterEqual(tokens, AIModelSetting.MIN_REASONING_TOKENS)

        # Un presupuesto propio manda sobre todo lo demas.
        ajuste = AIModelSetting(reasoning_effort='low', max_completion_tokens=8192)
        self.assertEqual(razonamiento_de('openai/gpt-oss-120b', ajuste), ('low', 8192))

        # En automatico (cadena vacia) se respeta la tabla.
        self.assertEqual(
            razonamiento_de('openai/gpt-oss-120b', AIModelSetting(reasoning_effort='')),
            ('low', 512),
        )

    def test_admin_refuses_reasoning_with_a_budget_that_does_not_fit(self):
        """La combinacion que rompe la ingesta en silencio no se puede guardar."""
        ajuste = AIModelSetting(reasoning_effort='high', max_completion_tokens=512)
        with self.assertRaises(ValidationError) as ctx:
            ajuste.full_clean()
        self.assertIn('max_completion_tokens', ctx.exception.error_dict)

        # Sin razonamiento, un presupuesto corto es legitimo.
        AIModelSetting(reasoning_effort='none', max_completion_tokens=512).full_clean()


class ProviderChainTests(SimpleTestCase):
    """Que proveedores se intentan y en que orden."""

    def test_defaults_are_gemini_with_groq_as_backup(self):
        cadena = cadena_de_proveedores(None)
        self.assertEqual([p.nombre for p in cadena], ['gemini', 'groq'])
        self.assertEqual(cadena[0].model_name, 'gemini-3.5-flash-lite')

    def test_the_admin_choice_decides_the_order(self):
        ajuste = AIModelSetting(provider='groq', model_name='', fallback_provider='gemini')
        cadena = cadena_de_proveedores(ajuste)
        self.assertEqual([p.nombre for p in cadena], ['groq', 'gemini'])
        # Sin model_name, cada proveedor usa el suyo.
        self.assertEqual(cadena[0].model_name, 'openai/gpt-oss-120b')

    def test_the_backup_can_be_switched_off(self):
        ajuste = AIModelSetting(provider='gemini', fallback_provider='')
        self.assertEqual(len(cadena_de_proveedores(ajuste)), 1)

    def test_an_unknown_provider_falls_back_to_the_default(self):
        ajuste = AIModelSetting(provider='inventado', fallback_provider='')
        self.assertEqual(cadena_de_proveedores(ajuste)[0].nombre, 'gemini')

    def test_the_backup_never_repeats_the_primary(self):
        ajuste = AIModelSetting(provider='groq', fallback_provider='groq')
        self.assertEqual(len(cadena_de_proveedores(ajuste)), 1)


class FeedIngestionBudgetTests(TestCase):
    def setUp(self):
        self.source = FeedSource.objects.create(
            name='Budget Feed',
            url='https://example.com/rss.xml',
        )

    @patch('my_news.services.EmbeddingService.check_redundancy', return_value=(False, None, 0.0))
    @patch('my_news.services.FeedService.initialize_vector_index', return_value=None)
    @patch('my_news.services.FeedService.initialize_gemini', return_value=object())
    @patch('my_news.services.FeedService.process_news_content')
    @patch('my_news.services.feedparser.parse')
    @patch('my_news.services.requests.get')
    def test_ai_budget_does_not_drop_unprocessed_entries(
        self,
        mock_get,
        mock_parse,
        mock_process,
        _initialize_gemini,
        _initialize_vector_index,
        _check_redundancy,
    ):
        class Response:
            content = b'<rss></rss>'

            def raise_for_status(self):
                return None

        now = timezone.now()
        mock_get.return_value = Response()
        mock_parse.return_value.entries = [
            FeedEntry(
                id='budget-1',
                title='Primera noticia',
                link='https://example.com/budget-1',
                description='Descripcion primera',
                published_parsed=(now - timedelta(minutes=2)).utctimetuple(),
            ),
            FeedEntry(
                id='budget-2',
                title='Segunda noticia',
                link='https://example.com/budget-2',
                description='Descripcion segunda',
                published_parsed=(now - timedelta(minutes=1)).utctimetuple(),
            ),
        ]
        mock_process.return_value = ('Resumen IA', None, None)

        created_count = FeedService.fetch_and_save_news(max_ai_items=1)

        self.assertEqual(created_count, 1)
        self.assertEqual(mock_process.call_count, 1)

        first = News.objects.get(guid='budget-1')

        self.assertEqual(first.description, 'Resumen IA')
        self.assertTrue(first.is_ai_processed)
        self.assertFalse(News.objects.filter(guid='budget-2').exists())


class NewsFeedOrderingTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.source = FeedSource.objects.create(
            name='Test Feed',
            url='https://example.com/rss.xml',
        )
        cls.superuser = get_user_model().objects.create_superuser(
            username='news-admin',
            email='news-admin@example.com',
            password='test-pass-123',
        )

    def create_news_batch(self, count, *, prefix='news', published_dates=None):
        base_time = timezone.now()
        created = []

        for index in range(count):
            published_at = (
                published_dates[index]
                if published_dates is not None
                else base_time - timedelta(minutes=index)
            )
            created.append(
                News.objects.create(
                    title=f'{prefix} {index}',
                    description=f'Description for {prefix} {index}',
                    link=f'https://example.com/{prefix}/{index}',
                    published_date=published_at,
                    source=self.source,
                    guid=f'{prefix}-{uuid.uuid4().hex}-{index}',
                    is_ai_processed=True,
                )
            )

        return created

    def setUp(self):
        cache.clear()

    @patch('my_news.tasks.FeedService.initialize_vector_index', return_value=None)
    def test_purge_old_news_keeps_saved_articles(self, _initialize_vector_index):
        old_date = timezone.now() - timedelta(days=16)
        saved = self.create_news_batch(1, prefix='saved-old', published_dates=[old_date])[0]
        saved.is_saved = True
        saved.save(update_fields=['is_saved'])
        unsaved = self.create_news_batch(1, prefix='unsaved-old', published_dates=[old_date])[0]
        recent = self.create_news_batch(1, prefix='recent', published_dates=[timezone.now()])[0]

        removed = purge_old_news(days=15)

        self.assertEqual(removed, 1)
        self.assertTrue(News.objects.filter(pk=saved.pk).exists())
        self.assertFalse(News.objects.filter(pk=unsaved.pk).exists())
        self.assertTrue(News.objects.filter(pk=recent.pk).exists())

    def test_get_page_orders_descending_with_id_tiebreaker(self):
        self.client.force_login(self.superuser)
        same_time = timezone.now()
        older_time = same_time - timedelta(hours=1)

        self.create_news_batch(
            5,
            prefix='desc-order',
            published_dates=[same_time, same_time, older_time, older_time, older_time],
        )

        response = self.client.get(reverse('my_news:get_page'), {'order': 'desc', 'page': 1})
        payload = response.json()

        expected_ids = list(
            News.visible.order_by('-published_date', '-id').values_list('id', flat=True)
        )
        returned_ids = [card['id'] for card in payload['cards']]

        self.assertEqual(returned_ids, expected_ids)

    def test_get_page_orders_ascending_with_id_tiebreaker(self):
        self.client.force_login(self.superuser)
        same_time = timezone.now()
        newer_time = same_time + timedelta(hours=1)

        self.create_news_batch(
            5,
            prefix='asc-order',
            published_dates=[same_time, same_time, newer_time, newer_time, newer_time],
        )

        response = self.client.get(reverse('my_news:get_page'), {'order': 'asc', 'page': 1})
        payload = response.json()

        expected_ids = list(
            News.visible.order_by('published_date', 'id').values_list('id', flat=True)
        )
        returned_ids = [card['id'] for card in payload['cards']]

        self.assertEqual(returned_ids, expected_ids)

    def test_delete_returns_actual_page_replacement_and_undo_restores_original_page(self):
        self.client.force_login(self.superuser)
        self.create_news_batch(26, prefix='delete-flow')
        ordered_ids = list(
            News.visible.order_by('-published_date', '-id').values_list('id', flat=True)
        )
        deleted_id = ordered_ids[10]
        expected_replacement_id = ordered_ids[25]

        delete_response = self.client.post(
            reverse('my_news:delete_news', args=[deleted_id]),
            {
                'current_page': 1,
                'order': 'desc',
                'saved_only': 'false',
            },
        )
        delete_payload = delete_response.json()

        self.assertEqual(delete_payload['status'], 'success')
        self.assertEqual(delete_payload['card']['id'], expected_replacement_id)

        current_page_ids = [
            card['id']
            for card in self.client.get(
                reverse('my_news:get_page'),
                {'order': 'desc', 'page': 1},
            ).json()['cards']
        ]
        expected_after_delete = [news_id for news_id in ordered_ids if news_id != deleted_id][:25]
        self.assertEqual(current_page_ids, expected_after_delete)

        undo_response = self.client.post(
            reverse('my_news:undo_delete', args=[deleted_id]),
            {'saved_only': 'false'},
        )
        undo_payload = undo_response.json()

        self.assertEqual(undo_payload['status'], 'success')
        self.assertEqual(undo_payload['card']['id'], deleted_id)

        restored_page_ids = [
            card['id']
            for card in self.client.get(
                reverse('my_news:get_page'),
                {'order': 'desc', 'page': 1},
            ).json()['cards']
        ]
        self.assertEqual(restored_page_ids, ordered_ids[:25])

    def test_latest_deleted_endpoint_recovers_undo_after_page_reload(self):
        self.client.force_login(self.superuser)
        self.create_news_batch(26, prefix='latest-deleted-flow')
        ordered_ids = list(
            News.visible.order_by('-published_date', '-id').values_list('id', flat=True)
        )
        deleted_id = ordered_ids[8]

        delete_response = self.client.post(
            reverse('my_news:delete_news', args=[deleted_id]),
            {
                'current_page': 1,
                'order': 'desc',
                'saved_only': 'false',
            },
        )
        self.assertEqual(delete_response.json()['status'], 'success')

        latest_response = self.client.get(
            reverse('my_news:latest_deleted_news'),
            {'saved_only': 'false'},
        )
        latest_payload = latest_response.json()

        self.assertEqual(latest_payload['status'], 'success')
        self.assertEqual(latest_payload['news_id'], deleted_id)
        self.assertEqual(latest_payload['card']['id'], deleted_id)

        undo_response = self.client.post(
            reverse('my_news:undo_delete', args=[latest_payload['news_id']]),
            {'saved_only': 'false'},
        )
        self.assertEqual(undo_response.json()['status'], 'success')
        self.assertFalse(News.objects.get(pk=deleted_id).is_deleted)
        self.assertIsNone(News.objects.get(pk=deleted_id).deleted_at)

    def test_latest_deleted_endpoint_returns_empty_without_deleted_news(self):
        self.client.force_login(self.superuser)
        self.create_news_batch(2, prefix='no-deleted-flow')

        response = self.client.get(
            reverse('my_news:latest_deleted_news'),
            {'saved_only': 'false'},
        )

        self.assertEqual(response.json()['status'], 'empty')

    def test_delete_respects_search_filter_when_computing_replacement(self):
        self.client.force_login(self.superuser)
        base_time = timezone.now()
        matching_dates = [base_time - timedelta(minutes=index) for index in range(26)]
        non_matching_dates = [base_time - timedelta(days=1, minutes=index) for index in range(3)]

        self.create_news_batch(26, prefix='query-hit', published_dates=matching_dates)
        self.create_news_batch(3, prefix='query-miss', published_dates=non_matching_dates)

        filtered_ids = list(
            News.visible.filter(title__icontains='query-hit')
            .order_by('-published_date', '-id')
            .values_list('id', flat=True)
        )
        deleted_id = filtered_ids[5]
        expected_replacement_id = filtered_ids[25]

        delete_response = self.client.post(
            reverse('my_news:delete_news', args=[deleted_id]),
            {
                'current_page': 1,
                'order': 'desc',
                'saved_only': 'false',
                'q': 'query-hit',
            },
        )
        delete_payload = delete_response.json()

        self.assertEqual(delete_payload['status'], 'success')
        self.assertEqual(delete_payload['total_news'], 25)
        self.assertEqual(delete_payload['card']['id'], expected_replacement_id)

        current_page_ids = [
            card['id']
            for card in self.client.get(
                reverse('my_news:get_page'),
                {'order': 'desc', 'page': 1, 'q': 'query-hit'},
            ).json()['cards']
        ]
        expected_after_delete = [news_id for news_id in filtered_ids if news_id != deleted_id][:25]
        self.assertEqual(current_page_ids, expected_after_delete)

    def test_template_pagination_keeps_order_and_search_query(self):
        self.create_news_batch(26, prefix='foo-news')

        self.client.force_login(self.superuser)
        response = self.client.get(
            reverse('my_news:news_list'),
            {'order': 'asc', 'q': 'foo-news'},
        )

        self.assertContains(response, '?page=2&order=asc')
        self.assertContains(response, 'q=foo-news')

    def test_public_news_view_shows_latest_created_day_and_ignores_personal_delete_flag(self):
        latest_created_time = timezone.now() - timedelta(days=38)
        previous_created_time = latest_created_time - timedelta(days=1)
        latest_published_time = latest_created_time - timedelta(days=3)
        previous_published_time = latest_published_time + timedelta(hours=1)
        latest_date = timezone.localtime(latest_created_time).date()

        latest_public_news = News.objects.create(
            title='public latest',
            description='Visible en la fecha mas reciente',
            link='https://example.com/public-latest',
            published_date=latest_published_time,
            source=self.source,
            guid=f'public-latest-{uuid.uuid4().hex}',
            is_deleted=True,
            is_ai_processed=True,
        )
        previous_public_news = News.objects.create(
            title='public previous',
            description='No visible porque es de un dia anterior',
            link='https://example.com/public-previous',
            published_date=previous_published_time,
            source=self.source,
            guid=f'public-previous-{uuid.uuid4().hex}',
            is_ai_processed=True,
        )
        News.objects.filter(pk=latest_public_news.pk).update(created_at=latest_created_time)
        News.objects.filter(pk=previous_public_news.pk).update(created_at=previous_created_time)
        latest_public_news.refresh_from_db()

        response = self.client.get(reverse('my_news:news_list'))

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'news_public.html')
        self.assertTrue(response.context['public_news_mode'])
        self.assertContains(response, 'Noticias de Hoy')
        self.assertContains(response, 'public latest')
        self.assertNotContains(response, 'public previous')
        self.assertContains(response, f'id="public-news-{latest_public_news.id}"')
        self.assertContains(response, 'delete-btn')
        self.assertNotContains(response, 'save-btn')
        self.assertEqual(list(response.context['object_list']), [latest_public_news])
        self.assertEqual(response.context['public_news_date'], latest_date.strftime('%d/%m/%Y'))
        self.assertEqual(response.context['public_storage_key'], f'public-news-hidden:{latest_date.isoformat()}')

    def test_public_news_view_applies_editorial_filters_and_uses_latest_created_day(self):
        latest_time = timezone.now()
        publishable_time = latest_time - timedelta(days=1)
        publishable = News.objects.create(
            title='public publishable',
            description='Visible para visitantes',
            link='https://example.com/public-publishable',
            published_date=publishable_time,
            source=self.source,
            guid=f'public-publishable-{uuid.uuid4().hex}',
            is_ai_processed=True,
        )

        filtered_states = (
            {'is_filtered': True},
            {'is_ai_filtered': True},
            {'is_redundant': True},
        )
        for index, state in enumerate(filtered_states):
            News.objects.create(
                title=f'public filtered {index}',
                description='No debe aparecer para visitantes',
                link=f'https://example.com/public-filtered-{index}',
                published_date=latest_time - timedelta(minutes=index),
                source=self.source,
                guid=f'public-filtered-{uuid.uuid4().hex}-{index}',
                **state,
            )

        response = self.client.get(reverse('my_news:news_list'))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(list(response.context['object_list']), [publishable])
        self.assertEqual(
            response.context['public_news_date'],
            timezone.localdate().strftime('%d/%m/%Y'),
        )
        self.assertContains(response, 'public publishable')
        self.assertNotContains(response, 'public filtered')

    def test_public_news_view_includes_items_created_today_with_older_publish_dates(self):
        created_today = timezone.now()
        old_published_time = created_today - timedelta(days=2)
        older_public_news = News.objects.create(
            title='created today but published earlier',
            description='Debe salir porque entro al feed hoy',
            link='https://example.com/created-today-published-earlier',
            published_date=old_published_time,
            source=self.source,
            guid=f'created-today-published-earlier-{uuid.uuid4().hex}',
            is_ai_processed=True,
        )

        response = self.client.get(reverse('my_news:news_list'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'created today but published earlier')
        self.assertContains(response, f'id="public-news-{older_public_news.id}"')
        self.assertEqual(response.context['total_news'], 1)

    def test_public_news_view_uses_private_page_size_pagination(self):
        base_time = timezone.now()
        published_dates = [base_time - timedelta(minutes=index) for index in range(PAGE_SIZE + 1)]
        public_news = self.create_news_batch(
            PAGE_SIZE + 1,
            prefix='public-page',
            published_dates=published_dates,
        )

        response = self.client.get(reverse('my_news:news_list'))

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context['is_paginated'])
        self.assertEqual(len(response.context['page_obj']), PAGE_SIZE)
        self.assertContains(response, f'data-total-news="{PAGE_SIZE + 1}"')
        self.assertContains(response, '?page=2')
        self.assertContains(response, f'id="public-news-{public_news[0].id}"')
        self.assertNotContains(response, f'id="public-news-{public_news[-1].id}"')
        self.assertEqual(response.context['total_news'], PAGE_SIZE + 1)

        page_two_response = self.client.get(reverse('my_news:news_list'), {'page': 2})

        self.assertEqual(len(page_two_response.context['page_obj']), 1)
        self.assertContains(page_two_response, f'id="public-news-{public_news[-1].id}"')
        self.assertContains(page_two_response, '?page=1')

    def test_public_news_view_paginates_personally_deleted_news(self):
        base_time = timezone.now()
        public_news = self.create_news_batch(
            PAGE_SIZE + 2,
            prefix='public-deleted-page',
            published_dates=[base_time - timedelta(minutes=index) for index in range(PAGE_SIZE + 2)],
        )
        News.objects.filter(pk__in=[item.pk for item in public_news]).update(
            is_deleted=True,
            deleted_at=timezone.now(),
        )

        response = self.client.get(reverse('my_news:news_list'))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['total_news'], PAGE_SIZE + 2)
        self.assertEqual(len(response.context['page_obj']), PAGE_SIZE)
        self.assertContains(response, f'id="public-news-{public_news[0].id}"')

        page_two_response = self.client.get(reverse('my_news:news_list'), {'page': 2})

        self.assertEqual(len(page_two_response.context['page_obj']), 2)
        self.assertContains(page_two_response, f'id="public-news-{public_news[-1].id}"')

    def test_private_json_endpoint_requires_superuser(self):
        response = self.client.get(reverse('my_news:get_page'), {'page': 1, 'order': 'desc'})
        self.assertEqual(response.status_code, 302)
        self.assertIn('/noticias/login/', response['Location'])

    def test_check_new_news_waits_until_news_is_settled(self):
        self.client.force_login(self.superuser)
        baseline = self.create_news_batch(1, prefix='baseline')[0]
        settled_time = timezone.now() - NEWS_NOTIFICATION_SETTLE_DELAY - timedelta(seconds=5)
        News.objects.filter(pk=baseline.pk).update(created_at=settled_time)
        cursor = f'{settled_time.isoformat()}|{baseline.id}'

        fresh = News.objects.create(
            title='fresh visible',
            description='Not ready for notification yet',
            link='https://example.com/fresh-visible',
            published_date=timezone.now(),
            source=self.source,
            guid=f'fresh-visible-{uuid.uuid4().hex}',
            is_ai_processed=True,
        )

        response = self.client.get(reverse('my_news:check_new_news'), {'cursor': cursor})
        payload = response.json()

        self.assertEqual(payload['status'], 'success')
        self.assertEqual(payload['news_cards'], [])
        self.assertEqual(payload['cursor'], cursor)

        fresh_settled_time = timezone.now() - NEWS_NOTIFICATION_SETTLE_DELAY - timedelta(seconds=1)
        News.objects.filter(pk=fresh.pk).update(created_at=fresh_settled_time)

        response = self.client.get(reverse('my_news:check_new_news'), {'cursor': cursor})
        payload = response.json()

        self.assertEqual([card['id'] for card in payload['news_cards']], [fresh.id])
        self.assertEqual(payload['cursor'], f'{fresh_settled_time.isoformat()}|{fresh.id}')

    def test_check_new_news_does_not_notify_filtered_news(self):
        self.client.force_login(self.superuser)
        baseline = self.create_news_batch(1, prefix='filtered-baseline')[0]
        settled_time = timezone.now() - NEWS_NOTIFICATION_SETTLE_DELAY - timedelta(seconds=5)
        News.objects.filter(pk=baseline.pk).update(created_at=settled_time)
        cursor = f'{settled_time.isoformat()}|{baseline.id}'

        filtered = News.objects.create(
            title='filtered new item',
            description='Should never be notified',
            link='https://example.com/filtered-new-item',
            published_date=timezone.now(),
            source=self.source,
            guid=f'filtered-new-item-{uuid.uuid4().hex}',
            is_filtered=True,
        )
        News.objects.filter(pk=filtered.pk).update(
            created_at=timezone.now() - NEWS_NOTIFICATION_SETTLE_DELAY - timedelta(seconds=1)
        )

        response = self.client.get(reverse('my_news:check_new_news'), {'cursor': cursor})
        payload = response.json()

        self.assertEqual(payload['status'], 'success')
        self.assertEqual(payload['news_cards'], [])
        self.assertEqual(payload['cursor'], cursor)


class NewsCardSingleSourceTests(TestCase):
    """La tarjeta que llega por JSON y la que pinta la pagina son la misma.

    El marcado estuvo duplicado en ``news_card.html`` y en ``renderNewsCardHTML``
    (news_script.js), y las dos copias divergieron: al boton de guardar del JS le
    faltaba ``type="button"`` y el ``alt`` de la imagen sin portada no coincidia.
    Ahora el servidor renderiza la plantilla tambien para el JSON; estos tests
    fallan si alguien vuelve a construir el marcado por otro lado.
    """

    @classmethod
    def setUpTestData(cls):
        cls.source = FeedSource.objects.create(
            name='Fuente Tarjeta',
            url='https://example.com/tarjeta.xml',
        )
        cls.superuser = get_user_model().objects.create_superuser(
            username='card-admin',
            email='card-admin@example.com',
            password='test-pass-123',
        )

    def setUp(self):
        cache.clear()

    def make_news(self, count=1, prefix='tarjeta'):
        base = timezone.now()
        return [
            News.objects.create(
                title=f'{prefix} {i}',
                description=f'Descripcion de {prefix} {i}',
                link=f'https://example.com/{prefix}/{i}',
                published_date=base - timedelta(minutes=i),
                source=self.source,
                guid=f'{prefix}-{uuid.uuid4().hex}-{i}',
                is_ai_processed=True,
            )
            for i in range(count)
        ]

    def test_json_card_is_the_same_markup_as_the_rendered_page(self):
        self.client.force_login(self.superuser)
        self.make_news()

        page = self.client.get(reverse('my_news:news_list'))
        payload = self.client.get(reverse('my_news:get_page'), {'page': 1}).json()

        # El JSON viaja sin la sangria de la plantilla, asi que se compara
        # contra la pagina pasada por el mismo colapso: lo que se exige es que
        # el marcado sea el mismo, no que lleve los mismos espacios.
        self.assertIn(
            payload['cards'][0]['html'],
            _collapse_html_whitespace(page.content.decode()),
        )

    def test_json_card_carries_html_and_the_stamps_the_frontend_reads(self):
        self.client.force_login(self.superuser)
        article = self.make_news()[0]

        card = self.client.get(reverse('my_news:get_page'), {'page': 1}).json()['cards'][0]

        self.assertEqual(sorted(card), ['created_at', 'html', 'id', 'published_at'])
        self.assertEqual(card['id'], article.id)
        self.assertEqual(card['published_at'], article.published_date.isoformat())
        self.assertIn(f'data-news-id="{article.id}"', card['html'])
        self.assertIn(f'id="news-{article.id}"', card['html'])

    def test_delete_button_follows_is_staff_and_ignores_another_users_cache(self):
        self.make_news()
        sin_staff = get_user_model().objects.create_user(
            username='sin-staff',
            password='test-pass-123',
            is_superuser=True,
            is_staff=False,
        )

        self.client.force_login(self.superuser)
        con = self.client.get(reverse('my_news:get_page'), {'page': 1}).json()['cards'][0]['html']
        self.client.force_login(sin_staff)
        sin = self.client.get(reverse('my_news:get_page'), {'page': 1}).json()['cards'][0]['html']

        self.assertIn('delete-btn', con)
        self.assertNotIn('delete-btn', sin)

    def test_replacement_card_after_delete_also_ships_html(self):
        self.client.force_login(self.superuser)
        articles = self.make_news(PAGE_SIZE + 1, prefix='reemplazo')

        response = self.client.post(
            reverse('my_news:delete_news', args=[articles[0].id]),
            {'page': 1, 'order': 'desc'},
        )

        self.assertIn('news-card-container', response.json()['card']['html'])

class GeminiThinkingTests(SimpleTestCase):
    """El nivel de pensamiento solo se manda si se ha elegido uno."""

    def _config_enviada(self, ajuste):
        capturado = {}

        class ModelosFalsos:
            def generate_content(self, model, contents, config):
                capturado['config'] = config
                return SimpleNamespace(candidates=[], text=RESPUESTA_OK)

        cliente = SimpleNamespace(models=ModelosFalsos())
        with patch.object(GeminiProvider, 'cliente', classmethod(lambda cls: cliente)):
            GeminiProvider(setting=ajuste).complete('prompt')
        return capturado['config']

    def test_no_thinking_config_is_sent_by_default(self):
        """Sin elegir nivel, no se toca: el modelo trae el suyo."""
        config = self._config_enviada(AIModelSetting())
        self.assertIsNone(getattr(config, 'thinking_config', None))

    def test_the_chosen_level_reaches_the_request(self):
        config = self._config_enviada(AIModelSetting(thinking_level='HIGH'))
        self.assertEqual(config.thinking_config.thinking_level, 'HIGH')

    def test_groq_ignores_the_thinking_level(self):
        """thinking_level es de Gemini; el razonamiento de Groq va aparte."""
        self.assertEqual(
            razonamiento_de('openai/gpt-oss-120b', AIModelSetting(thinking_level='HIGH')),
            ('low', 512),
        )

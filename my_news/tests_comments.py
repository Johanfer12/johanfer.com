import json
import uuid
from unittest.mock import Mock, patch

import requests
from django.core.cache import cache
from django.test import SimpleTestCase, TestCase
from django.urls import reverse
from django.utils import timezone

from .comment_extractors import (
    CommentExtractionError,
    ElChapuzasDisqusCommentExtractor,
    WebediaCommentExtractor,
    WowheadCommentExtractor,
    get_comment_extractor,
    supports_comment_extraction,
)
from .models import FeedSource, News


def response_with_text(text):
    response = Mock()
    response.text = text
    response.raise_for_status.return_value = None
    return response


def response_with_http_error():
    response = Mock()
    response.raise_for_status.side_effect = requests.HTTPError('403 Client Error')
    return response


class CommentExtractorRegistryTests(SimpleTestCase):
    def test_registry_matches_supported_domains_and_subdomains(self):
        self.assertIsInstance(
            get_comment_extractor('https://www.xataka.com/historia/noticia'),
            WebediaCommentExtractor,
        )
        self.assertIsInstance(
            get_comment_extractor('https://www.3djuegos.com/noticias/noticia'),
            WebediaCommentExtractor,
        )
        self.assertIsInstance(
            get_comment_extractor('https://www.vidaextra.com/industria/noticia'),
            WebediaCommentExtractor,
        )
        self.assertIsInstance(
            get_comment_extractor('https://elchapuzasinformatico.com/noticia/'),
            ElChapuzasDisqusCommentExtractor,
        )
        self.assertIsInstance(
            get_comment_extractor('https://www.wowhead.com/news=382891/rutas'),
            WowheadCommentExtractor,
        )

    def test_registry_does_not_match_domain_suffix_attacks(self):
        self.assertFalse(supports_comment_extraction('https://xataka.com.example.org/noticia'))
        self.assertFalse(supports_comment_extraction('https://example.org/?next=xataka.com'))
        self.assertFalse(supports_comment_extraction('https://wowhead.com.example.org/noticia'))


class WebediaCommentExtractorTests(SimpleTestCase):
    @patch('my_news.comment_extractors.requests.get')
    def test_extracts_embedded_users_comments_and_replies(self, get_mock):
        embedded = {
            'comments': [
                {
                    'id': 7,
                    'user_name': 'Ada',
                    'content_filtered': '<p>Primer <strong>comentario</strong>.</p>',
                    'date': 1_700_000_000,
                    'parent': None,
                    'tree_level': 0,
                    'vote_count': 2,
                },
                {
                    'id': 8,
                    'user_name': 'Linus',
                    'content': 'Respuesta',
                    'date': 1_700_000_100,
                    'parent': 7,
                    'tree_level': 1,
                    'vote_count': 0,
                },
            ],
            'meta': {'totalCount': 2},
        }
        get_mock.return_value = response_with_text(
            f'<script>AML.Comments.config.data = {json.dumps(embedded)};</script>'
        )

        result = WebediaCommentExtractor().extract('https://www.xataka.com/prueba')

        self.assertEqual(result['source'], 'Webedia')
        self.assertEqual(result['total'], 2)
        self.assertEqual(result['comments'][0]['user'], 'Ada')
        self.assertEqual(result['comments'][0]['comment'], 'Primer\ncomentario\n.')
        self.assertEqual(result['comments'][0]['votes'], 2)
        self.assertIsNone(result['comments'][0]['upvotes'])
        self.assertIsNone(result['comments'][0]['downvotes'])
        self.assertEqual(result['comments'][1]['parent_id'], '7')
        self.assertEqual(result['comments'][1]['depth'], 1)


class ElChapuzasDisqusCommentExtractorTests(SimpleTestCase):
    @patch('my_news.comment_extractors.requests.get')
    def test_extracts_disqus_thread_data(self, get_mock):
        embed_vars = {
            'disqusShortname': 'elchapuzasinformatico',
            'disqusIdentifier': '123 https://example.test/?p=123',
            'disqusUrl': 'https://elchapuzasinformatico.com/noticia/',
            'disqusTitle': 'Noticia',
        }
        thread_data = {
            'cursor': {'total': 1},
            'response': {
                'posts': [{
                    'id': '55',
                    'raw_message': (
                        'Comentario desde Disqus '
                        'https://uploads.disquscdn.com/images/example.png'
                    ),
                    'createdAt': '2026-07-30T13:00:00',
                    'author': {'name': 'Grace'},
                    'parent': None,
                    'depth': 0,
                    'points': 3,
                    'likes': 4,
                    'dislikes': 1,
                    'isDeleted': False,
                    'media': [{
                        'resolvedUrl': 'https://uploads.disquscdn.com/images/example.png',
                        'thumbnailUrl': '//uploads.disquscdn.com/images/example-small.png',
                    }],
                }],
                'thread': {'posts': 1},
            },
        }
        get_mock.side_effect = [
            response_with_text(f'<script>var embedVars = {json.dumps(embed_vars)};</script>'),
            response_with_text(
                '<script type="text/json" id="disqus-threadData">'
                f'{json.dumps(thread_data)}</script>'
            ),
        ]

        result = ElChapuzasDisqusCommentExtractor().extract(
            'https://elchapuzasinformatico.com/noticia/'
        )

        self.assertEqual(result['source'], 'Disqus')
        self.assertEqual(result['total'], 1)
        self.assertEqual(result['comments'][0]['user'], 'Grace')
        self.assertEqual(result['comments'][0]['votes'], 3)
        self.assertEqual(result['comments'][0]['upvotes'], 4)
        self.assertEqual(result['comments'][0]['downvotes'], 1)
        self.assertEqual(result['comments'][0]['comment'], 'Comentario desde Disqus')
        self.assertEqual(
            result['comments'][0]['media'][0]['thumbnail_url'],
            'https://uploads.disquscdn.com/images/example-small.png',
        )
        self.assertIn('output=1', get_mock.call_args_list[0].args[0])
        self.assertEqual(get_mock.call_args_list[1].args[0], 'https://disqus.com/embed/comments/')

    @patch('my_news.comment_extractors.requests.get')
    def test_uses_article_guid_to_query_disqus_directly(self, get_mock):
        article_url = (
            'https://elchapuzasinformatico.com/2026/07/'
            'compra-geforce-rtx-5070-ti-recibe-botella-de-agua/'
        )
        thread_data = {
            'cursor': {'total': 1},
            'response': {
                'posts': [{
                    'id': '57',
                    'raw_message': 'En mi máquina &quot;funciona&quot;',
                    'createdAt': '2026-07-30T13:00:00',
                    'author': {'name': 'Grace'},
                    'parent': None,
                    'depth': 0,
                    'points': 1,
                    'likes': 1,
                    'dislikes': 0,
                    'isDeleted': False,
                }],
                'thread': {'posts': 1},
            },
        }
        get_mock.return_value = response_with_text(
            '<script type="text/json" id="disqus-threadData">'
            f'{json.dumps(thread_data)}</script>'
        )

        result = ElChapuzasDisqusCommentExtractor().extract(
            article_url,
            guid='https://elchapuzasinformatico.com/?p=662601',
            title='Compra una GeForce RTX 5070 Ti',
        )

        self.assertEqual(result['comments'][0]['comment'], 'En mi máquina "funciona"')
        self.assertEqual(get_mock.call_count, 1)
        self.assertEqual(get_mock.call_args.args[0], 'https://disqus.com/embed/comments/')
        self.assertEqual(
            get_mock.call_args.kwargs['params']['t_i'],
            '662601 https://elchapuzasinformatico.com/?p=662601',
        )

    @patch('my_news.comment_extractors.requests.get')
    def test_uses_rss_fallback_when_article_is_blocked(self, get_mock):
        article_url = (
            'https://elchapuzasinformatico.com/2026/07/'
            'compra-geforce-rtx-5070-ti-recibe-botella-de-agua/'
        )
        feed_xml = f'''<?xml version="1.0" encoding="UTF-8"?>
            <rss version="2.0">
                <channel>
                    <item>
                        <title>Compra una GeForce RTX 5070 Ti</title>
                        <link>{article_url}</link>
                        <guid isPermaLink="false">
                            https://elchapuzasinformatico.com/?p=662601
                        </guid>
                    </item>
                </channel>
            </rss>
        '''
        thread_data = {
            'cursor': {'total': 1},
            'response': {
                'posts': [{
                    'id': '56',
                    'raw_message': 'Comentario recuperado',
                    'createdAt': '2026-07-30T13:00:00',
                    'author': {'name': 'Ada'},
                    'parent': None,
                    'depth': 0,
                    'points': 1,
                    'likes': 1,
                    'dislikes': 0,
                    'isDeleted': False,
                }],
                'thread': {'posts': 1},
            },
        }
        get_mock.side_effect = [
            response_with_http_error(),
            response_with_text(feed_xml),
            response_with_text(
                '<script type="text/json" id="disqus-threadData">'
                f'{json.dumps(thread_data)}</script>'
            ),
        ]

        result = ElChapuzasDisqusCommentExtractor().extract(article_url)

        self.assertEqual(result['total'], 1)
        self.assertEqual(result['comments'][0]['comment'], 'Comentario recuperado')
        self.assertEqual(get_mock.call_args_list[1].args[0], 'https://elchapuzasinformatico.com/feed/')
        self.assertEqual(get_mock.call_args_list[2].kwargs['params']['t_i'], (
            '662601 https://elchapuzasinformatico.com/?p=662601'
        ))
        self.assertEqual(get_mock.call_args_list[2].kwargs['params']['t_u'], article_url)


class NewsCommentsViewTests(TestCase):
    def setUp(self):
        cache.clear()
        self.source = FeedSource.objects.create(
            name='Fuente',
            url='https://example.com/feed',
        )

    def create_news(self, *, link):
        return News.objects.create(
            title=f'Noticia {uuid.uuid4().hex}',
            description='Resumen',
            link=link,
            published_date=timezone.now(),
            source=self.source,
            guid=uuid.uuid4().hex,
            is_ai_processed=True,
        )

    def test_card_only_shows_comment_button_for_registered_extractors(self):
        supported = self.create_news(link='https://www.xataka.com/prueba')
        unsupported = self.create_news(link='https://example.com/prueba')

        response = self.client.get(reverse('my_news:news_list'))

        self.assertContains(
            response,
            reverse('my_news:news_comments', args=[supported.id]),
        )
        self.assertNotContains(
            response,
            reverse('my_news:news_comments', args=[unsupported.id]),
        )
        self.assertEqual(response.content.count(b'class="news-link icon-only comments-btn"'), 1)

    @patch('my_news.views.extract_comments')
    def test_endpoint_returns_normalized_comments(self, extract_mock):
        article = self.create_news(link='https://www.3djuegos.com/noticias/prueba')
        extract_mock.return_value = {
            'source': 'Webedia',
            'total': 1,
            'comments': [{
                'id': '1',
                'user': 'Usuario',
                'comment': 'Texto',
                'date': None,
                'parent_id': None,
                'depth': 0,
                'votes': 0,
            }],
        }

        response = self.client.get(reverse('my_news:news_comments', args=[article.id]))

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload['status'], 'success')
        self.assertEqual(payload['comments'][0]['user'], 'Usuario')
        self.assertEqual(payload['article_url'], article.link)
        self.assertEqual(response.headers['X-Comments-Cache'], 'MISS')
        self.assertIn('comments;dur=', response.headers['Server-Timing'])

        cached_response = self.client.get(reverse('my_news:news_comments', args=[article.id]))

        self.assertEqual(cached_response.status_code, 200)
        self.assertEqual(cached_response.headers['X-Comments-Cache'], 'HIT')
        extract_mock.assert_called_once_with(
            article.link,
            guid=article.guid,
            title=article.title,
        )

    def test_endpoint_rejects_unregistered_source(self):
        article = self.create_news(link='https://example.com/prueba')

        response = self.client.get(reverse('my_news:news_comments', args=[article.id]))

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()['status'], 'unsupported')


NL = chr(10)
CRNL = chr(13) + chr(10)
OPEN_Q = chr(171)
CLOSE_Q = chr(187)


def wowhead_page(comments, *, label=None, extra_listview=''):
    """Reproduce la página de Wowhead: botón con el total y el Listview."""
    toggle = ''
    if label is not None:
        toggle = f'<div data-show-label="{label}" id="comments-button-toggle-group"></div>'
    payload = json.dumps({'id': 'posts', 'template': 'news-comment', 'data': comments})
    return (
        f'{toggle}{extra_listview}'
        f'<div id="lv-posts"></div><script>new Listview({payload});</script>'
    )


class WowheadCommentExtractorTests(SimpleTestCase):
    ARTICLE_URL = 'https://www.wowhead.com/forever/news/tres-rutas-382891'

    @patch('my_news.comment_extractors.requests.get')
    def test_extracts_comments_from_the_article_listview(self, get_mock):
        get_mock.return_value = response_with_text(wowhead_page(
            [
                {
                    'id': 6418258,
                    'bodyPrefix': '[db=classicplus]',
                    'body': 'Noice. Honestly, the ironforge run is nostalgic.',
                    'date': '2026-09-15T09:07:26-05:00',
                    'user': 'Sp33dey',
                },
                {
                    'id': 6418259,
                    'body': 'Hopefully they add more Zeppelins',
                    'date': '2026-09-15T09:08:34-05:00',
                    'user': 'Dekabe',
                },
            ],
            label='Show 19 Comments',
        ))

        result = WowheadCommentExtractor().extract(self.ARTICLE_URL)

        self.assertEqual(result['source'], 'Wowhead')
        # El botón manda sobre el recuento: hay más comentarios paginados.
        self.assertEqual(result['total'], 19)
        self.assertEqual(len(result['comments']), 2)
        self.assertEqual(result['comments'][0]['id'], '6418258')
        self.assertEqual(result['comments'][0]['user'], 'Sp33dey')
        self.assertEqual(
            result['comments'][0]['comment'],
            'Noice. Honestly, the ironforge run is nostalgic.',
        )
        self.assertEqual(result['comments'][0]['date'], '2026-09-15T09:07:26-05:00')
        self.assertIsNone(result['comments'][0]['votes'])
        self.assertIsNone(result['comments'][0]['parent_id'])
        self.assertEqual(result['comments'][0]['depth'], 0)
        self.assertEqual(result['comments'][0]['media'], [])

    @patch('my_news.comment_extractors.requests.get')
    def test_uses_the_bot_user_agent_cloudfront_accepts(self, get_mock):
        get_mock.return_value = response_with_text(wowhead_page([]))

        WowheadCommentExtractor().extract(self.ARTICLE_URL)

        user_agent = get_mock.call_args.kwargs['headers']['User-Agent']
        self.assertIn('johanfer-news-bot', user_agent)
        self.assertNotIn('Chrome', user_agent)

    @patch('my_news.comment_extractors.requests.get')
    def test_ignores_listviews_that_are_not_comments(self, get_mock):
        other = '<script>new Listview({"id":"posts","template":"news","data":[{"id":1}]});</script>'
        get_mock.return_value = response_with_text(wowhead_page(
            [{'id': 7, 'body': 'El bueno', 'date': None, 'user': 'Ada'}],
            extra_listview=other,
        ))

        result = WowheadCommentExtractor().extract(self.ARTICLE_URL)

        self.assertEqual(len(result['comments']), 1)
        self.assertEqual(result['comments'][0]['comment'], 'El bueno')
        self.assertIsNone(result['comments'][0]['date'])

    @patch('my_news.comment_extractors.requests.get')
    def test_falls_back_to_the_listview_size_without_a_toggle_label(self, get_mock):
        get_mock.return_value = response_with_text(wowhead_page(
            [{'id': 7, 'body': 'Uno', 'user': 'Ada'}, {'id': 8, 'body': 'Dos', 'user': 'Linus'}],
        ))

        self.assertEqual(WowheadCommentExtractor().extract(self.ARTICLE_URL)['total'], 2)

    @patch('my_news.comment_extractors.requests.get')
    def test_rejects_pages_without_the_comments_listview(self, get_mock):
        get_mock.return_value = response_with_text('<div id="lv-posts"></div>')

        with self.assertRaises(CommentExtractionError):
            WowheadCommentExtractor().extract(self.ARTICLE_URL)

    @patch('my_news.comment_extractors.requests.get')
    def test_reports_a_blocked_article_as_a_controlled_error(self, get_mock):
        get_mock.return_value = response_with_http_error()

        with self.assertRaises(CommentExtractionError):
            WowheadCommentExtractor().extract(self.ARTICLE_URL)


class WowheadBBCodeTests(SimpleTestCase):
    """El cuerpo llega en BBCode, no en HTML como el resto de fuentes."""

    def extract_one(self, body):
        with patch('my_news.comment_extractors.requests.get') as get_mock:
            get_mock.return_value = response_with_text(wowhead_page(
                [{'id': 1, 'body': body, 'user': 'Ada'}],
            ))
            result = WowheadCommentExtractor().extract('https://www.wowhead.com/news=1/x')
        return result['comments'][0]['comment']

    def test_renders_a_quote_with_its_author(self):
        self.assertEqual(
            self.extract_one(
                '[quote=Dekabe]More Zeppelins[/quote]' + CRNL + CRNL + 'Should add Thunder Bluff'
            ),
            'Dekabe: ' + OPEN_Q + 'More Zeppelins' + CLOSE_Q + NL + NL + 'Should add Thunder Bluff',
        )

    def test_renders_nested_quotes_from_the_inside_out(self):
        self.assertEqual(
            self.extract_one('[quote=Ada][quote=Linus]Raiz[/quote]Medio[/quote]Fuera'),
            ('Ada: ' + OPEN_Q + 'Linus: ' + OPEN_Q + 'Raiz' + CLOSE_Q + NL + 'Medio'
             + CLOSE_Q + NL + 'Fuera'),
        )

    def test_keeps_the_label_of_a_link_and_drops_images(self):
        self.assertEqual(
            self.extract_one(
                'Mira [url=https://ejemplo.test/a]esto[/url] [img]https://x.test/i.png[/img]'
            ),
            'Mira esto',
        )

    def test_strips_remaining_markup_and_collapses_blank_lines(self):
        self.assertEqual(
            self.extract_one('[b]Negrita[/b]' + NL * 4 + 'Final'),
            'Negrita' + NL + NL + 'Final',
        )

    def test_skips_comments_left_empty_after_cleaning(self):
        with patch('my_news.comment_extractors.requests.get') as get_mock:
            get_mock.return_value = response_with_text(wowhead_page([
                {'id': 1, 'body': '[img]https://x.test/i.png[/img]', 'user': 'Ada'},
                {'id': 2, 'body': 'Con texto', 'user': 'Linus'},
            ]))
            result = WowheadCommentExtractor().extract('https://www.wowhead.com/news=1/x')

        self.assertEqual([c['id'] for c in result['comments']], ['2'])

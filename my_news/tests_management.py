from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .models import AIFilterInstruction, FeedSource, FilterWord, News


class FeedManagementTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_superuser(
            username='admin', email='admin@example.com', password='pass'
        )
        self.source = FeedSource.objects.create(
            name='Tecnología', url='https://example.com/feed.xml'
        )
        self.word_filter = FilterWord.objects.create(word='horóscopo')
        self.ai_filter = AIFilterInstruction.objects.create(
            instruction='Artículos de opinión muy sesgados'
        )

    def login(self):
        self.client.force_login(self.user)

    def test_management_requires_superuser(self):
        response = self.client.get(reverse('my_news:feed_management'))

        self.assertEqual(response.status_code, 302)
        self.assertIn('/noticias/login/', response.url)

        regular_user = get_user_model().objects.create_user('lector', password='pass')
        self.client.force_login(regular_user)
        response = self.client.post(reverse('my_news:source_toggle', args=[self.source.pk]))
        self.assertEqual(response.status_code, 302)
        self.source.refresh_from_db()
        self.assertTrue(self.source.active)

    def test_dashboard_lists_sources_and_both_filter_types(self):
        self.login()

        response = self.client.get(reverse('my_news:feed_management'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Tecnología')
        self.assertContains(response, 'horóscopo')
        self.assertContains(response, 'Artículos de opinión muy sesgados')
        self.assertNotContains(response, '/j_admin/')

        news_response = self.client.get(reverse('my_news:news_list'))
        self.assertContains(news_response, reverse('my_news:feed_management'))
        self.assertNotContains(news_response, '/j_admin/my_news/filterword/')

    def test_source_can_be_created_and_rejects_invalid_threshold(self):
        self.login()
        create_url = reverse('my_news:source_create')

        invalid = self.client.post(create_url, {
            'name': 'Inválida',
            'url': 'https://invalid.example/feed',
            'active': 'on',
            'similarity_threshold': '1.5',
        })
        self.assertEqual(invalid.status_code, 200)
        self.assertIn('similarity_threshold', invalid.context['form'].errors)
        self.assertFalse(FeedSource.objects.filter(name='Inválida').exists())

        valid = self.client.post(create_url, {
            'name': 'Ciencia',
            'url': 'https://science.example/feed',
            'active': 'on',
            'deep_search': 'on',
            'similarity_threshold': '0.88',
        })
        self.assertRedirects(
            valid, reverse('my_news:feed_management') + '#sources',
            fetch_redirect_response=False,
        )
        source = FeedSource.objects.get(name='Ciencia')
        self.assertTrue(source.active)
        self.assertTrue(source.deep_search)
        self.assertEqual(source.similarity_threshold, 0.88)

    def test_source_can_be_edited_and_toggled_only_by_post(self):
        self.login()
        edit_url = reverse('my_news:source_edit', args=[self.source.pk])
        response = self.client.post(edit_url, {
            'name': 'Tecnología diaria',
            'url': self.source.url,
            'active': 'on',
            'similarity_threshold': '0.91',
        })
        self.assertEqual(response.status_code, 302)
        self.source.refresh_from_db()
        self.assertEqual(self.source.name, 'Tecnología diaria')
        self.assertEqual(self.source.similarity_threshold, 0.91)

        toggle_url = reverse('my_news:source_toggle', args=[self.source.pk])
        self.assertEqual(self.client.get(toggle_url).status_code, 405)
        self.client.post(toggle_url)
        self.source.refresh_from_db()
        self.assertFalse(self.source.active)

    def test_word_and_ai_filters_can_be_created(self):
        self.login()

        word_response = self.client.post(reverse('my_news:word_filter_create'), {
            'word': 'rumor sin confirmar',
            'active': 'on',
            'title_only': 'on',
        })
        self.assertEqual(word_response.status_code, 302)
        word_filter = FilterWord.objects.get(word='rumor sin confirmar')
        self.assertTrue(word_filter.title_only)

        ai_response = self.client.post(reverse('my_news:ai_filter_create'), {
            'instruction': 'Contenido patrocinado sin identificar',
            'active': 'on',
        })
        self.assertEqual(ai_response.status_code, 302)
        self.assertTrue(
            AIFilterInstruction.objects.filter(
                instruction='Contenido patrocinado sin identificar', active=True
            ).exists()
        )

    def test_word_filter_can_be_edited_toggled_and_deleted(self):
        self.login()
        edit_url = reverse('my_news:word_filter_edit', args=[self.word_filter.pk])

        response = self.client.post(edit_url, {
            'word': 'astrología',
            'active': 'on',
            'title_only': 'on',
        })
        self.assertEqual(response.status_code, 302)
        self.word_filter.refresh_from_db()
        self.assertEqual(self.word_filter.word, 'astrología')
        self.assertTrue(self.word_filter.title_only)

        toggle_url = reverse('my_news:word_filter_toggle', args=[self.word_filter.pk])
        self.client.post(toggle_url)
        self.word_filter.refresh_from_db()
        self.assertFalse(self.word_filter.active)

        delete_url = reverse('my_news:word_filter_delete', args=[self.word_filter.pk])
        self.assertEqual(self.client.get(delete_url).status_code, 200)
        self.client.post(delete_url, {'confirmation': 'delete'})
        self.assertFalse(FilterWord.objects.filter(pk=self.word_filter.pk).exists())

    def test_ai_filter_can_be_edited_toggled_and_deleted(self):
        self.login()
        edit_url = reverse('my_news:ai_filter_edit', args=[self.ai_filter.pk])

        response = self.client.post(edit_url, {
            'instruction': 'Publicidad encubierta',
            'active': 'on',
        })
        self.assertEqual(response.status_code, 302)
        self.ai_filter.refresh_from_db()
        self.assertEqual(self.ai_filter.instruction, 'Publicidad encubierta')

        toggle_url = reverse('my_news:ai_filter_toggle', args=[self.ai_filter.pk])
        self.client.post(toggle_url)
        self.ai_filter.refresh_from_db()
        self.assertFalse(self.ai_filter.active)

        delete_url = reverse('my_news:ai_filter_delete', args=[self.ai_filter.pk])
        self.assertEqual(self.client.get(delete_url).status_code, 200)
        self.client.post(delete_url, {'confirmation': 'delete'})
        self.assertFalse(AIFilterInstruction.objects.filter(pk=self.ai_filter.pk).exists())

    def test_source_delete_warns_about_and_removes_related_news(self):
        self.login()
        News.objects.create(
            title='Noticia asociada', description='Texto',
            link='https://example.com/news', published_date=timezone.now(),
            source=self.source, guid='management-delete', is_ai_processed=True,
        )
        delete_url = reverse('my_news:source_delete', args=[self.source.pk])

        confirmation = self.client.get(delete_url)
        self.assertContains(confirmation, '<strong>1</strong>', html=True)
        self.assertContains(confirmation, 'noticias asociadas')

        rejected = self.client.post(delete_url, {})
        self.assertEqual(rejected.status_code, 400)
        self.assertTrue(FeedSource.objects.filter(pk=self.source.pk).exists())

        accepted = self.client.post(delete_url, {'confirmation': 'delete'})
        self.assertEqual(accepted.status_code, 302)
        self.assertFalse(FeedSource.objects.filter(pk=self.source.pk).exists())
        self.assertFalse(News.objects.filter(guid='management-delete').exists())

from django.apps import AppConfig


class HomePageConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'home_page'

    def ready(self):
        from . import signals  # noqa: F401

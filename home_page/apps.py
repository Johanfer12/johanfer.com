from django.apps import AppConfig


class HomePageConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'home_page'

    def ready(self):
        from . import signals  # noqa: F401
        # PRAGMAs de SQLite (WAL y compañía). Cuelgan de aquí porque hace
        # falta que las apps estén cargadas para conectar la señal, y esta es
        # la primera app propia de INSTALLED_APPS.
        from Bookshelf import db_pragmas  # noqa: F401

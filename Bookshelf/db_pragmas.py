"""PRAGMAs de SQLite aplicados a cada conexión nueva.

Va por señal y no por ``DATABASES['default']['OPTIONS']['init_command']``
porque ese ajuste para SQLite **existe desde Django 5.1** y producción corre
la 5.0: allí `sqlite3.connect()` recibe `init_command` como argumento
desconocido y la aplicación no arranca (ni siquiera `manage.py migrate`). La
señal funciona igual en las dos versiones.

Qué se ajusta y por qué. La base vive en la tarjeta SD de una Raspberry Pi,
así que lo que se optimiza son las escrituras, no la velocidad:

- ``journal_mode=WAL``: el modo por defecto ('delete') escribe cada
  transacción dos veces —al journal y a la base— y además crea y borra el
  fichero de journal en cada una. WAL escribe una sola vez, en un fichero que
  se reutiliza. Es persistente: queda grabado en la base, no por conexión.
- ``synchronous=NORMAL``: con WAL, el fsync solo ocurre en los checkpoints y
  no en cada commit. Es la combinación que recomienda SQLite para WAL. El
  riesgo que se acepta es perder las últimas transacciones si se va la luz,
  nunca corromper la base; aquí eso significa, como mucho, volver a bajar unas
  noticias en la siguiente pasada del cron.
- ``busy_timeout``: con WAL los lectores no bloquean al escritor, pero dos
  escritores sí compiten (gunicorn y el cron son procesos distintos). Esperar
  es mejor que devolver "database is locked".

OJO: WAL crea ``database.db-wal`` y ``database.db-shm`` junto a la base. Una
copia de seguridad tiene que llevarse los tres, o usar ``.backup`` de sqlite3,
que ya los consolida.
"""

from django.db.backends.signals import connection_created
from django.dispatch import receiver


@receiver(connection_created)
def aplicar_pragmas_sqlite(sender, connection, **kwargs):
    if connection.vendor != 'sqlite':
        return
    with connection.cursor() as cursor:
        cursor.execute('PRAGMA journal_mode=WAL;')
        cursor.execute('PRAGMA synchronous=NORMAL;')
        cursor.execute('PRAGMA temp_store=MEMORY;')
        cursor.execute('PRAGMA busy_timeout=5000;')

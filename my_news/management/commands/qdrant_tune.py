"""Ajusta la colección de Qdrant para la ventana larga en una Raspberry Pi.

    python manage.py qdrant_tune            # dice qué haría
    python manage.py qdrant_tune --apply

Hace falta **una vez**, porque la colección ya existe y estos parámetros solo
se aplican al crearla. Lo que ajusta, medido en la Pi con 28.000 puntos (un año
de noticias):

- **Cuantización escalar a int8.** Los vectores pasan de 86 MB a ~21 MB de
  memoria y la búsqueda baja de 31,2 ms a 25,3 ms: comparar enteros sale más
  barato que comparar flotantes. Sin esto, un año de ventana no cabe cómodo en
  el GB de la Pi.
- **``flush_interval_sec`` de 5 a 60.** Doce veces menos volcados del WAL a la
  tarjeta SD. Con ~77 vectores nuevos al día no hay nada que ganar volcando
  cada cinco segundos, y la SD se desgasta con cada escritura.

El índice HNSW no se toca: Qdrant lo construye solo al pasar de 10.000 puntos
(``indexing_threshold``), y tarda unos 6 minutos la primera vez.
"""

from django.core.management.base import BaseCommand

from my_news.services import FeedService


class Command(BaseCommand):
    help = "Aplica cuantización int8 y un flush más espaciado a la colección de Qdrant."

    def add_arguments(self, parser):
        parser.add_argument(
            '--apply',
            action='store_true',
            help='Aplica los cambios. Sin esto solo se informa del estado.',
        )
        parser.add_argument(
            '--flush-interval',
            type=int,
            default=60,
            help='Segundos entre volcados del WAL al disco (por defecto 60).',
        )

    def handle(self, *args, **options):
        indice = FeedService.initialize_vector_index()
        if indice is None:
            self.stderr.write(self.style.ERROR(
                'Qdrant no está disponible; no hay nada que ajustar.'
            ))
            return

        try:
            info = indice.client.get_collection(indice.collection)
        except Exception as exc:
            self.stderr.write(self.style.ERROR(f'No se pudo leer la colección: {exc}'))
            return

        cuantizacion = getattr(info.config, 'quantization_config', None)
        flush = getattr(info.config.optimizer_config, 'flush_interval_sec', None)

        self.stdout.write(f'Colección:   {indice.collection}')
        self.stdout.write(f'Puntos:      {info.points_count}')
        self.stdout.write(f'Indexados:   {info.indexed_vectors_count} (HNSW)')
        self.stdout.write(f'Cuantización:{" ninguna" if cuantizacion is None else " int8"}')
        self.stdout.write(f'Flush:       {flush} s')

        # Una mezcla de modelos no rompe nada visiblemente: las puntuaciones
        # simplemente dejan de significar lo que significaban.
        try:
            versiones = indice.model_version_counts()
        except Exception:
            versiones = {}
        if versiones:
            actual = indice.current_model_version()
            self.stdout.write('Modelos:')
            for version, n in sorted(versiones.items(), key=lambda x: -x[1]):
                marca = '  <- el de ahora' if version == actual else ''
                self.stdout.write(f'  {version:32} {n:6}{marca}')
            ajenos = sum(n for v, n in versiones.items() if v != actual)
            if ajenos:
                self.stdout.write(self.style.WARNING(
                    f'  {ajenos} puntos son de otro modelo y la búsqueda los ignora. '
                    'Son espacio ocupado sin uso: conviene reindexarlos o borrarlos.'
                ))

        if not options['apply']:
            pendiente = []
            if cuantizacion is None:
                pendiente.append('activar cuantización int8')
            if flush != options['flush_interval']:
                pendiente.append(f'poner el flush en {options["flush_interval"]} s')
            if pendiente:
                self.stdout.write('')
                self.stdout.write('Se haría: ' + '; '.join(pendiente))
                self.stdout.write('Repite con --apply para aplicarlo.')
            else:
                self.stdout.write('')
                self.stdout.write(self.style.SUCCESS('Ya está todo ajustado.'))
            return

        try:
            aplicado = indice.tune_for_scale(flush_interval_sec=options['flush_interval'])
        except Exception as exc:
            self.stderr.write(self.style.ERROR(f'No se pudo ajustar: {exc}'))
            return

        if not aplicado:
            self.stdout.write(self.style.SUCCESS('No hacía falta cambiar nada.'))
            return

        for clave, valor in aplicado.items():
            self.stdout.write(self.style.SUCCESS(f'  {clave} -> {valor}'))
        self.stdout.write('')
        self.stdout.write(
            'La cuantización se construye en segundo plano; con ~1.000 puntos '
            'tarda poco, con 28.000 fueron unos 3 minutos en la Pi.'
        )

import hashlib
import uuid
from typing import List, Optional

# qdrant-client se importa la primera vez que se instancia el servicio, no al
# cargar el modulo. Cuesta ~10 s y ~120 MB en la Pi, y el proceso web no toca
# Qdrant para servir una pagina: solo lo usan la ingesta y los comandos. Con el
# import arriba, gunicorn lo pagaba entero en cada arranque.
QdrantClient = None  # type: ignore
qm = None  # type: ignore


def _cargar_qdrant():
    """Deja QdrantClient y qm disponibles como globales del modulo.

    Los metodos de la clase usan ``qm.`` y solo se llaman sobre una instancia,
    asi que para entonces ``__init__`` ya paso por aqui.
    """
    global QdrantClient, qm
    if QdrantClient is None:
        from qdrant_client import QdrantClient as _Cliente
        from qdrant_client import models as _modelos
        QdrantClient, qm = _Cliente, _modelos


class VectorIndexUnavailable(Exception):
    pass


class VectorIndexService:
    """Wrapper mínimo para operar Qdrant sin silencios."""

    def __init__(self, url: str, collection: str, api_key: Optional[str] = None):
        try:
            _cargar_qdrant()
        except ImportError as exc:
            raise VectorIndexUnavailable(
                "qdrant-client no está instalado. Instálalo con 'pip install qdrant-client'."
            ) from exc
        self.client = QdrantClient(url=url, api_key=api_key)
        self.collection = collection
        # ``ensure_collection`` se llamaba una vez por noticia y cada llamada
        # era un ``get_collections()`` por HTTP: 8,2 ms medidos en la Pi, 70
        # veces por pasada. La colección no desaparece a mitad de una pasada,
        # así que basta comprobarlo una vez por proceso.
        self._collection_ready = False

    def ensure_collection(self, dim: int) -> None:
        """Crea la colección si no existe (lanza excepción en error)."""
        if self._collection_ready:
            return
        cols = self.client.get_collections().collections
        if any(c.name == self.collection for c in cols):
            self._collection_ready = True
            return
        self.client.create_collection(
            collection_name=self.collection,
            vectors_config=qm.VectorParams(size=dim, distance=qm.Distance.COSINE),
            # El payload en disco y los vectores cuantizados a int8 es lo que
            # hace que una ventana de un año quepa en el GB de la Pi.
            on_disk_payload=True,
            quantization_config=qm.ScalarQuantization(
                scalar=qm.ScalarQuantizationConfig(
                    type=qm.ScalarType.INT8, always_ram=True
                )
            ),
        )
        # Índices de payload usados en filtros
        self.client.create_payload_index(
            self.collection,
            field_name="published_ts",
            field_schema=qm.PayloadSchemaType.INTEGER,
        )
        self.client.create_payload_index(
            self.collection,
            field_name="is_filtered",
            field_schema=qm.PayloadSchemaType.BOOL,
        )
        self.client.create_payload_index(
            self.collection,
            field_name="is_redundant",
            field_schema=qm.PayloadSchemaType.BOOL,
        )
        self.client.create_payload_index(
            self.collection,
            field_name="source_id",
            field_schema=qm.PayloadSchemaType.INTEGER,
        )
        self.client.create_payload_index(
            self.collection,
            field_name="guid_hash",
            field_schema=qm.PayloadSchemaType.KEYWORD,
        )
        self._collection_ready = True

    @staticmethod
    def guid_hash(guid: str) -> str:
        return hashlib.sha256(guid.encode("utf-8")).hexdigest()

    def upsert(self, guid: str, vector: List[float], payload: dict) -> None:
        point_id = str(uuid.uuid5(uuid.NAMESPACE_URL, guid))
        point = qm.PointStruct(
            id=point_id,
            vector=vector,
            payload={
                "guid": guid,
                "guid_hash": self.guid_hash(guid),
                **payload,
            },
        )
        self.client.upsert(self.collection, points=[point])

    def delete(self, guid: str) -> None:
        point_id = str(uuid.uuid5(uuid.NAMESPACE_URL, guid))
        self.client.delete(self.collection, points_selector=qm.PointIdsList(points=[point_id]))

    def delete_many(self, guids: List[str]) -> int:
        point_ids = [
            str(uuid.uuid5(uuid.NAMESPACE_URL, guid))
            for guid in guids
            if guid
        ]
        if not point_ids:
            return 0
        self.client.delete(
            self.collection,
            points_selector=qm.PointIdsList(points=point_ids),
        )
        return len(point_ids)

    def tune_for_scale(self, flush_interval_sec: int = 60) -> dict:
        """Ajusta una colección ya creada para una ventana larga en una SD.

        Dos cosas distintas, las dos medidas en la Pi con 28.000 puntos:

        - La cuantización a int8 deja los vectores en la cuarta parte de
          memoria (86 MB -> 21 MB) y encima acelera la búsqueda (31,2 ms ->
          25,3 ms), porque compara enteros en vez de flotantes.
        - Subir ``flush_interval_sec`` de 5 a 60 divide por doce los volcados
          del WAL al disco. Con ~77 vectores nuevos al día no hay nada que
          ganar volcando cada cinco segundos, y la tarjeta SD lo agradece.

        Devuelve qué se aplicó, para poder registrarlo.
        """
        info = self.client.get_collection(self.collection)
        aplicado = {}

        if getattr(info.config, 'quantization_config', None) is None:
            self.client.update_collection(
                self.collection,
                quantization_config=qm.ScalarQuantization(
                    scalar=qm.ScalarQuantizationConfig(
                        type=qm.ScalarType.INT8, always_ram=True
                    )
                ),
            )
            aplicado['quantization'] = 'int8'

        actual = getattr(info.config.optimizer_config, 'flush_interval_sec', None)
        if actual != flush_interval_sec:
            self.client.update_collection(
                self.collection,
                optimizers_config=qm.OptimizersConfigDiff(
                    flush_interval_sec=flush_interval_sec
                ),
            )
            aplicado['flush_interval_sec'] = flush_interval_sec

        return aplicado

    def delete_older_than(self, min_published_ts: int) -> None:
        """Borra de una vez los puntos anteriores a una fecha.

        Reemplaza a enumerar guids y mandarlos en una lista: el criterio es una
        fecha, así que se lo damos a Qdrant como filtro y resuelve él. Una
        petición en lugar de una lista que crece con la ventana.
        """
        self.client.delete(
            self.collection,
            points_selector=qm.FilterSelector(
                filter=qm.Filter(
                    must=[
                        qm.FieldCondition(
                            key="published_ts",
                            range=qm.Range(lt=int(min_published_ts)),
                        )
                    ]
                )
            ),
        )

    def known_guids(self, guids: List[str], batch_size: int = 256) -> set:
        """De los guids dados, cuáles están ya indexados.

        Antes esto se averiguaba recorriendo la colección entera y quedándose
        con los news_id: 161 ms con 1.151 puntos, pero ~3,9 s con los 28.000 de
        una ventana anual, y corriendo 29 veces al día. Preguntar por los guids
        concretos no depende del tamaño de la colección, solo de cuántos se
        preguntan, que son unas pocas decenas.
        """
        pendientes = [g for g in guids if g]
        if not pendientes:
            return set()

        por_id = {
            str(uuid.uuid5(uuid.NAMESPACE_URL, guid)): guid for guid in pendientes
        }
        encontrados = set()
        ids = list(por_id)
        for inicio in range(0, len(ids), batch_size):
            lote = ids[inicio:inicio + batch_size]
            puntos = self.client.retrieve(
                self.collection,
                ids=lote,
                with_payload=False,
                with_vectors=False,
            )
            for punto in puntos:
                guid = por_id.get(str(punto.id))
                if guid:
                    encontrados.add(guid)
        return encontrados

    @staticmethod
    def _first_vector(raw):
        """Qdrant devuelve un dict si la colección usa vectores con nombre."""
        if isinstance(raw, dict):
            return next(iter(raw.values()), None)
        return raw

    def scroll_points(self, limit: int = 256, with_vectors: bool = False):
        offset = None
        while True:
            points, next_offset = self.client.scroll(
                collection_name=self.collection,
                limit=limit,
                offset=offset,
                with_payload=True,
                with_vectors=with_vectors,
            )
            for point in points:
                yield point
            if next_offset is None:
                break
            offset = next_offset

    def delete_point_ids(self, point_ids: List[str]) -> int:
        cleaned_ids = [point_id for point_id in point_ids if point_id is not None]
        if not cleaned_ids:
            return 0
        self.client.delete(
            self.collection,
            points_selector=qm.PointIdsList(points=cleaned_ids),
        )
        return len(cleaned_ids)

    def search(
        self,
        vector: List[float],
        top_k: int,
        min_published_ts: Optional[int] = None,
        exclude_guid: Optional[str] = None,
        extra_must: Optional[list] = None,
    ):
        must = [
            qm.FieldCondition(key="is_filtered", match=qm.MatchValue(value=False)),
            qm.FieldCondition(key="is_redundant", match=qm.MatchValue(value=False)),
        ]
        if min_published_ts is not None:
            must.append(
                qm.FieldCondition(
                    key="published_ts", range=qm.Range(gte=int(min_published_ts))
                )
            )
        if extra_must:
            must.extend(extra_must)

        must_not = []
        if exclude_guid:
            must_not.append(
                qm.FieldCondition(
                    key="guid_hash", match=qm.MatchValue(value=self.guid_hash(exclude_guid))
                )
            )
        qfilter = qm.Filter(must=must, must_not=must_not)

        # ``search`` está deprecado en qdrant-client desde la 1.10 a favor de
        # ``query_points``. Se devuelve ``.points`` para que los llamadores
        # sigan recibiendo una lista de aciertos con ``score`` y ``payload``.
        return self.client.query_points(
            collection_name=self.collection,
            query=vector,
            query_filter=qfilter,
            limit=top_k,
        ).points

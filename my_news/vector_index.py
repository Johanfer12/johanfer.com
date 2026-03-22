import hashlib
import uuid
from typing import List, Optional

try:
    from qdrant_client import QdrantClient
    from qdrant_client import models as qm
except Exception:  # pragma: no cover
    QdrantClient = None  # type: ignore
    qm = None  # type: ignore


class VectorIndexUnavailable(Exception):
    pass


class VectorIndexService:
    """Wrapper mínimo para operar Qdrant sin silencios."""

    def __init__(self, url: str, collection: str, api_key: Optional[str] = None):
        if QdrantClient is None:
            raise VectorIndexUnavailable(
                "qdrant-client no está instalado. Instálalo con 'pip install qdrant-client'."
            )
        self.client = QdrantClient(url=url, api_key=api_key)
        self.collection = collection

    def ensure_collection(self, dim: int) -> None:
        """Crea la colección si no existe (lanza excepción en error)."""
        cols = self.client.get_collections().collections
        if any(c.name == self.collection for c in cols):
            return
        self.client.create_collection(
            collection_name=self.collection,
            vectors_config=qm.VectorParams(size=dim, distance=qm.Distance.COSINE),
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

    def scroll_points(self, limit: int = 256):
        offset = None
        while True:
            points, next_offset = self.client.scroll(
                collection_name=self.collection,
                limit=limit,
                offset=offset,
                with_payload=True,
                with_vectors=False,
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

        return self.client.search(
            collection_name=self.collection,
            query_vector=vector,
            query_filter=qfilter,
            limit=top_k,
        )

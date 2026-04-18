"""Chroma collection 封装。独立于 app.services.chroma_store，共享 persist_dir 但使用不同 collection。"""

from __future__ import annotations

import logging
from typing import Any, cast

import chromadb
from chromadb.api.models.Collection import Collection

from app.services.memory.config import Agent4Settings
from app.services.memory.embedder import Embedder
from app.services.memory.schemas import MemoryDoc, RawHit

logger = logging.getLogger(__name__)

EMBEDDING_MODEL_META_KEY = "agent4_embedding_model"
EMBEDDING_DIM_META_KEY = "agent4_embedding_dim"


class MemoryStore:
    """Agent 4 的 Chroma 持久层。"""

    def __init__(self, settings: Agent4Settings, embedder: Embedder) -> None:
        self.settings = settings
        self.embedder = embedder
        self.client = chromadb.PersistentClient(path=str(settings.persist_dir))

    def _get_collection(self, name: str) -> Collection:
        return self.client.get_or_create_collection(
            name=name,
            metadata={
                EMBEDDING_MODEL_META_KEY: self.embedder.model_name,
            },
        )

    def ensure_collections(self) -> None:
        """幂等创建 Agent 4 需要的 collection。"""
        for name in (
            self.settings.collection_ad_examples,
            self.settings.collection_product_knowledge,
        ):
            self._get_collection(name)

    def recreate(self, name: str) -> None:
        """删除并重建单个 collection（用于 --force 灌库）。"""
        try:
            self.client.delete_collection(name=name)
        except Exception:
            pass
        self._get_collection(name)

    def count(self, name: str) -> int:
        return self._get_collection(name).count()

    def upsert_docs(self, name: str, docs: list[MemoryDoc]) -> int:
        """把文档 embed 后写入 collection。返回写入条数。"""
        if not docs:
            return 0
        collection = self._get_collection(name)
        texts = [doc.content for doc in docs]
        vectors = self.embedder.embed(texts)
        ids = [doc.id for doc in docs]
        metadatas: list[dict[str, Any]] = [
            self._sanitize_metadata(doc.metadata) for doc in docs
        ]
        collection.upsert(
            ids=ids,
            documents=texts,
            embeddings=cast(Any, vectors),
            metadatas=cast(Any, metadatas),
        )
        logger.info(
            "memory_store.upsert collection=%s count=%s model=%s",
            name,
            len(docs),
            self.embedder.model_name,
        )
        return len(docs)

    def query(
        self,
        name: str,
        query_vector: list[float],
        top_k: int,
        where: dict[str, Any] | None = None,
    ) -> list[RawHit]:
        """向量检索。返回 RawHit 列表，按距离从小到大排序。"""
        collection = self._get_collection(name)
        # Chroma 空库时 query 也可以调用，返回空即可；
        # where 为 {} 时 Chroma 会报错，需要置为 None。
        cleaned_where = where if where else None
        try:
            result = collection.query(
                query_embeddings=cast(Any, [query_vector]),
                n_results=top_k,
                where=cast(Any, cleaned_where),
            )
        except Exception as exc:
            logger.warning(
                "memory_store.query 失败 collection=%s err=%s", name, exc
            )
            return []
        ids_list = result.get("ids") or [[]]
        docs_list = result.get("documents") or [[]]
        metas_list = result.get("metadatas") or [[]]
        dists_list = result.get("distances") or [[]]
        ids = ids_list[0] if ids_list else []
        docs = docs_list[0] if docs_list else []
        metas = metas_list[0] if metas_list else []
        dists = dists_list[0] if dists_list else []
        hits: list[RawHit] = []
        for idx, raw_id in enumerate(ids):
            hits.append(
                RawHit(
                    id=str(raw_id),
                    text=str(docs[idx]) if idx < len(docs) else "",
                    metadata=dict(metas[idx]) if idx < len(metas) and metas[idx] else {},
                    distance=float(dists[idx]) if idx < len(dists) else 0.0,
                )
            )
        return hits

    @staticmethod
    def _sanitize_metadata(meta: dict[str, Any]) -> dict[str, Any]:
        """Chroma metadata 只接受 str/int/float/bool。list 拼成 | 分隔字符串。"""
        cleaned: dict[str, Any] = {}
        for key, value in meta.items():
            if isinstance(value, (str, int, float, bool)) or value is None:
                if value is None:
                    continue
                cleaned[key] = value
            elif isinstance(value, list):
                cleaned[key] = "|".join(str(item) for item in value)
            else:
                cleaned[key] = str(value)
        return cleaned

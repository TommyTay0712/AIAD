from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, cast

import chromadb
from chromadb.api.models.Collection import Collection

logger = logging.getLogger(__name__)


class ChromaStore:
    """ChromaDB 持久化封装。"""

    def __init__(self, persist_dir: Path) -> None:
        self.client = chromadb.PersistentClient(path=str(persist_dir))

    def _upsert_rows(self, collection: Collection, rows: list[dict[str, Any]], prefix: str) -> int:
        if not rows:
            return 0
        ids = [f"{prefix}:{idx}" for idx in range(len(rows))]
        documents = [json.dumps(row, ensure_ascii=False) for row in rows]
        metadatas = [
            {
                "platform": str(row.get("platform", "")),
                "note_id": str(row.get("note_id", "")),
            }
            for row in rows
        ]
        collection.upsert(ids=ids, documents=documents, metadatas=cast(Any, metadatas))
        return len(rows)

    def write_task_payload(self, task_id: str, payload: dict[str, Any]) -> dict[str, int]:
        """写入 summary/content/comment/feature 四类数据。"""
        content_collection = self.client.get_or_create_collection(name="content_table")
        comment_collection = self.client.get_or_create_collection(name="comment_table")
        feature_collection = self.client.get_or_create_collection(name="feature_table")
        summary_collection = self.client.get_or_create_collection(name="summary_table")

        summary_row = payload.get("summary", {})
        summary_count = self._upsert_rows(summary_collection, [summary_row], f"{task_id}:summary")
        content_count = self._upsert_rows(
            content_collection,
            payload.get("content_table", []),
            f"{task_id}:content",
        )
        comment_count = self._upsert_rows(
            comment_collection,
            payload.get("comment_table", []),
            f"{task_id}:comment",
        )
        feature_count = self._upsert_rows(
            feature_collection,
            payload.get("feature_table", []),
            f"{task_id}:feature",
        )
        logger.info(
            "ChromaDB写入完成 task_id=%s summary=%s content=%s comment=%s feature=%s",
            task_id,
            summary_count,
            content_count,
            comment_count,
            feature_count,
        )
        return {
            "summary_count": summary_count,
            "content_count": content_count,
            "comment_count": comment_count,
            "feature_count": feature_count,
        }

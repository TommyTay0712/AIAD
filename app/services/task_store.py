from __future__ import annotations

import json
import threading
from datetime import datetime
from pathlib import Path
from typing import Any

from app.models.schemas import TaskRecord


class TaskStore:
    """基于JSON文件的任务追踪存储。"""

    # 类级别锁：所有实例共享，保护同一 JSON 文件的并发读写
    _lock: threading.Lock = threading.Lock()

    def __init__(self, store_file: Path) -> None:
        self.store_file = store_file

    def _read_all(self) -> dict[str, dict]:
        content = self.store_file.read_text(encoding="utf-8").strip()
        if not content:
            return {}
        return json.loads(content)

    def _write_all(self, payload: dict[str, dict]) -> None:
        self.store_file.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def upsert(self, record: TaskRecord) -> TaskRecord:
        with self._lock:
            payload = self._read_all()
            now = datetime.now().isoformat()
            data = record.model_dump(mode="json")
            data["updated_at"] = now
            if record.task_id not in payload:
                data["created_at"] = now
            else:
                data["created_at"] = payload[record.task_id]["created_at"]
            payload[record.task_id] = data
            self._write_all(payload)
            return TaskRecord.model_validate(payload[record.task_id])

    def get(self, task_id: str) -> TaskRecord | None:
        payload = self._read_all()
        raw = payload.get(task_id)
        if not raw:
            return None
        return TaskRecord.model_validate(raw)

    def patch_result(self, task_id: str, updates: dict[str, Any]) -> None:
        """原子性地合并更新单条任务的 result 字段（部分更新，不覆盖其他字段）。"""
        with self._lock:
            payload = self._read_all()
            if task_id not in payload:
                return
            existing_result: dict[str, Any] = payload[task_id].get("result") or {}
            existing_result.update(updates)
            payload[task_id]["result"] = existing_result
            payload[task_id]["updated_at"] = datetime.now().isoformat()
            self._write_all(payload)

    def list_recent(self, limit: int = 10) -> list[TaskRecord]:
        payload = self._read_all()
        records = [TaskRecord.model_validate(item) for item in payload.values()]
        records.sort(key=lambda record: record.updated_at, reverse=True)
        return records[: max(1, limit)]

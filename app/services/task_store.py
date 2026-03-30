from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from app.models.schemas import TaskRecord


class TaskStore:
    """基于JSON文件的任务追踪存储。"""

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

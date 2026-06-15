from __future__ import annotations

import json
import logging
import sqlite3
from collections.abc import Generator
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any

from app.models.schemas import ErrorCode, TaskRecord, TaskStatus

logger = logging.getLogger(__name__)

_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS tasks (
    task_id       TEXT PRIMARY KEY,
    status        TEXT NOT NULL,
    params        TEXT NOT NULL DEFAULT '{}',
    result        TEXT NOT NULL DEFAULT '{}',
    output_files  TEXT NOT NULL DEFAULT '{}',
    error_code    TEXT,
    error_message TEXT NOT NULL DEFAULT '',
    created_at    TEXT NOT NULL,
    updated_at    TEXT NOT NULL
)
"""

# ON CONFLICT: 保留 created_at（不在 DO UPDATE SET 中），只更新其余字段
_UPSERT = """
INSERT INTO tasks
    (task_id, status, params, result, output_files,
     error_code, error_message, created_at, updated_at)
VALUES
    (:task_id, :status, :params, :result, :output_files,
     :error_code, :error_message, :created_at, :updated_at)
ON CONFLICT(task_id) DO UPDATE SET
    status        = excluded.status,
    params        = excluded.params,
    result        = excluded.result,
    output_files  = excluded.output_files,
    error_code    = excluded.error_code,
    error_message = excluded.error_message,
    updated_at    = excluded.updated_at
"""


class TaskStore:
    """基于 SQLite WAL 的任务追踪存储，跨进程安全（支持 --workers N）。"""

    def __init__(self, store_file: Path) -> None:
        # 兼容旧 .json 路径：统一转为 .db 扩展名
        self.db_path = store_file.with_suffix(".db")
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    @contextmanager
    def _conn(self) -> Generator[sqlite3.Connection, None, None]:
        conn = sqlite3.connect(str(self.db_path), check_same_thread=False, timeout=10)
        conn.row_factory = sqlite3.Row
        # WAL 模式：多进程并发读写安全；busy_timeout 避免 SQLITE_BUSY 立即报错
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=5000")
        conn.execute("PRAGMA synchronous=NORMAL")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _init_db(self) -> None:
        with self._conn() as conn:
            conn.execute(_CREATE_TABLE)

    @staticmethod
    def _to_row(record: TaskRecord) -> dict[str, Any]:
        now = datetime.now().isoformat()
        return {
            "task_id": record.task_id,
            "status": record.status.value,
            "params": json.dumps(record.params, ensure_ascii=False),
            "result": json.dumps(record.result, ensure_ascii=False),
            "output_files": json.dumps(record.output_files, ensure_ascii=False),
            "error_code": record.error_code.value if record.error_code else None,
            "error_message": record.error_message,
            "created_at": now,   # 仅在 INSERT 时写入；UPSERT 不更新此字段
            "updated_at": now,
        }

    @staticmethod
    def _from_row(row: sqlite3.Row) -> TaskRecord:
        d = dict(row)
        d["params"] = json.loads(d["params"])
        d["result"] = json.loads(d["result"])
        d["output_files"] = json.loads(d["output_files"])
        return TaskRecord.model_validate(d)

    def upsert(self, record: TaskRecord) -> TaskRecord:
        with self._conn() as conn:
            conn.execute(_UPSERT, self._to_row(record))
            row = conn.execute(
                "SELECT * FROM tasks WHERE task_id=?", (record.task_id,)
            ).fetchone()
        return self._from_row(row)

    def get(self, task_id: str) -> TaskRecord | None:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM tasks WHERE task_id=?", (task_id,)
            ).fetchone()
        return self._from_row(row) if row else None

    def patch_result(self, task_id: str, updates: dict[str, Any]) -> None:
        """在单个 SQLite 事务内原子合并 result 字段，无跨进程读-改-写竞态。"""
        with self._conn() as conn:
            row = conn.execute(
                "SELECT result FROM tasks WHERE task_id=?", (task_id,)
            ).fetchone()
            if not row:
                return
            existing: dict[str, Any] = json.loads(row["result"])
            existing.update(updates)
            conn.execute(
                "UPDATE tasks SET result=?, updated_at=? WHERE task_id=?",
                (json.dumps(existing, ensure_ascii=False), datetime.now().isoformat(), task_id),
            )

    def list_recent(self, limit: int = 10) -> list[TaskRecord]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM tasks ORDER BY updated_at DESC LIMIT ?",
                (max(1, limit),),
            ).fetchall()
        return [self._from_row(r) for r in rows]

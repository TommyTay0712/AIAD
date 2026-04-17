from datetime import datetime
from pathlib import Path

import app.services.task_store as task_store_module
from app.models.schemas import TaskRecord, TaskStatus
from app.services.task_store import TaskStore


class _Clock:
    current = datetime(2026, 4, 16, 10, 0, 0)

    @classmethod
    def now(cls) -> datetime:
        return cls.current


def _make_record(task_id: str, status: TaskStatus) -> TaskRecord:
    return TaskRecord(
        task_id=task_id,
        created_at=datetime(2024, 1, 1, 0, 0, 0),
        updated_at=datetime(2024, 1, 1, 0, 0, 0),
        status=status,
        params={"platform": "xhs"},
    )


def test_task_store_upsert_preserves_created_at(tmp_path: Path, monkeypatch) -> None:
    store_file = tmp_path / "tasks.json"
    store_file.write_text("{}", encoding="utf-8")
    store = TaskStore(store_file)
    monkeypatch.setattr(task_store_module, "datetime", _Clock)

    _Clock.current = datetime(2026, 4, 16, 10, 0, 0)
    created = store.upsert(_make_record("task-1", TaskStatus.RUNNING))

    _Clock.current = datetime(2026, 4, 16, 10, 5, 0)
    updated = store.upsert(_make_record("task-1", TaskStatus.SUCCESS))

    assert created.created_at == datetime(2026, 4, 16, 10, 0, 0)
    assert updated.created_at == created.created_at
    assert updated.updated_at == datetime(2026, 4, 16, 10, 5, 0)
    assert updated.status == TaskStatus.SUCCESS


def test_task_store_get_returns_none_for_missing_task(tmp_path: Path) -> None:
    store_file = tmp_path / "tasks.json"
    store_file.write_text("{}", encoding="utf-8")
    store = TaskStore(store_file)

    assert store.get("missing-task") is None


def test_task_store_list_recent_returns_latest_first(tmp_path: Path, monkeypatch) -> None:
    store_file = tmp_path / "tasks.json"
    store_file.write_text("{}", encoding="utf-8")
    store = TaskStore(store_file)
    monkeypatch.setattr(task_store_module, "datetime", _Clock)

    _Clock.current = datetime(2026, 4, 16, 10, 0, 0)
    store.upsert(_make_record("task-1", TaskStatus.RUNNING))

    _Clock.current = datetime(2026, 4, 16, 10, 1, 0)
    store.upsert(_make_record("task-2", TaskStatus.RUNNING))

    _Clock.current = datetime(2026, 4, 16, 10, 2, 0)
    store.upsert(_make_record("task-1", TaskStatus.SUCCESS))

    recent = store.list_recent(limit=2)

    assert [record.task_id for record in recent] == ["task-1", "task-2"]
    assert recent[0].status == TaskStatus.SUCCESS

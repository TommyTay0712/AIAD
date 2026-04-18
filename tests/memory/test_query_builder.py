from __future__ import annotations

import json
from pathlib import Path

from app.services.memory.config import Agent4Settings
from app.services.memory.query_builder import build_query

FIXTURE_DIR = Path(__file__).parent / "fixtures"


def _make_settings(tmp_path: Path) -> Agent4Settings:
    return Agent4Settings(
        project_root=tmp_path,
        persist_dir=tmp_path / "chroma",
        seed_dir=tmp_path / "seeds",
    )


def test_build_query_beach_contains_signals(tmp_path: Path) -> None:
    state = json.loads(
        (FIXTURE_DIR / "mock_global_state_beach.json").read_text(encoding="utf-8")
    )
    settings = _make_settings(tmp_path)
    spec = build_query(state, settings)
    assert "海边/沙滩" in spec.semantic_text
    assert "低敏诉求" in spec.semantic_text
    assert "测评风" in spec.semantic_text
    assert spec.signals["scene"] == "海边/沙滩"
    assert spec.signals["target_style"] == "测评风"
    assert spec.signals["pain_points"] == ["低敏诉求", "补涂便利"]
    assert spec.signals["cold_start"] is False


def test_build_query_cold_start_flag(tmp_path: Path) -> None:
    state = json.loads(
        (FIXTURE_DIR / "mock_global_state_empty.json").read_text(encoding="utf-8")
    )
    settings = _make_settings(tmp_path)
    spec = build_query(state, settings)
    assert spec.signals["cold_start"] is True
    assert spec.signals["target_style"] == "测评风"


def test_build_query_has_query_prefix(tmp_path: Path) -> None:
    state = json.loads(
        (FIXTURE_DIR / "mock_global_state_beach.json").read_text(encoding="utf-8")
    )
    settings = _make_settings(tmp_path)
    spec = build_query(state, settings)
    assert spec.semantic_text.startswith(settings.embedding_query_prefix)


def test_build_query_defaults_platform_filter(tmp_path: Path) -> None:
    settings = _make_settings(tmp_path)
    spec = build_query({"vision_analysis": {"scene": "海边/沙滩"}}, settings)
    meta_filter = spec.metadata_filter
    assert "platform" in json.dumps(meta_filter, ensure_ascii=False)

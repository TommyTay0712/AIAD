from __future__ import annotations

import json
from pathlib import Path

from app.services.memory.config import Agent4Settings
from app.services.memory.memory_store import MemoryStore
from app.services.memory.seed_loader import (
    load_forbidden_phrases,
    load_seeds_into_memory,
)
from tests.memory.fixtures.fake_embedder import FakeEmbedder


def _prepare_settings(tmp_path: Path) -> Agent4Settings:
    seed_dir = tmp_path / "seeds"
    seed_dir.mkdir()
    return Agent4Settings(
        project_root=tmp_path,
        persist_dir=tmp_path / "chroma",
        seed_dir=seed_dir,
    )


def test_load_forbidden_phrases_skips_blanks_and_comments(tmp_path: Path) -> None:
    settings = _prepare_settings(tmp_path)
    (settings.seed_dir / "forbidden_phrases.txt").write_text(
        "# 注释\n根治\n\n包治\n根治\n",
        encoding="utf-8",
    )
    assert load_forbidden_phrases(settings) == ["根治", "包治"]


def test_load_forbidden_phrases_missing_file_returns_empty(tmp_path: Path) -> None:
    settings = _prepare_settings(tmp_path)
    assert load_forbidden_phrases(settings) == []


def test_load_seeds_into_memory_upserts_and_queries(
    tmp_path: Path, monkeypatch
) -> None:
    settings = _prepare_settings(tmp_path)
    ad = {
        "id": "ad-1",
        "content": "海边防晒补涂喷雾最方便",
        "style": "测评风",
        "scene": "海边/沙滩",
        "pain_point_tags": ["低敏诉求", "补涂便利"],
        "quality_score": 0.85,
        "platform": "小红书",
    }
    pk = {
        "id": "pk-1",
        "brand": "示例",
        "product": "防晒",
        "point": "水润不假白",
        "allowed_claim": True,
        "scene_fit": ["海边"],
    }
    (settings.seed_dir / "ad_examples.jsonl").write_text(
        json.dumps(ad, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    (settings.seed_dir / "product_knowledge.jsonl").write_text(
        json.dumps(pk, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    # 把 build_embedder 替换成 FakeEmbedder，避免测试里加载真模型
    # load_seeds_into_memory 内部延迟 import，所以要在 embedder 源模块 patch
    import app.services.memory.embedder as embedder_mod

    monkeypatch.setattr(embedder_mod, "build_embedder", lambda s: FakeEmbedder())

    counts = load_seeds_into_memory(settings, force=True)
    assert counts[settings.collection_ad_examples] == 1
    assert counts[settings.collection_product_knowledge] == 1

    store = MemoryStore(settings, FakeEmbedder())
    assert store.count(settings.collection_ad_examples) == 1
    assert store.count(settings.collection_product_knowledge) == 1

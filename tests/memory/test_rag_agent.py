"""rag_agent 端到端冒烟测试。使用 FakeEmbedder 避免加载真模型。"""

from __future__ import annotations

import json
from pathlib import Path

from app.services.memory.config import Agent4Settings
from app.services.memory.memory_store import MemoryStore
from app.services.memory.schemas import MemoryDoc
from tests.memory.fixtures.fake_embedder import FakeEmbedder

FIXTURE_DIR = Path(__file__).parent / "fixtures"


def _prepare_settings(tmp_path: Path) -> Agent4Settings:
    seed_dir = tmp_path / "seeds"
    seed_dir.mkdir()
    return Agent4Settings(
        project_root=tmp_path,
        persist_dir=tmp_path / "chroma",
        seed_dir=seed_dir,
    )


def _seed_store(settings: Agent4Settings) -> None:
    embedder = FakeEmbedder()
    store = MemoryStore(settings, embedder)
    store.ensure_collections()
    store.upsert_docs(
        settings.collection_ad_examples,
        [
            MemoryDoc(
                id="ad-beach-001",
                content="海边补防晒喷雾最方便，不搓泥也不假白",
                metadata={
                    "style": "测评风",
                    "scene": "海边/沙滩",
                    "pain_point_tags": "低敏诉求|补涂便利",
                    "quality_score": 0.9,
                    "platform": "小红书",
                },
            ),
            MemoryDoc(
                id="ad-commute-001",
                content="通勤防晒要选水润型，底妆更服帖",
                metadata={
                    "style": "科普风",
                    "scene": "通勤/日常",
                    "pain_point_tags": "假白|油腻",
                    "quality_score": 0.8,
                    "platform": "小红书",
                },
            ),
        ],
    )
    store.upsert_docs(
        settings.collection_product_knowledge,
        [
            MemoryDoc(
                id="pk-1",
                content="水润不假白",
                metadata={"brand": "示例", "allowed_claim": True},
            ),
        ],
    )


def _patch_settings_and_embedder(monkeypatch, settings: Agent4Settings) -> None:
    import app.services.memory.rag_agent as rag_agent

    monkeypatch.setattr(rag_agent, "get_agent4_settings", lambda: settings)
    monkeypatch.setattr(
        rag_agent, "_get_embedder", lambda _s: FakeEmbedder()
    )
    rag_agent._cached_embedder.cache_clear()


def test_run_rag_agent_end_to_end_returns_hits(tmp_path: Path, monkeypatch) -> None:
    settings = _prepare_settings(tmp_path)
    _seed_store(settings)
    _patch_settings_and_embedder(monkeypatch, settings)

    from app.services.memory.rag_agent import run_rag_agent

    state_json = json.loads(
        (FIXTURE_DIR / "mock_global_state_beach.json").read_text(encoding="utf-8")
    )
    state = {"global_state": state_json}
    result = run_rag_agent(state)
    gs = result["global_state"]

    assert "rag_references" in gs
    assert "rag_references_full" in gs
    assert "retrieval_summary" in gs
    summary = gs["retrieval_summary"]
    assert summary["hit_count"] >= 1
    assert summary["embedding_model"] == "fake-hash-32"


def test_run_rag_agent_cold_start_returns_empty_but_valid(
    tmp_path: Path, monkeypatch
) -> None:
    settings = _prepare_settings(tmp_path)
    _patch_settings_and_embedder(monkeypatch, settings)

    from app.services.memory.rag_agent import run_rag_agent

    state_json = json.loads(
        (FIXTURE_DIR / "mock_global_state_empty.json").read_text(encoding="utf-8")
    )
    state = {"global_state": state_json}
    result = run_rag_agent(state)
    gs = result["global_state"]

    assert gs["retrieval_summary"]["confidence"] == "low_confidence"
    assert gs["rag_references"] == []
    assert gs["rag_references_full"] == []
    assert isinstance(gs["rag_forbidden_phrases"], list)


def test_run_rag_agent_never_raises_on_error(tmp_path: Path, monkeypatch) -> None:
    """即使 embedder 抛异常，也要走 empty_output 兜底。"""
    settings = _prepare_settings(tmp_path)

    class BrokenEmbedder:
        model_name = "broken"

        def embed(self, texts):
            raise RuntimeError("boom")

        def get_dimension(self):
            return 32

    import app.services.memory.rag_agent as rag_agent

    monkeypatch.setattr(rag_agent, "get_agent4_settings", lambda: settings)
    monkeypatch.setattr(rag_agent, "_get_embedder", lambda _s: BrokenEmbedder())
    rag_agent._cached_embedder.cache_clear()

    from app.services.memory.rag_agent import run_rag_agent

    result = run_rag_agent({"global_state": {}})
    gs = result["global_state"]
    assert gs["retrieval_summary"]["confidence"] == "low_confidence"
    assert "agent4_error" in gs["retrieval_summary"]["reason"]

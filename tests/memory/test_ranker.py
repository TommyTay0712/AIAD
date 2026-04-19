from __future__ import annotations

from app.services.memory.ranker import mmr_deduplicate, rerank
from app.services.memory.schemas import RawHit


def _hit(
    hit_id: str,
    text: str,
    *,
    style: str = "",
    scene: str = "",
    pains: list[str] | None = None,
    quality: float = 0.5,
    distance: float = 0.3,
) -> RawHit:
    meta: dict = {"style": style, "scene": scene, "quality_score": quality}
    if pains is not None:
        meta["pain_point_tags"] = "|".join(pains)
    return RawHit(id=hit_id, text=text, metadata=meta, distance=distance)


def test_rerank_style_match_ranks_first() -> None:
    hits = [
        _hit("a", "文案A", style="科普风", distance=0.2),
        _hit("b", "文案B", style="测评风", distance=0.4),
    ]
    signals = {"target_style": "测评风", "scene": "", "pain_points": []}
    out = rerank(hits, signals, forbidden=[])
    assert out[0].id == "b"
    assert "style" in out[0].matched_signals


def test_rerank_scene_and_painpoint_stack() -> None:
    hits = [
        _hit(
            "beach",
            "海边文案",
            style="测评风",
            scene="海边/沙滩",
            pains=["低敏诉求", "补涂便利"],
            distance=0.3,
        ),
        _hit("other", "其他文案", style="测评风", scene="", pains=[], distance=0.3),
    ]
    signals = {
        "target_style": "测评风",
        "scene": "海边/沙滩",
        "pain_points": ["低敏诉求"],
    }
    out = rerank(hits, signals, forbidden=[])
    assert out[0].id == "beach"
    assert "scene" in out[0].matched_signals
    assert any(tag.startswith("pain_point:") for tag in out[0].matched_signals)


def test_rerank_forbidden_phrase_drops_hit() -> None:
    hits = [
        _hit("ok", "正常文案", distance=0.1),
        _hit("bad", "这款产品根治所有问题", distance=0.05),
    ]
    out = rerank(hits, signals={"target_style": ""}, forbidden=["根治"])
    assert [h.id for h in out] == ["ok"]


def test_mmr_respects_max_per_style() -> None:
    from app.services.memory.schemas import RetrievalHit

    hits = [
        RetrievalHit(id="a", text="A 文案", style="测评风", score=1.0),
        RetrievalHit(id="b", text="B 文案", style="测评风", score=0.9),
        RetrievalHit(id="c", text="C 文案", style="测评风", score=0.8),
        RetrievalHit(id="d", text="D 文案", style="科普风", score=0.7),
    ]
    picked = mmr_deduplicate(hits, lambda_=0.8, max_k=3, max_per_style=2)
    styles = [h.style for h in picked]
    assert styles.count("测评风") <= 2
    assert "科普风" in styles


def test_mmr_empty_input_returns_empty() -> None:
    assert mmr_deduplicate([], lambda_=0.7, max_k=5, max_per_style=2) == []

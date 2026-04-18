from __future__ import annotations

from app.services.memory.formatter import empty_output, format_retrieval_context
from app.services.memory.schemas import (
    ProductKnowledge,
    QuerySpec,
    RetrievalHit,
)


def _query_spec(cold: bool = False) -> QuerySpec:
    return QuerySpec(
        semantic_text="海边/沙滩 低敏诉求",
        metadata_filter={},
        signals={"scene": "海边/沙滩", "cold_start": cold},
    )


def test_format_high_confidence() -> None:
    hits = [
        RetrievalHit(
            id=str(i),
            text=f"hit {i}",
            style="测评风",
            scene="海边/沙滩",
            score=0.9 - i * 0.05,
            matched_signals=["style", "scene"],
        )
        for i in range(3)
    ]
    out = format_retrieval_context(
        final_hits=hits,
        product_knowledge=[
            ProductKnowledge(point="水润不假白", allowed_claim=True)
        ],
        forbidden=["根治"],
        query_spec=_query_spec(),
        embedder_name="fake-hash-32",
    )
    assert out.retrieval_summary.confidence == "high"
    assert out.retrieval_summary.hit_count == 3
    assert out.retrieval_summary.embedding_model == "fake-hash-32"
    assert len(out.rag_references) == 3
    assert out.rag_references[0].startswith("【测评风】")
    assert out.rag_product_knowledge[0].point == "水润不假白"
    assert out.rag_forbidden_phrases == ["根治"]


def test_format_low_confidence_when_no_hits() -> None:
    out = format_retrieval_context(
        final_hits=[],
        product_knowledge=[],
        forbidden=[],
        query_spec=_query_spec(cold=True),
        embedder_name="fake",
    )
    assert out.retrieval_summary.confidence == "low_confidence"
    assert "cold_start" in out.retrieval_summary.reason
    assert out.rag_references == []


def test_empty_output_always_valid() -> None:
    out = empty_output(reason="test", embedder_name="none", forbidden=["根治"])
    assert out.retrieval_summary.confidence == "low_confidence"
    assert out.retrieval_summary.reason == "test"
    assert out.rag_forbidden_phrases == ["根治"]
    assert out.rag_references == []
    assert out.rag_references_full == []

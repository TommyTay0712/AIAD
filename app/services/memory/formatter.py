"""把检索结果打包成 RagOutput，并计算置信度。"""

from __future__ import annotations

from app.services.memory.schemas import (
    ProductKnowledge,
    QuerySpec,
    RagOutput,
    RetrievalHit,
    RetrievalSummary,
)

HIGH_CONFIDENCE_MIN_HITS = 3
HIGH_CONFIDENCE_MIN_TOP_SCORE = 0.75
MEDIUM_CONFIDENCE_MIN_HITS = 2
MEDIUM_CONFIDENCE_MIN_TOP_SCORE = 0.55


def _compute_confidence(
    final_hits: list[RetrievalHit], signals: dict
) -> tuple[str, str]:
    if not final_hits:
        if signals.get("cold_start"):
            return "low_confidence", "cold_start_upstream_signals_empty"
        return "low_confidence", "no_hits"
    top_score = final_hits[0].score
    scene_hit = any("scene" in h.matched_signals for h in final_hits)
    if (
        len(final_hits) >= HIGH_CONFIDENCE_MIN_HITS
        and top_score >= HIGH_CONFIDENCE_MIN_TOP_SCORE
        and scene_hit
    ):
        return "high", f"top_score={top_score:.2f} scene_matched"
    if (
        len(final_hits) >= MEDIUM_CONFIDENCE_MIN_HITS
        and top_score >= MEDIUM_CONFIDENCE_MIN_TOP_SCORE
    ):
        return "medium", f"top_score={top_score:.2f}"
    if signals.get("cold_start"):
        return "low_confidence", "cold_start_upstream_signals_empty"
    return "low_confidence", f"top_score={top_score:.2f} below_threshold"


def _as_back_compat_references(hits: list[RetrievalHit]) -> list[str]:
    """为兼容 Agent 5 现有 rag_references: list[str] 字段，生成字符串版本。"""
    out: list[str] = []
    for h in hits:
        text = h.text.strip()
        if not text:
            continue
        snippet = text[:80]
        prefix = f"【{h.style}】" if h.style else ""
        out.append(f"{prefix}{snippet}")
    return out


def format_retrieval_context(
    *,
    final_hits: list[RetrievalHit],
    product_knowledge: list[ProductKnowledge],
    forbidden: list[str],
    query_spec: QuerySpec,
    embedder_name: str,
) -> RagOutput:
    """打包为 RagOutput。"""
    confidence, reason = _compute_confidence(final_hits, query_spec.signals)
    summary = RetrievalSummary(
        query_used=query_spec.semantic_text,
        hit_count=len(final_hits),
        confidence=confidence,
        reason=reason,
        embedding_model=embedder_name,
    )
    return RagOutput(
        rag_references=_as_back_compat_references(final_hits),
        rag_references_full=final_hits,
        rag_product_knowledge=product_knowledge,
        rag_forbidden_phrases=list(forbidden),
        retrieval_summary=summary,
    )


def empty_output(
    *,
    reason: str,
    embedder_name: str,
    query_used: str = "",
    forbidden: list[str] | None = None,
) -> RagOutput:
    """任何异常或冷启动走的合法空壳，保证主流程不中断。"""
    return RagOutput(
        rag_references=[],
        rag_references_full=[],
        rag_product_knowledge=[],
        rag_forbidden_phrases=list(forbidden or []),
        retrieval_summary=RetrievalSummary(
            query_used=query_used,
            hit_count=0,
            confidence="low_confidence",
            reason=reason,
            embedding_model=embedder_name,
        ),
    )

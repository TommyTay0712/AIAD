"""Agent 4 的全部类型定义。

这里定义的数据结构就是 Agent 4 的"出厂规格书"，
任何上下游改动都必须经过这个 schema 层，避免字段散落。
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class MemoryDoc(BaseModel):
    """落盘到 Chroma 的单条记忆条目。"""

    id: str
    content: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class QuerySpec(BaseModel):
    """由 build_query 组装的结构化查询对象。"""

    semantic_text: str
    metadata_filter: dict[str, Any] = Field(default_factory=dict)
    signals: dict[str, Any] = Field(
        default_factory=dict,
        description="原始上游字段 (scene / target_style / pain_points 等)，供 ranker 加权",
    )


class RawHit(BaseModel):
    """Chroma 原始召回结果，尚未重排。"""

    id: str
    text: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    distance: float = Field(
        default=0.0,
        description="Chroma 返回的距离值，越小越相似",
    )


class RetrievalHit(BaseModel):
    """重排和去重之后的最终候选。给 Agent 5 消费。"""

    id: str
    text: str
    style: str = ""
    scene: str = ""
    pain_points: list[str] = Field(default_factory=list)
    score: float = 0.0
    matched_signals: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ProductKnowledge(BaseModel):
    """产品事实 / 可宣称卖点。"""

    point: str
    allowed_claim: bool = True
    evidence: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class RetrievalSummary(BaseModel):
    """Agent 4 自述本次检索的情况，便于 Agent 5/6 条件决策与排查。"""

    query_used: str = ""
    hit_count: int = 0
    confidence: str = "low_confidence"
    reason: str = ""
    embedding_model: str = ""


class RagOutput(BaseModel):
    """Agent 4 最终写回 global_state 的结构。

    为了向后兼容 Agent 5 目前读的 ``rag_references: list[str]``，
    这里仍保留字符串列表字段，同时追加结构化的 ``rag_references_full``。
    """

    rag_references: list[str] = Field(default_factory=list)
    rag_references_full: list[RetrievalHit] = Field(default_factory=list)
    rag_product_knowledge: list[ProductKnowledge] = Field(default_factory=list)
    rag_forbidden_phrases: list[str] = Field(default_factory=list)
    retrieval_summary: RetrievalSummary = Field(default_factory=RetrievalSummary)

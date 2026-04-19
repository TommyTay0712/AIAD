"""Agent 4 的唯一对外入口 run_rag_agent。

LangGraph 节点签名：state: dict -> state: dict。
任何异常都被吞掉，返回结构合法的空壳，绝不让主流程中断。
"""

from __future__ import annotations

import logging
from functools import lru_cache
from typing import Any

from app.services.memory.config import Agent4Settings, get_agent4_settings
from app.services.memory.embedder import Embedder, build_embedder
from app.services.memory.formatter import empty_output, format_retrieval_context
from app.services.memory.memory_store import MemoryStore
from app.services.memory.query_builder import build_query
from app.services.memory.ranker import mmr_deduplicate, rerank
from app.services.memory.schemas import ProductKnowledge, RagOutput
from app.services.memory.seed_loader import load_forbidden_phrases

logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def _cached_embedder(cache_key: str) -> Embedder:
    """按配置指纹缓存 embedder。cache_key 是 provider+model 的组合。"""
    settings = get_agent4_settings()
    return build_embedder(settings)


def _get_embedder(settings: Agent4Settings) -> Embedder:
    cache_key = f"{settings.embedding_provider}|{settings.embedding_model}"
    return _cached_embedder(cache_key)


def _pick_product_knowledge(
    store: MemoryStore,
    settings: Agent4Settings,
    product_info: str,
    embedder: Embedder,
    top_k: int = 5,
) -> list[ProductKnowledge]:
    """按产品描述做一次语义检索，取允许宣称的卖点。"""
    if not product_info.strip():
        return []
    query_text = settings.embedding_query_prefix + product_info.strip()
    try:
        vec = embedder.embed([query_text])[0]
    except Exception as exc:
        logger.warning("产品知识 embedding 失败 err=%s", exc)
        return []
    hits = store.query(
        name=settings.collection_product_knowledge,
        query_vector=vec,
        top_k=top_k,
    )
    result: list[ProductKnowledge] = []
    for hit in hits:
        meta = hit.metadata or {}
        allowed = meta.get("allowed_claim", True)
        if isinstance(allowed, str):
            allowed = allowed.lower() not in {"false", "0", "no"}
        if not allowed:
            continue
        result.append(
            ProductKnowledge(
                point=hit.text.strip(),
                allowed_claim=bool(allowed),
                evidence=str(meta.get("evidence", "")),
                metadata=meta,
            )
        )
    return result


def run_rag_agent(state: dict[str, Any]) -> dict[str, Any]:
    """LangGraph node 入口。

    - 只读 ``state['global_state']`` 的 request_info / vision_analysis / nlp_analysis。
    - 只追加字段到 ``state['global_state']``，不修改已有字段。
    - 永不抛异常；失败时返回结构合法的空壳（confidence=low_confidence）。
    """
    global_state: dict[str, Any] = dict(state.get("global_state") or {})
    output: RagOutput
    embedder_name = "unknown"
    query_used = ""
    forbidden: list[str] = []

    try:
        settings = get_agent4_settings()
        forbidden = load_forbidden_phrases(settings)
        embedder = _get_embedder(settings)
        embedder_name = embedder.model_name
        store = MemoryStore(settings, embedder)
        store.ensure_collections()

        query_spec = build_query(global_state, settings)
        query_used = query_spec.semantic_text
        query_vec = embedder.embed([query_spec.semantic_text])[0]

        raw_hits = store.query(
            name=settings.collection_ad_examples,
            query_vector=query_vec,
            top_k=settings.top_k_recall,
            where=query_spec.metadata_filter,
        )
        if not raw_hits:
            # 过滤条件太严时退一步：去掉 where 再查一次，增强冷启动鲁棒性。
            raw_hits = store.query(
                name=settings.collection_ad_examples,
                query_vector=query_vec,
                top_k=settings.top_k_recall,
            )

        scored_hits = rerank(raw_hits, query_spec.signals, forbidden)
        final_hits = mmr_deduplicate(
            scored_hits,
            lambda_=settings.mmr_lambda,
            max_k=settings.top_k_final,
            max_per_style=settings.max_per_style,
        )
        product_knowledge = _pick_product_knowledge(
            store=store,
            settings=settings,
            product_info=str(query_spec.signals.get("product_info", "")),
            embedder=embedder,
        )
        output = format_retrieval_context(
            final_hits=final_hits,
            product_knowledge=product_knowledge,
            forbidden=forbidden,
            query_spec=query_spec,
            embedder_name=embedder_name,
        )
        logger.info(
            "rag_agent ok hits=%s confidence=%s",
            output.retrieval_summary.hit_count,
            output.retrieval_summary.confidence,
        )
    except Exception as exc:
        logger.exception("rag_agent 执行失败，走 empty_output 兜底")
        output = empty_output(
            reason=f"agent4_error: {type(exc).__name__}: {str(exc)[:200]}",
            embedder_name=embedder_name,
            query_used=query_used,
            forbidden=forbidden,
        )

    new_global_state = dict(global_state)
    new_global_state.update(output.model_dump())
    new_state = dict(state)
    new_state["global_state"] = new_global_state
    return new_state

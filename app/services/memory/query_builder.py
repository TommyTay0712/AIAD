"""从 global_state 组装结构化查询。纯函数，无 I/O。"""

from __future__ import annotations

from typing import Any

from app.services.memory.config import Agent4Settings
from app.services.memory.schemas import QuerySpec

DEFAULT_PLATFORM = "小红书"
MAX_PAIN_POINTS = 5
MAX_DETECTED_ITEMS = 5


def _clean_list(raw: Any, limit: int) -> list[str]:
    if not isinstance(raw, list):
        return []
    cleaned: list[str] = []
    seen: set[str] = set()
    for item in raw:
        text = str(item).strip()
        if not text or text in seen:
            continue
        seen.add(text)
        cleaned.append(text)
        if len(cleaned) >= limit:
            break
    return cleaned


def _extract_signals(global_state: dict[str, Any]) -> dict[str, Any]:
    request_info = global_state.get("request_info") or {}
    vision = global_state.get("vision_analysis") or {}
    nlp = global_state.get("nlp_analysis") or {}
    return {
        "product_info": str(request_info.get("product_info", "")).strip(),
        "target_style": str(request_info.get("target_style", "")).strip() or "测评风",
        "scene": str(vision.get("scene", "")).strip(),
        "vibe": str(vision.get("vibe", "")).strip(),
        "detected_items": _clean_list(
            vision.get("detected_items"), MAX_DETECTED_ITEMS
        ),
        "main_emotion": str(nlp.get("main_emotion", "")).strip(),
        "pain_points": _clean_list(nlp.get("pain_points"), MAX_PAIN_POINTS),
        "language_style": str(nlp.get("language_style", "")).strip(),
    }


def _compose_semantic_text(signals: dict[str, Any]) -> str:
    parts: list[str] = []
    if signals["scene"]:
        parts.append(f"场景:{signals['scene']}")
    if signals["vibe"]:
        parts.append(f"氛围:{signals['vibe']}")
    if signals["pain_points"]:
        parts.append("痛点:" + ",".join(signals["pain_points"]))
    if signals["language_style"]:
        parts.append(f"语气:{signals['language_style']}")
    if signals["target_style"]:
        parts.append(f"风格:{signals['target_style']}")
    if signals["product_info"]:
        parts.append(f"产品:{signals['product_info']}")
    if not parts:
        return "通用软植入评论参考"
    return "；".join(parts)


def _build_metadata_filter(
    signals: dict[str, Any], settings: Agent4Settings
) -> dict[str, Any]:
    conditions: list[dict[str, Any]] = [{"platform": DEFAULT_PLATFORM}]
    if settings.min_quality_score > 0:
        conditions.append(
            {"quality_score": {"$gte": settings.min_quality_score}}
        )
    if len(conditions) == 1:
        return conditions[0]
    return {"$and": conditions}


def build_query(
    global_state: dict[str, Any], settings: Agent4Settings
) -> QuerySpec:
    """global_state -> QuerySpec。字段缺失时返回"冷启动"查询，不编造信号。"""
    signals = _extract_signals(global_state or {})
    semantic_text = _compose_semantic_text(signals)
    if settings.embedding_query_prefix:
        semantic_text = settings.embedding_query_prefix + semantic_text
    cold_start = not any(
        [
            signals["scene"],
            signals["pain_points"],
            signals["product_info"],
        ]
    )
    signals["cold_start"] = cold_start
    return QuerySpec(
        semantic_text=semantic_text,
        metadata_filter=_build_metadata_filter(signals, settings),
        signals=signals,
    )

"""重排 + MMR 去重 + 风控过滤。全部纯函数。"""

from __future__ import annotations

from app.services.memory.schemas import RawHit, RetrievalHit

W_STYLE = 0.30
W_SCENE = 0.20
W_PAIN_EACH = 0.15
W_QUALITY_BONUS = 0.10
QUALITY_THRESHOLD_FOR_BONUS = 0.9


def _parse_tag_list(raw: object) -> list[str]:
    """Chroma metadata 里我们把 list 存成 | 分隔字符串，这里反解析。"""
    if not raw:
        return []
    if isinstance(raw, list):
        return [str(item).strip() for item in raw if str(item).strip()]
    if isinstance(raw, str):
        return [item.strip() for item in raw.split("|") if item.strip()]
    return []


def _distance_to_relevance(distance: float) -> float:
    """Chroma 余弦距离 -> 相似度得分。距离越小相似度越高。"""
    return max(0.0, 1.0 - float(distance))


def _contains_forbidden(text: str, forbidden: list[str]) -> bool:
    if not forbidden:
        return False
    return any(word for word in forbidden if word and word in text)


def rerank(
    hits: list[RawHit],
    signals: dict,
    forbidden: list[str],
) -> list[RetrievalHit]:
    """按规则对粗召回结果加权重排；命中 forbidden 词的直接丢弃。"""
    target_style = str(signals.get("target_style", "")).strip()
    target_scene = str(signals.get("scene", "")).strip()
    target_pains: set[str] = set(
        str(p).strip() for p in signals.get("pain_points", []) if str(p).strip()
    )

    scored: list[RetrievalHit] = []
    for hit in hits:
        if _contains_forbidden(hit.text, forbidden):
            continue
        meta = hit.metadata or {}
        hit_style = str(meta.get("style", "")).strip()
        hit_scene = str(meta.get("scene", "")).strip()
        hit_pains = _parse_tag_list(meta.get("pain_point_tags"))
        hit_quality = float(meta.get("quality_score", 0.0) or 0.0)

        base = _distance_to_relevance(hit.distance)
        matched: list[str] = []
        score = base

        if target_style and hit_style == target_style:
            score += W_STYLE
            matched.append("style")
        if target_scene and hit_scene and target_scene == hit_scene:
            score += W_SCENE
            matched.append("scene")
        if target_pains:
            overlap = target_pains.intersection(hit_pains)
            if overlap:
                score += W_PAIN_EACH * len(overlap)
                matched.extend(f"pain_point:{p}" for p in overlap)
        if hit_quality >= QUALITY_THRESHOLD_FOR_BONUS:
            score += W_QUALITY_BONUS
            matched.append(f"quality>={QUALITY_THRESHOLD_FOR_BONUS}")

        scored.append(
            RetrievalHit(
                id=hit.id,
                text=hit.text,
                style=hit_style,
                scene=hit_scene,
                pain_points=hit_pains,
                score=round(score, 4),
                matched_signals=matched,
                metadata=meta,
            )
        )

    scored.sort(key=lambda h: h.score, reverse=True)
    return scored


def _text_overlap_ratio(a: str, b: str) -> float:
    """极简文本相似度：基于 3-gram 集合的 Jaccard。用于 MMR 去重，不追求精确。"""
    if not a or not b:
        return 0.0
    grams_a = {a[i : i + 3] for i in range(max(0, len(a) - 2))}
    grams_b = {b[i : i + 3] for i in range(max(0, len(b) - 2))}
    if not grams_a or not grams_b:
        return 0.0
    inter = len(grams_a & grams_b)
    union = len(grams_a | grams_b)
    return inter / union if union else 0.0


def mmr_deduplicate(
    hits: list[RetrievalHit],
    lambda_: float,
    max_k: int,
    max_per_style: int,
) -> list[RetrievalHit]:
    """对重排结果做多样性筛选。约束：同一 style 最多 max_per_style 条。"""
    if not hits:
        return []
    selected: list[RetrievalHit] = []
    style_counter: dict[str, int] = {}
    remaining = list(hits)

    while remaining and len(selected) < max_k:
        best_idx = -1
        best_score = float("-inf")
        for idx, cand in enumerate(remaining):
            style = cand.style or "_unknown"
            if style_counter.get(style, 0) >= max_per_style:
                continue
            if selected:
                max_sim = max(
                    _text_overlap_ratio(cand.text, chosen.text) for chosen in selected
                )
            else:
                max_sim = 0.0
            mmr_score = lambda_ * cand.score - (1 - lambda_) * max_sim
            if mmr_score > best_score:
                best_score = mmr_score
                best_idx = idx
        if best_idx < 0:
            break
        chosen = remaining.pop(best_idx)
        selected.append(chosen)
        style_counter[chosen.style or "_unknown"] = (
            style_counter.get(chosen.style or "_unknown", 0) + 1
        )
    return selected

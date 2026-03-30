from __future__ import annotations

from typing import Any


def _relevance_score(ad_type: str, text: str, labels: list[str]) -> float:
    score = 0.2
    if ad_type and ad_type in text:
        score += 0.4
    if labels:
        score += 0.2
    return min(1.0, score)


def build_opportunities(
    *,
    ad_type: str,
    normalized_data: dict[str, Any],
) -> dict[str, Any]:
    """根据特征表构建投放机会输出。"""
    contents = normalized_data["content_table"]
    features = {item["note_id"]: item for item in normalized_data["feature_table"]}
    sorted_content = sorted(
        contents,
        key=lambda item: (
            item["like_count"] + item["comment_count"] + item.get("collect_count", 0),
            _relevance_score(
                ad_type,
                f"{item['title']} {item['desc']}",
                features.get(item["note_id"], {}).get("intent_labels", []),
            ),
        ),
        reverse=True,
    )
    hot_contents = [
        {
            "note_id": item["note_id"],
            "note_url": item["note_url"],
            "title": item["title"],
            "engagement": item["like_count"] + item["comment_count"] + item.get("collect_count", 0),
            "relevance_score": _relevance_score(
                ad_type,
                f"{item['title']} {item['desc']}",
                features.get(item["note_id"], {}).get("intent_labels", []),
            ),
        }
        for item in sorted_content[:10]
    ]

    pain_points = []
    placements = []
    suggestions = []
    for item in hot_contents:
        feature = features.get(item["note_id"], {})
        pain_points.append(
            {
                "note_id": item["note_id"],
                "note_url": item["note_url"],
                "pain_points": feature.get("pain_points", []),
            }
        )
        placements.append(
            {
                "note_id": item["note_id"],
                "note_url": item["note_url"],
                "topic_cluster": feature.get("topic_cluster", "general"),
                "placement_hint": "在真实使用场景中植入产品对比与结果展示",
            }
        )
        suggestions.append(
            {
                "note_id": item["note_id"],
                "note_url": item["note_url"],
                "audience": feature.get("audience_profile", "泛人群"),
                "creative_direction": (
                    f"{ad_type}可围绕"
                    f"{','.join(feature.get('intent_labels', ['场景']))}"
                    "制作短视频素材"
                ),
                "keywords": feature.get("intent_labels", []),
                "risk_flags": feature.get("risk_flags", []),
            }
        )

    return {
        "hot_contents": hot_contents,
        "user_pain_points": pain_points,
        "placement_scenarios": placements,
        "ad_recommendations": suggestions,
    }

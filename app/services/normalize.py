from __future__ import annotations

import json
import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def parse_cn_number(value: Any) -> int:
    """将中文数字文本转换为整数。"""
    if value is None:
        return 0
    if isinstance(value, int | float):
        return int(value)
    text = str(value).strip().replace(",", "")
    if not text:
        return 0
    try:
        if text.endswith("万"):
            return int(float(text[:-1]) * 10000)
        return int(float(text))
    except ValueError:
        return 0


def clean_text(value: Any) -> str:
    """清洗文本中的空白与异常字符。"""
    if value is None:
        return ""
    text = str(value)
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def normalize_time(value: Any) -> str:
    """标准化时间字段为ISO字符串。"""
    if value is None:
        return ""
    text = clean_text(value)
    if not text:
        return ""
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d", "%Y/%m/%d %H:%M:%S", "%Y/%m/%d"):
        try:
            return datetime.strptime(text, fmt).isoformat()
        except ValueError:
            continue
    return text


def read_jsonl(file_path: Path) -> list[dict[str, Any]]:
    """读取JSONL文件。"""
    if not file_path.exists():
        return []
    rows: list[dict[str, Any]] = []
    with file_path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                logger.error("JSONL解析失败 file=%s line=%s", file_path, line[:120])
    return rows


def parse_media_urls(value: Any) -> list[str]:
    text = clean_text(value)
    if not text:
        return []
    return [item.strip() for item in text.split(",") if item.strip()]


def collect_media_paths(media_root_dir: Path | None, note_id: str) -> tuple[list[str], list[str]]:
    if not media_root_dir:
        return ([], [])
    image_dir = media_root_dir / "images" / note_id
    video_dir = media_root_dir / "videos" / note_id
    image_paths = (
        sorted(str(path.resolve()) for path in image_dir.glob("*") if path.is_file())
        if image_dir.exists()
        else []
    )
    video_paths = (
        sorted(str(path.resolve()) for path in video_dir.glob("*") if path.is_file())
        if video_dir.exists()
        else []
    )
    return (image_paths, video_paths)


def _topic_cluster(text: str) -> str:
    if any(token in text for token in ["护肤", "成分", "敏感"]):
        return "beauty_care"
    if any(token in text for token in ["健身", "减脂", "运动"]):
        return "fitness"
    if any(token in text for token in ["母婴", "宝宝", "育儿"]):
        return "parenting"
    return "general"


def _sentiment_score(text: str) -> float:
    positive = ["推荐", "好用", "喜欢", "有效", "回购"]
    negative = ["踩雷", "无效", "差", "刺激", "失望"]
    score = 0
    for item in positive:
        if item in text:
            score += 1
    for item in negative:
        if item in text:
            score -= 1
    return max(-1.0, min(1.0, score / 3))


def _intent_labels(text: str) -> list[str]:
    mapping = {
        "功效": ["有效", "改善", "提亮", "保湿", "修复"],
        "价格": ["便宜", "价格", "预算", "性价比"],
        "成分": ["成分", "烟酰胺", "玻尿酸", "A醇"],
        "场景": ["通勤", "熬夜", "换季", "约会", "出差"],
        "品牌": ["品牌", "大牌", "平替"],
    }
    labels = [label for label, words in mapping.items() if any(word in text for word in words)]
    return labels or ["场景"]


def _pain_points(text: str) -> list[str]:
    points = []
    if any(item in text for item in ["敏感", "刺激", "泛红"]):
        points.append("低敏诉求")
    if any(item in text for item in ["贵", "预算", "价格"]):
        points.append("价格敏感")
    if any(item in text for item in ["没效果", "无效", "失望"]):
        points.append("效果不确定")
    return points or ["需求待挖掘"]


def _risk_flags(text: str) -> list[str]:
    flags = []
    if any(item in text for item in ["医美", "治疗", "药效"]):
        flags.append("合规表述风险")
    if any(item in text for item in ["夸张", "虚假", "骗局"]):
        flags.append("真实性风险")
    return flags


def _audience_profile(content: dict[str, Any], comment_text: str) -> str:
    author = clean_text(content.get("author_name") or "")
    if "学生" in comment_text:
        return "学生党"
    if any(item in comment_text for item in ["宝妈", "带娃"]):
        return "宝妈人群"
    if author:
        return f"{author}相关受众"
    return "泛人群"


def normalize_dataset(
    *,
    platform: str,
    source_keyword: str,
    content_file: Path,
    comment_file: Path | None,
    media_root_dir: Path | None = None,
) -> dict[str, Any]:
    """将爬虫原始数据转换为标准化数据表。"""
    raw_contents = read_jsonl(content_file)
    raw_comments = read_jsonl(comment_file) if comment_file else []

    content_table: list[dict[str, Any]] = []
    seen_content: set[tuple[str, str]] = set()
    for row in raw_contents:
        note_id = clean_text(row.get("note_id") or row.get("aweme_id") or row.get("id"))
        if not note_id:
            continue
        dedupe_key = (platform, note_id)
        if dedupe_key in seen_content:
            continue
        seen_content.add(dedupe_key)
        item = {
            "platform": platform,
            "note_id": note_id,
            "title": clean_text(row.get("title")),
            "desc": clean_text(row.get("desc") or row.get("content")),
            "tags": row.get("tags") or [],
            "publish_time": normalize_time(row.get("time") or row.get("publish_time")),
            "like_count": parse_cn_number(row.get("liked_count") or row.get("like_count")),
            "comment_count": parse_cn_number(row.get("comments_count") or row.get("comment_count")),
            "collect_count": parse_cn_number(
                row.get("collected_count") or row.get("collect_count")
            ),
            "share_count": parse_cn_number(row.get("share_count")),
            "author_id": clean_text(row.get("user_id") or row.get("author_id")),
            "author_name": clean_text(row.get("nickname") or row.get("author_name")),
            "note_url": clean_text(row.get("note_url") or row.get("url")),
            "source_keyword": source_keyword,
        }
        image_urls = parse_media_urls(row.get("image_list"))
        video_urls = parse_media_urls(row.get("video_url") or row.get("video_download_url"))
        image_paths, video_paths = collect_media_paths(media_root_dir, note_id)
        item["image_urls"] = image_urls
        item["video_urls"] = video_urls
        item["image_local_paths"] = image_paths
        item["video_local_paths"] = video_paths
        item["media_local_paths"] = image_paths + video_paths
        item["has_media"] = bool(image_urls or video_urls or image_paths or video_paths)
        content_table.append(item)

    comment_table: list[dict[str, Any]] = []
    seen_comment: set[tuple[str, str]] = set()
    for row in raw_comments:
        comment_id = clean_text(row.get("comment_id") or row.get("id"))
        note_id = clean_text(row.get("note_id"))
        if not comment_id:
            continue
        dedupe_key = (platform, comment_id)
        if dedupe_key in seen_comment:
            continue
        seen_comment.add(dedupe_key)
        comment_table.append(
            {
                "platform": platform,
                "note_id": note_id,
                "comment_id": comment_id,
                "comment_text": clean_text(row.get("content") or row.get("comment_text")),
                "comment_time": normalize_time(row.get("create_time") or row.get("comment_time")),
                "like_count": parse_cn_number(
                    row.get("sub_comment_count") or row.get("like_count")
                ),
                "ip_location": clean_text(row.get("ip_location")),
                "parent_comment_id": clean_text(row.get("parent_comment_id")),
            }
        )

    comment_by_note: dict[str, list[dict[str, Any]]] = {}
    for comment in comment_table:
        comment_by_note.setdefault(comment["note_id"], []).append(comment)

    feature_table: list[dict[str, Any]] = []
    for content in content_table:
        comments = comment_by_note.get(content["note_id"], [])
        joined_text = " ".join(
            [content["title"], content["desc"], *[c["comment_text"] for c in comments]]
        )
        topic = _topic_cluster(joined_text)
        sentiment = _sentiment_score(joined_text)
        intents = _intent_labels(joined_text)
        pain_points = _pain_points(joined_text)
        risks = _risk_flags(joined_text)
        fit_score = round(
            (
                content["like_count"] * 0.4
                + content["comment_count"] * 0.3
                + (sentiment + 1) * 50
            )
            / 100,
            4,
        )
        feature_table.append(
            {
                "platform": content["platform"],
                "note_id": content["note_id"],
                "topic_cluster": topic,
                "sentiment_score": sentiment,
                "intent_labels": intents,
                "pain_points": pain_points,
                "ad_fit_score": fit_score,
                "risk_flags": risks,
                "audience_profile": _audience_profile(content, joined_text),
            }
        )

    summary = {
        "platform": platform,
        "source_keyword": source_keyword,
        "content_count": len(content_table),
        "comment_count": len(comment_table),
        "feature_count": len(feature_table),
        "media_note_count": len([row for row in content_table if row.get("has_media")]),
        "image_file_count": sum(len(row.get("image_local_paths", [])) for row in content_table),
        "video_file_count": sum(len(row.get("video_local_paths", [])) for row in content_table),
    }
    return {
        "summary": summary,
        "content_table": content_table,
        "comment_table": comment_table,
        "feature_table": feature_table,
    }

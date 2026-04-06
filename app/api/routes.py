from __future__ import annotations

import json
import logging
import re
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException

from app.core.config import Settings, get_settings
from app.models.schemas import (
    AnalyzeOutput,
    ErrorCode,
    RunRequest,
    TaskRecord,
    TaskResponse,
    TaskStatus,
)
from app.services.chroma_store import ChromaStore
from app.services.crawler_runner import run_crawler
from app.services.normalize import normalize_dataset
from app.services.task_store import TaskStore
from app.workflows.data_graph import run_data_workflow

router = APIRouter(prefix="/api/ad-intel", tags=["ad-intel"])
logger = logging.getLogger(__name__)


def _task_store(settings: Settings = Depends(get_settings)) -> TaskStore:
    return TaskStore(settings.task_store_file)


def _run_pipeline_task(task_id: str, payload: RunRequest, settings: Settings) -> None:
    task_store = TaskStore(settings.task_store_file)
    keywords = payload.keywords or [payload.ad_type]
    try:
        crawler = run_crawler(
            settings=settings,
            task_store=task_store,
            platform=payload.platform,
            keywords=keywords,
            limit=payload.limit,
            max_comments_per_note=payload.max_comments_per_note,
            enable_media_download=payload.enable_media_download,
            task_id=task_id,
        )
        if crawler.status == TaskStatus.FAILED:
            return

        content_file = Path(crawler.output_files.get("content_file", ""))
        if not content_file.exists():
            record = task_store.get(task_id)
            if record:
                record.status = TaskStatus.FAILED
                record.error_code = ErrorCode.CRAWLER_ERROR
                record.error_message = "未找到内容数据文件"
                task_store.upsert(record)
            return

        comment_file_raw = crawler.output_files.get("comment_file")
        comment_file = Path(comment_file_raw) if comment_file_raw else None
        normalized = normalize_dataset(
            platform=payload.platform,
            source_keyword=",".join(keywords),
            content_file=content_file,
            comment_file=comment_file,
            media_root_dir=Path(crawler.output_files["media_root_dir"])
            if crawler.output_files.get("media_root_dir")
            else None,
        )
        final_payload = run_data_workflow(normalized)
        chroma_counts = ChromaStore(settings.chroma_persist_dir).write_task_payload(
            task_id,
            final_payload,
        )
        processed_path = settings.processed_output_dir / f"{task_id}_normalized.json"
        processed_path.write_text(
            json.dumps(final_payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        record = task_store.get(task_id)
        if record:
            record.status = TaskStatus.SUCCESS
            record.result = {"processed_file": str(processed_path), "chroma_counts": chroma_counts}
            record.error_code = None
            record.error_message = ""
            task_store.upsert(record)
        logger.info("数据整理完成 task_id=%s output=%s", task_id, processed_path)
    except Exception as exc:
        logger.error("任务执行异常 task_id=%s error=%s", task_id, str(exc))
        record = task_store.get(task_id)
        if record:
            record.status = TaskStatus.FAILED
            record.error_code = ErrorCode.INTERNAL_ERROR
            record.error_message = str(exc)[:1000]
            task_store.upsert(record)


def _load_task_payload(task_id: str, task_store: TaskStore) -> tuple[TaskRecord, dict[str, Any]]:
    record = task_store.get(task_id)
    if not record:
        raise HTTPException(status_code=404, detail="task not found")
    if record.status != TaskStatus.SUCCESS:
        raise HTTPException(status_code=409, detail="task not completed")
    processed_file = record.result.get("processed_file")
    if not processed_file:
        raise HTTPException(status_code=404, detail="processed file not found")
    result_file = Path(processed_file)
    if not result_file.exists():
        raise HTTPException(status_code=404, detail="processed file not exists")
    return record, json.loads(result_file.read_text(encoding="utf-8"))


def _guess_sentiment(text: str) -> str:
    positive_words = (
        "喜欢",
        "好",
        "推荐",
        "不错",
        "满意",
        "划算",
        "值得",
        "棒",
        "love",
        "great",
        "good",
    )
    negative_words = (
        "差",
        "不好",
        "贵",
        "坑",
        "失望",
        "一般",
        "垃圾",
        "踩雷",
        "bad",
        "expensive",
        "worse",
    )
    lower_text = text.lower()
    pos_score = sum(word in lower_text for word in positive_words)
    neg_score = sum(word in lower_text for word in negative_words)
    if pos_score > neg_score:
        return "positive"
    if neg_score > pos_score:
        return "negative"
    return "neutral"


def _build_review_queue(payload: dict[str, Any], limit: int = 20) -> list[dict[str, Any]]:
    content_map = {
        item.get("note_id", ""): item
        for item in payload.get("content_table", [])
        if isinstance(item, dict)
    }
    queue: list[dict[str, Any]] = []
    for index, comment in enumerate(payload.get("comment_table", [])):
        if not isinstance(comment, dict):
            continue
        text = str(comment.get("comment_text", "")).strip()
        if not text:
            continue
        sentiment = _guess_sentiment(text)
        affinity_map = {"positive": 92, "neutral": 76, "negative": 58}
        focus_map = {"positive": "种草转化", "neutral": "品牌曝光", "negative": "痛点回应"}
        note_id = comment.get("note_id", "")
        source_meta = content_map.get(note_id, {})
        queue.append(
            {
                "comment_id": comment.get("comment_id") or f"{note_id}-{index}",
                "author": source_meta.get("author_name", "匿名用户"),
                "platform": "小红书",
                "source_text": text[:220],
                "ad_text": (
                    f"看到你提到“{text[:28]}”，我们准备了更贴近真实场景的解决方案，"
                    "欢迎查看详细体验与案例对比。"
                ),
                "predicted_affinity": affinity_map.get(sentiment, 70),
                "focus": focus_map.get(sentiment, "品牌曝光"),
                "sentiment": sentiment,
            }
        )
        if len(queue) >= limit:
            break
    return queue


def _build_topic_cloud(payload: dict[str, Any], limit: int = 12) -> list[dict[str, Any]]:
    source_text = []
    for row in payload.get("feature_table", []):
        if isinstance(row, dict) and row.get("topic_cluster"):
            source_text.append(str(row.get("topic_cluster", "")))
    for row in payload.get("content_table", [])[:200]:
        if isinstance(row, dict):
            source_text.append(str(row.get("title", "")))
            source_text.append(str(row.get("desc", "")))
    tokens = re.findall(r"[\u4e00-\u9fa5]{2,}|[A-Za-z]{3,}", " ".join(source_text))
    stopwords = {
        "我们",
        "这个",
        "那个",
        "就是",
        "the",
        "and",
        "for",
        "with",
        "that",
        "from",
        "this",
    }
    filtered = [token for token in tokens if token.lower() not in stopwords]
    counter = Counter(filtered)
    classes = [
        "text-5xl font-black text-primary-container",
        "text-4xl font-extrabold text-primary",
        "text-3xl font-bold text-secondary",
        "text-2xl font-semibold text-tertiary-container",
        "text-xl font-medium text-on-surface-variant",
    ]
    cloud = []
    for index, item in enumerate(counter.most_common(limit)):
        cloud.append({"word": item[0], "className": classes[index % len(classes)]})
    return cloud


def _build_sentiment_bars(payload: dict[str, Any]) -> list[dict[str, Any]]:
    counts = {"positive": 0, "neutral": 0, "negative": 0}
    for row in payload.get("comment_table", []):
        if not isinstance(row, dict):
            continue
        sentiment = _guess_sentiment(str(row.get("comment_text", "")))
        counts[sentiment] += 1
    total = max(1, sum(counts.values()))
    positive = round(counts["positive"] * 100 / total)
    neutral = round(counts["neutral"] * 100 / total)
    negative = max(0, 100 - positive - neutral)
    return [
        {"label": "POSITIVE", "value": positive, "colorClass": "bg-secondary"},
        {"label": "NEUTRAL", "value": neutral, "colorClass": "bg-tertiary-container"},
        {"label": "NEGATIVE", "value": negative, "colorClass": "bg-error"},
    ]


def _build_progress(record: TaskRecord, payload: dict[str, Any]) -> dict[str, Any]:
    if record.status == TaskStatus.SUCCESS:
        step = {"current": 4, "total": 4, "label": "Final Report", "percent": 100}
    elif record.status == TaskStatus.RUNNING:
        step = {"current": 3, "total": 4, "label": "Content Synthesis", "percent": 68}
    else:
        step = {"current": 4, "total": 4, "label": "Failed", "percent": 100}
    summary = payload.get("summary", {}) if isinstance(payload, dict) else {}
    now = datetime.now().strftime("%H:%M:%S")
    return {
        "step": step,
        "metrics": {
            "posts_scanned": int(summary.get("content_count", 0)),
            "comments_read": int(summary.get("comment_count", 0)),
        },
        "logs": [
            f"{now} [SYSTEM] 任务状态：{record.status.value}",
            f"{now} [CRAWLER] 内容条数：{summary.get('content_count', 0)}",
            f"{now} [ANALYSIS] 评论条数：{summary.get('comment_count', 0)}",
            f"{now} [FEATURE] 特征条数：{summary.get('feature_count', 0)}",
        ],
    }


@router.post("/run", response_model=TaskResponse)
def run_analysis(
    payload: RunRequest,
    background_tasks: BackgroundTasks,
    settings: Settings = Depends(get_settings),
    task_store: TaskStore = Depends(_task_store),
) -> TaskResponse:
    """执行广告分析任务。"""
    if not payload.ad_type.strip():
        raise HTTPException(
            status_code=422,
            detail={"error_code": ErrorCode.INVALID_INPUT.value, "message": "ad_type不能为空"},
        )
    task_id = uuid4().hex[:12]
    record = TaskRecord(
        task_id=task_id,
        status=TaskStatus.RUNNING,
        created_at=datetime.now(),
        updated_at=datetime.now(),
        params={
            "ad_type": payload.ad_type,
            "keywords": payload.keywords,
            "platform": payload.platform,
            "limit": payload.limit,
            "max_comments_per_note": payload.max_comments_per_note,
            "enable_media_download": payload.enable_media_download,
            "time_range": payload.time_range,
        },
    )
    task_store.upsert(record)
    background_tasks.add_task(_run_pipeline_task, task_id, payload, settings)
    return TaskResponse(
        task_id=task_id,
        status=TaskStatus.RUNNING,
        message="任务已提交，正在抓取并整理数据",
    )


@router.get("/task/{task_id}", response_model=AnalyzeOutput | TaskResponse)
def get_task_result(
    task_id: str,
    settings: Settings = Depends(get_settings),
    task_store: TaskStore = Depends(_task_store),
) -> AnalyzeOutput | TaskResponse:
    """获取任务状态与结果。"""
    record = task_store.get(task_id)
    if not record:
        raise HTTPException(status_code=404, detail="task not found")
    if record.status != TaskStatus.SUCCESS:
        return TaskResponse(
            task_id=task_id,
            status=record.status,
            error_code=record.error_code,
            message=record.error_message,
        )
    processed_file = record.result.get("processed_file")
    if not processed_file:
        return TaskResponse(
            task_id=task_id,
            status=TaskStatus.RUNNING,
            message="结果生成中，请稍后重试",
        )
    result_file = Path(processed_file)
    if not result_file.exists():
        return TaskResponse(
            task_id=task_id,
            status=TaskStatus.FAILED,
            error_code=ErrorCode.INTERNAL_ERROR,
            message="结果文件不存在",
        )
    payload = json.loads(result_file.read_text(encoding="utf-8"))
    return AnalyzeOutput.model_validate(payload)


@router.get("/task/{task_id}/meta", response_model=dict[str, Any])
def get_task_meta(
    task_id: str,
    settings: Settings = Depends(get_settings),
    task_store: TaskStore = Depends(_task_store),
) -> dict[str, Any]:
    record = task_store.get(task_id)
    if not record:
        raise HTTPException(status_code=404, detail="task not found")
    result = record.result or {}
    return {
        "task_id": task_id,
        "status": record.status,
        "error_code": record.error_code,
        "message": record.error_message,
        "processed_file": result.get("processed_file", ""),
        "chroma_counts": result.get("chroma_counts", {}),
        "params": record.params,
        "updated_at": record.updated_at.isoformat(),
    }


@router.get("/task/{task_id}/insights", response_model=dict[str, Any])
def get_task_insights(
    task_id: str,
    task_store: TaskStore = Depends(_task_store),
) -> dict[str, Any]:
    record, payload = _load_task_payload(task_id, task_store)
    summary = payload.get("summary", {}) if isinstance(payload, dict) else {}
    review_queue = _build_review_queue(payload)
    sentiment_bars = _build_sentiment_bars(payload)
    topic_cloud = _build_topic_cloud(payload)
    completed_tasks = len(
        [
            item
            for item in task_store.list_recent(limit=200)
            if item.status == TaskStatus.SUCCESS
        ]
    )
    efficiency = min(99, 65 + int(summary.get("feature_count", 0) / 2))
    return {
        "task_id": task_id,
        "review_queue": review_queue,
        "progress": _build_progress(record, payload),
        "analytics": {
            "kpis": {
                "comment_count": int(summary.get("comment_count", 0)),
                "content_count": int(summary.get("content_count", 0)),
                "dispatch_efficiency": efficiency,
                "completed_tasks": completed_tasks,
            },
            "sentiment_bars": sentiment_bars,
            "topic_cloud": topic_cloud,
            "insight": "高意向评论集中在‘真实体验+效果对比’语义簇，建议优先派发该类文案。",
        },
    }


@router.get("/tasks/recent", response_model=list[dict[str, Any]])
def get_recent_tasks(
    limit: int = 10,
    task_store: TaskStore = Depends(_task_store),
) -> list[dict[str, Any]]:
    records = task_store.list_recent(limit=limit)
    return [
        {
            "task_id": item.task_id,
            "status": item.status,
            "updated_at": item.updated_at.isoformat(),
            "error_message": item.error_message,
            "params": item.params,
        }
        for item in records
    ]

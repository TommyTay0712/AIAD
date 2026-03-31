from __future__ import annotations

import json
import logging
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

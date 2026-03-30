from __future__ import annotations

import json
import logging
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException

from app.core.config import Settings, get_settings
from app.models.schemas import AnalyzeOutput, ErrorCode, RunRequest, TaskResponse, TaskStatus
from app.services.crawler_runner import run_crawler
from app.services.normalize import normalize_dataset
from app.services.task_store import TaskStore
from app.workflows.data_graph import run_data_workflow

router = APIRouter(prefix="/api/ad-intel", tags=["ad-intel"])
logger = logging.getLogger(__name__)


def _task_store(settings: Settings = Depends(get_settings)) -> TaskStore:
    return TaskStore(settings.task_store_file)


@router.post("/run", response_model=TaskResponse)
def run_analysis(
    payload: RunRequest,
    settings: Settings = Depends(get_settings),
    task_store: TaskStore = Depends(_task_store),
) -> TaskResponse:
    """执行广告分析任务。"""
    if not payload.ad_type.strip():
        raise HTTPException(
            status_code=422,
            detail={"error_code": ErrorCode.INVALID_INPUT.value, "message": "ad_type不能为空"},
        )
    keywords = payload.keywords or [payload.ad_type]
    crawler = run_crawler(
        settings=settings,
        task_store=task_store,
        platform=payload.platform,
        keywords=keywords,
        limit=payload.limit,
    )
    if crawler.status == TaskStatus.FAILED:
        raise HTTPException(
            status_code=400,
            detail={"error_code": crawler.error_code, "message": crawler.error_message},
        )

    content_file = Path(crawler.output_files.get("content_file", ""))
    if not content_file.exists():
        raise HTTPException(
            status_code=400,
            detail={"error_code": ErrorCode.CRAWLER_ERROR.value, "message": "未找到内容数据文件"},
        )
    comment_file_raw = crawler.output_files.get("comment_file")
    comment_file = Path(comment_file_raw) if comment_file_raw else None
    normalized = normalize_dataset(
        platform=payload.platform,
        source_keyword=",".join(keywords),
        content_file=content_file,
        comment_file=comment_file,
    )
    final_payload = run_data_workflow(normalized)

    processed_path = settings.processed_output_dir / f"{crawler.task_id}_normalized.json"
    processed_path.write_text(
        json.dumps(final_payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    record = task_store.get(crawler.task_id)
    if record:
        record.result = {"processed_file": str(processed_path)}
        task_store.upsert(record)

    logger.info("数据整理完成 task_id=%s output=%s", crawler.task_id, processed_path)
    return TaskResponse(
        task_id=crawler.task_id,
        status=TaskStatus.SUCCESS,
        message=str(processed_path),
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
    result_file = Path(record.result.get("processed_file", ""))
    if not result_file.exists():
        return TaskResponse(
            task_id=task_id,
            status=TaskStatus.FAILED,
            error_code=ErrorCode.INTERNAL_ERROR,
            message="结果文件不存在",
        )
    payload = json.loads(result_file.read_text(encoding="utf-8"))
    return AnalyzeOutput.model_validate(payload)

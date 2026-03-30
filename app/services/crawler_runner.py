from __future__ import annotations

import logging
import shutil
import subprocess
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from app.core.config import Settings
from app.models.schemas import ErrorCode, TaskRecord, TaskStatus
from app.services.task_store import TaskStore

logger = logging.getLogger(__name__)


@dataclass
class CrawlerRunResult:
    task_id: str
    status: TaskStatus
    output_files: dict[str, str]
    error_code: ErrorCode | None = None
    error_message: str = ""


def _detect_login_required(stdout: str, stderr: str) -> bool:
    """识别登录失效场景。"""
    merged = f"{stdout}\n{stderr}".lower()
    keywords = ["qrcode", "scan", "login", "登录", "cookie失效", "未登录"]
    return any(item in merged for item in keywords)


def _collect_latest_jsonl(source_dir: Path) -> tuple[Path | None, Path | None]:
    """收集最近生成的内容与评论JSONL文件。"""
    contents = sorted(source_dir.rglob("search_contents_*.jsonl"), key=lambda p: p.stat().st_mtime)
    comments = sorted(source_dir.rglob("search_comments_*.jsonl"), key=lambda p: p.stat().st_mtime)
    return (contents[-1] if contents else None, comments[-1] if comments else None)


def run_crawler(
    *,
    settings: Settings,
    task_store: TaskStore,
    platform: str,
    keywords: list[str],
    limit: int,
) -> CrawlerRunResult:
    """执行MediaCrawler并将输出收口到AIAD目录。"""
    task_id = uuid4().hex[:12]
    record = TaskRecord(
        task_id=task_id,
        created_at=datetime.now(),
        updated_at=datetime.now(),
        status=TaskStatus.RUNNING,
        params={"platform": platform, "keywords": keywords, "limit": limit},
    )
    task_store.upsert(record)

    command = [
        "python",
        "main.py",
        "--platform",
        platform,
        "--lt",
        "qrcode",
        "--type",
        "search",
        "--keywords",
        ",".join(keywords),
        "--save_data_option",
        "jsonl",
        "--headless",
        "false",
    ]
    logger.info("开始执行爬虫 task_id=%s command=%s", task_id, " ".join(command))
    result = subprocess.run(
        command,
        cwd=settings.media_crawler_dir,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    if result.returncode != 0:
        error_code = ErrorCode.CRAWLER_ERROR
        if _detect_login_required(result.stdout, result.stderr):
            error_code = ErrorCode.LOGIN_REQUIRED
        error_message = (result.stderr or result.stdout).strip()[:1000]
        record.status = TaskStatus.FAILED
        record.error_code = error_code
        record.error_message = error_message
        task_store.upsert(record)
        logger.error("爬虫执行失败 task_id=%s error=%s", task_id, error_message)
        return CrawlerRunResult(
            task_id=task_id,
            status=TaskStatus.FAILED,
            output_files={},
            error_code=error_code,
            error_message=error_message,
        )

    source_data_dir = settings.media_crawler_dir / "data"
    content_file, comment_file = _collect_latest_jsonl(source_data_dir)
    output_files: dict[str, str] = {}
    if content_file:
        target_content = settings.crawler_output_dir / f"{task_id}_search_contents.jsonl"
        shutil.copy2(content_file, target_content)
        output_files["content_file"] = str(target_content)
    if comment_file:
        target_comment = settings.crawler_output_dir / f"{task_id}_search_comments.jsonl"
        shutil.copy2(comment_file, target_comment)
        output_files["comment_file"] = str(target_comment)

    record.status = TaskStatus.SUCCESS
    record.output_files = output_files
    task_store.upsert(record)
    logger.info("爬虫执行成功 task_id=%s outputs=%s", task_id, output_files)
    return CrawlerRunResult(task_id=task_id, status=TaskStatus.SUCCESS, output_files=output_files)

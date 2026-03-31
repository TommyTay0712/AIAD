from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
from collections import defaultdict
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
    keywords = [
        "login state result: false",
        "waiting for scan code login",
        "cookie失效",
        "未登录",
        "login_by_qrcode",
        "timeouterror: locator.click",
    ]
    return any(item in merged for item in keywords)


def _clean_runtime_logs(raw_text: str) -> str:
    lines = raw_text.splitlines()
    filtered = [
        line
        for line in lines
        if "pkg_resources is deprecated as an API" not in line
        and "setuptools.pypa.io/en/latest/pkg_resources.html" not in line
    ]
    return "\n".join(filtered).strip()


def _build_error_message(stdout: str, stderr: str, max_chars: int = 1500) -> str:
    merged = _clean_runtime_logs(f"{stderr}\n{stdout}".strip())
    if not merged:
        merged = f"{stderr}\n{stdout}".strip()
    return merged[-max_chars:] if len(merged) > max_chars else merged


def _collect_latest_jsonl(source_dir: Path) -> tuple[Path | None, Path | None]:
    """收集最近生成的内容与评论JSONL文件。"""
    contents = sorted(source_dir.rglob("search_contents_*.jsonl"), key=lambda p: p.stat().st_mtime)
    comments = sorted(source_dir.rglob("search_comments_*.jsonl"), key=lambda p: p.stat().st_mtime)
    return (contents[-1] if contents else None, comments[-1] if comments else None)


def _is_recent_file(file_path: Path | None, max_age_seconds: int = 21600) -> bool:
    if not file_path:
        return False
    age_seconds = datetime.now().timestamp() - file_path.stat().st_mtime
    return age_seconds <= max_age_seconds


def _extract_source_keywords(content_file: Path | None, max_lines: int = 60) -> set[str]:
    if not content_file or not content_file.exists():
        return set()
    detected: set[str] = set()
    with content_file.open("r", encoding="utf-8") as handle:
        for idx, line in enumerate(handle):
            if idx >= max_lines:
                break
            text = line.strip()
            if not text:
                continue
            try:
                row = json.loads(text)
            except json.JSONDecodeError:
                continue
            keyword = str(row.get("source_keyword", "")).strip()
            if keyword:
                detected.add(keyword)
    return detected


def _is_keyword_match(content_file: Path | None, keywords: list[str]) -> bool:
    if not keywords:
        return True
    expected = {item.strip().lower() for item in keywords if item.strip()}
    if not expected:
        return True
    detected = {item.lower() for item in _extract_source_keywords(content_file)}
    if not detected:
        return False
    return bool(expected & detected)


def _trim_jsonl_outputs(
    content_path: Path,
    comment_path: Path | None,
    max_notes: int,
    max_comments_per_note: int,
) -> tuple[int, int]:
    content_rows: list[dict] = []
    with content_path.open("r", encoding="utf-8") as handle:
        for line in handle:
            text = line.strip()
            if not text:
                continue
            try:
                row = json.loads(text)
            except json.JSONDecodeError:
                continue
            content_rows.append(row)
            if len(content_rows) >= max_notes:
                break
    kept_note_ids = {str(item.get("note_id", "")) for item in content_rows if item.get("note_id")}
    with content_path.open("w", encoding="utf-8") as handle:
        for item in content_rows:
            handle.write(json.dumps(item, ensure_ascii=False) + "\n")

    kept_comments = 0
    if comment_path and comment_path.exists():
        comment_counts: dict[str, int] = defaultdict(int)
        comment_rows: list[dict] = []
        with comment_path.open("r", encoding="utf-8") as handle:
            for line in handle:
                text = line.strip()
                if not text:
                    continue
                try:
                    row = json.loads(text)
                except json.JSONDecodeError:
                    continue
                note_id = str(row.get("note_id", ""))
                if note_id not in kept_note_ids:
                    continue
                if comment_counts[note_id] >= max_comments_per_note:
                    continue
                comment_counts[note_id] += 1
                comment_rows.append(row)
        with comment_path.open("w", encoding="utf-8") as handle:
            for item in comment_rows:
                handle.write(json.dumps(item, ensure_ascii=False) + "\n")
        kept_comments = len(comment_rows)
    return len(content_rows), kept_comments


def run_crawler(
    *,
    settings: Settings,
    task_store: TaskStore,
    platform: str,
    keywords: list[str],
    limit: int,
    max_comments_per_note: int,
    enable_media_download: bool,
    task_id: str | None = None,
) -> CrawlerRunResult:
    """执行MediaCrawler并将输出收口到AIAD目录。"""
    task_id = task_id or uuid4().hex[:12]
    record = TaskRecord(
        task_id=task_id,
        created_at=datetime.now(),
        updated_at=datetime.now(),
        status=TaskStatus.RUNNING,
        params={
            "platform": platform,
            "keywords": keywords,
            "limit": limit,
            "max_comments_per_note": max_comments_per_note,
            "enable_media_download": enable_media_download,
        },
    )
    task_store.upsert(record)

    run_output_dir = settings.crawler_output_dir / "_runs" / task_id
    run_output_dir.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env["PLAYWRIGHT_BROWSERS_PATH"] = str(settings.playwright_browsers_path)
    started_at = datetime.now().timestamp()
    result: subprocess.CompletedProcess[str] | None = None
    for login_type in ("cookie", "qrcode"):
        command = [
            str(settings.mediacrawler_python_exe),
            "main.py",
            "--platform",
            platform,
            "--lt",
            login_type,
            "--type",
            "search",
            "--keywords",
            ",".join(keywords),
            "--max_notes_count",
            str(limit),
            "--max_comments_count_singlenotes",
            str(max_comments_per_note),
            "--enable_get_meidas",
            "true" if enable_media_download else "false",
            "--save_data_option",
            "jsonl",
            "--headless",
            "false",
            "--save_data_path",
            str(run_output_dir),
        ]
        logger.info(
            "开始执行爬虫 task_id=%s login_type=%s command=%s",
            task_id,
            login_type,
            " ".join(command),
        )
        try:
            result = subprocess.run(
                command,
                cwd=settings.media_crawler_dir,
                capture_output=True,
                text=True,
                encoding="utf-8",
                env=env,
            )
        except Exception as exc:
            record.status = TaskStatus.FAILED
            record.error_code = ErrorCode.CRAWLER_ERROR
            record.error_message = str(exc)[:1000]
            task_store.upsert(record)
            logger.error("爬虫进程启动失败 task_id=%s error=%s", task_id, str(exc))
            return CrawlerRunResult(
                task_id=task_id,
                status=TaskStatus.FAILED,
                output_files={},
                error_code=ErrorCode.CRAWLER_ERROR,
                error_message=str(exc)[:1000],
            )
        if result.returncode == 0:
            break
        if login_type == "cookie" and _detect_login_required(result.stdout, result.stderr):
            logger.warning("cookie登录态不可用，切换二维码登录重试 task_id=%s", task_id)
            shutil.rmtree(run_output_dir, ignore_errors=True)
            run_output_dir.mkdir(parents=True, exist_ok=True)
            continue
        break
    if result is None:
        raise RuntimeError("crawler subprocess not executed")
    source_data_dir = run_output_dir
    content_file, comment_file = _collect_latest_jsonl(source_data_dir)
    has_new_content = bool(content_file and content_file.stat().st_mtime >= started_at)
    has_new_comment = bool(comment_file and comment_file.stat().st_mtime >= started_at)
    has_recent_content = _is_recent_file(content_file)
    has_recent_comment = _is_recent_file(comment_file)
    keyword_match = _is_keyword_match(content_file, keywords)

    if (content_file or comment_file) and not keyword_match:
        error_message = (
            f"抓取结果关键词不匹配，当前请求={keywords}，"
            "请重新登录小红书后重试，避免复用旧搜索结果"
        )
        record.status = TaskStatus.FAILED
        record.error_code = ErrorCode.CRAWLER_ERROR
        record.error_message = error_message
        task_store.upsert(record)
        logger.error("关键词不匹配 task_id=%s", task_id)
        return CrawlerRunResult(
            task_id=task_id,
            status=TaskStatus.FAILED,
            output_files={},
            error_code=ErrorCode.CRAWLER_ERROR,
            error_message=error_message,
        )

    if result.returncode != 0 and not (has_new_content or has_new_comment or has_recent_content):
        error_code = ErrorCode.CRAWLER_ERROR
        if _detect_login_required(result.stdout, result.stderr):
            error_code = ErrorCode.LOGIN_REQUIRED
        error_message = _build_error_message(result.stdout, result.stderr)
        if error_code == ErrorCode.LOGIN_REQUIRED:
            error_message = (
                "检测到登录态失效或扫码超时，请在弹出的浏览器中完成小红书登录后重试。\n"
                + error_message
            )[:1500]
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
    if result.returncode != 0:
        logger.warning(
            "爬虫返回非0，启用数据回退 task_id=%s code=%s "
            "new_content=%s new_comment=%s recent_content=%s recent_comment=%s",
            task_id,
            result.returncode,
            has_new_content,
            has_new_comment,
            has_recent_content,
            has_recent_comment,
        )
    output_files: dict[str, str] = {}
    if content_file:
        target_content = settings.crawler_output_dir / f"{task_id}_search_contents.jsonl"
        shutil.copy2(content_file, target_content)
        output_files["content_file"] = str(target_content)
    if comment_file:
        target_comment = settings.crawler_output_dir / f"{task_id}_search_comments.jsonl"
        shutil.copy2(comment_file, target_comment)
        output_files["comment_file"] = str(target_comment)
    media_root_dir = run_output_dir / platform
    if enable_media_download and media_root_dir.exists():
        output_files["media_root_dir"] = str(media_root_dir)
    if "content_file" in output_files:
        trimmed_notes, trimmed_comments = _trim_jsonl_outputs(
            Path(output_files["content_file"]),
            Path(output_files["comment_file"]) if "comment_file" in output_files else None,
            max_notes=limit,
            max_comments_per_note=max_comments_per_note,
        )
        logger.info(
            "任务数据按请求裁剪 task_id=%s notes=%s comments=%s",
            task_id,
            trimmed_notes,
            trimmed_comments,
        )

    record.status = TaskStatus.RUNNING
    record.output_files = output_files
    record.error_code = None
    record.error_message = ""
    task_store.upsert(record)
    logger.info("爬虫阶段完成 task_id=%s outputs=%s", task_id, output_files)
    return CrawlerRunResult(task_id=task_id, status=TaskStatus.SUCCESS, output_files=output_files)

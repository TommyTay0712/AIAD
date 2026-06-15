from __future__ import annotations

"""
Crawler Service 微服务

职责：
- 语义缓存查询（命中则跳过爬虫）
- 非阻塞启动 MediaCrawler，后台边爬边积累评论
- 实时暴露评论轮询接口，供 task service 边爬边取
- 成功后将结果写入语义缓存
"""

import asyncio
import json
import logging
from pathlib import Path
from typing import Any

from fastapi import APIRouter, FastAPI, HTTPException
from fastapi.responses import FileResponse

from services.shared.config import load_service_config
from services.shared.schemas import CrawlRequest, HealthResponse

import sys
sys.path.append(str(Path(__file__).resolve().parents[2]))

from app.services.crawler_runner import run_crawler
from app.services.keyword_cache import KeywordCache, build_keyword_cache
from app.services.task_store import TaskStore
from app.core.config import get_settings

logger = logging.getLogger(__name__)

config = load_service_config("crawler")
app = FastAPI(title="AIAD Crawler Service", version="0.1.0")
router = APIRouter(prefix="/crawl", tags=["crawler"])

# 每个任务的状态与评论缓冲
_crawl_data: dict[str, dict[str, Any]] = {}
# {task_id: {status, comments, content_file, comment_file, error}}

# 每个任务的实时日志缓冲
_task_logs: dict[str, list[str]] = {}

# 语义缓存单例（懒加载）
_keyword_cache: KeywordCache | None = None


def _get_keyword_cache() -> KeywordCache | None:
    global _keyword_cache
    if _keyword_cache is None:
        try:
            _keyword_cache = build_keyword_cache(get_settings())
            logger.info("keyword_cache 初始化完成")
        except Exception as exc:
            logger.warning("keyword_cache 初始化失败，跳过缓存 error=%s", exc)
    return _keyword_cache


def _load_jsonl(path: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    p = Path(path)
    if not p.exists():
        return rows
    with p.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
    return rows


async def _background_crawl(request: CrawlRequest, settings: Any, task_store: Any) -> None:
    """后台爬取：监视输出 JSONL 文件，边爬边把新评论追加到缓冲。"""
    task_id = request.task_id
    run_output_dir = settings.crawler_output_dir / "_runs" / task_id

    def emit_log(event: dict[str, Any]) -> None:
        line = event.get("line", "")
        if line:
            _task_logs[task_id].append(line)

    async def _watch_comment_file() -> None:
        """每秒扫描 JSONL，把新评论追加到 _crawl_data 缓冲。"""
        comment_file: Path | None = None
        seen_lines = 0
        while True:
            await asyncio.sleep(1)
            # 发现文件
            if comment_file is None and run_output_dir.exists():
                files = sorted(
                    run_output_dir.rglob("search_comments_*.jsonl"),
                    key=lambda p: p.stat().st_mtime,
                )
                if files:
                    comment_file = files[-1]
            # 读取新行
            if comment_file and comment_file.exists():
                try:
                    text = comment_file.read_text(encoding="utf-8", errors="replace")
                    lines = text.splitlines()
                    for line in lines[seen_lines:]:
                        line = line.strip()
                        if line:
                            try:
                                _crawl_data[task_id]["comments"].append(json.loads(line))
                            except json.JSONDecodeError:
                                pass
                    seen_lines = len(lines)
                except Exception:
                    pass

    watcher = asyncio.create_task(_watch_comment_file())
    try:
        crawl_result = await asyncio.to_thread(
            run_crawler,
            task_id=task_id,
            platform=request.platform,
            keywords=request.keywords,
            limit=request.limit,
            max_comments_per_note=request.max_comments_per_note,
            enable_media_download=request.enable_media_download,
            settings=settings,
            task_store=task_store,
            emit_fn=emit_log,
        )
        # 爬完后用裁剪后的最终文件覆盖（保证数量准确）
        cf = str(crawl_result.output_files.get("comment_file", ""))
        cof = str(crawl_result.output_files.get("content_file", ""))
        _crawl_data[task_id]["comments"] = _load_jsonl(cf) if cf else []
        _crawl_data[task_id]["comment_file"] = cf
        _crawl_data[task_id]["content_file"] = cof
        _crawl_data[task_id]["status"] = "done"

        # 写语义缓存
        primary_keyword = request.keywords[0] if request.keywords else ""
        if cof and primary_keyword:
            kw_cache = await asyncio.to_thread(_get_keyword_cache)
            if kw_cache is not None:
                try:
                    await asyncio.to_thread(
                        kw_cache.store,
                        task_id=task_id,
                        keyword=primary_keyword,
                        platform=request.platform,
                        content_file=cof,
                        comment_file=cf,
                        result_count=len(_crawl_data[task_id]["comments"]),
                    )
                except Exception as exc:
                    logger.warning("缓存写入失败（非致命）error=%s", exc)

    except Exception as exc:
        logger.error("后台爬取失败 task_id=%s error=%s", task_id, exc)
        _crawl_data[task_id]["status"] = "error"
        _crawl_data[task_id]["error"] = str(exc)[:500]
    finally:
        watcher.cancel()
        try:
            await watcher
        except asyncio.CancelledError:
            pass

        async def _cleanup() -> None:
            await asyncio.sleep(300)
            _crawl_data.pop(task_id, None)
            _task_logs.pop(task_id, None)

        asyncio.create_task(_cleanup())


@app.get("/health", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    return HealthResponse(service="crawler")


@router.post("")
async def crawl(request: CrawlRequest) -> dict[str, Any]:
    """启动爬取任务（立即返回），实际爬取在后台进行。"""
    logger.info("收到采集任务 task_id=%s platform=%s keywords=%s",
                request.task_id, request.platform, request.keywords)

    settings = get_settings()
    primary_keyword = request.keywords[0] if request.keywords else ""

    # === 语义缓存查询 ===
    if primary_keyword:
        kw_cache = await asyncio.to_thread(_get_keyword_cache)
        if kw_cache is not None:
            try:
                cache_hit = await asyncio.to_thread(
                    kw_cache.lookup,
                    primary_keyword,
                    request.platform,
                    float("inf"),  # 不限时间，命中即复用
                )
                if cache_hit is not None:
                    logger.info("命中语义缓存，跳过爬虫 task_id=%s keyword=%s",
                                request.task_id, cache_hit.keyword)
                    comments = _load_jsonl(cache_hit.comment_file) if cache_hit.comment_file else []
                    _crawl_data[request.task_id] = {
                        "status": "done",
                        "comments": comments,
                        "content_file": cache_hit.content_file,
                        "comment_file": cache_hit.comment_file or "",
                        "error": "",
                    }
                    _task_logs[request.task_id] = []
                    return {"task_id": request.task_id, "status": "done",
                            "total": len(comments), "cache_hit": True}
            except Exception as exc:
                logger.warning("缓存查询异常，继续正常爬取 error=%s", exc)

    # === 启动后台爬取 ===
    _crawl_data[request.task_id] = {
        "status": "running",
        "comments": [],
        "content_file": "",
        "comment_file": "",
        "error": "",
    }
    _task_logs[request.task_id] = []

    task_store = TaskStore(settings.task_store_file)
    asyncio.create_task(_background_crawl(request, settings, task_store))

    return {"task_id": request.task_id, "status": "running", "total": 0, "cache_hit": False}


@router.get("/{task_id}/poll")
async def poll_crawl(task_id: str, offset: int = 0) -> dict[str, Any]:
    """轮询爬取进度和评论数据（task service 每 5s 调用一次）。"""
    data = _crawl_data.get(task_id)
    if data is None:
        return {"status": "unknown", "comments": [], "total": 0,
                "content_file": "", "comment_file": "", "error": "task not found"}
    all_comments = data.get("comments", [])
    return {
        "status": data.get("status", "running"),
        "comments": all_comments[offset:],
        "total": len(all_comments),
        "content_file": data.get("content_file", ""),
        "comment_file": data.get("comment_file", ""),
        "error": data.get("error", ""),
    }


@router.get("/{task_id}/logs")
async def get_crawl_logs(task_id: str, offset: int = 0) -> dict[str, Any]:
    """返回爬虫日志行（task service 轮询用）。"""
    lines = _task_logs.get(task_id, [])
    return {"lines": lines[offset:], "total": len(lines)}


@app.get("/qrcode/{task_id}")
async def get_qrcode(task_id: str) -> FileResponse:
    settings = get_settings()
    qrcode_path = settings.crawler_output_dir / f"{task_id}_qrcode.png"
    if not qrcode_path.exists():
        raise HTTPException(status_code=404, detail="QR code not yet generated")
    return FileResponse(str(qrcode_path), media_type="image/png")


app.include_router(router)

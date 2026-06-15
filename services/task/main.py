from __future__ import annotations

"""
Task Service 微服务

职责：
- 任务生命周期管理（创建、查询、更新）
- SSE 实时事件推送
- 工作流编排（调度 Crawler → Analysis → Copywriter）
"""

import asyncio
import json
import logging
import math
import os
import queue as stdlib_queue
import time
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

import httpx
from fastapi import APIRouter, BackgroundTasks, FastAPI, Request
from fastapi.responses import StreamingResponse

from services.shared.config import load_service_config
from services.shared.schemas import HealthResponse

# 任务持久化（复用 app/ 中已有的 TaskStore + TaskRecord）
try:
    from app.services.task_store import TaskStore as _TaskStore
    from app.models.schemas import TaskRecord as _TaskRecord
    from app.models.schemas import TaskStatus as _TaskStatus
    _TASK_DB_PATH = Path(
        os.getenv("TASK_STORE_FILE") or
        str(Path(__file__).resolve().parents[2] / "data" / "tasks.db")
    )
    _DB_OK = True
except ImportError:
    _DB_OK = False

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(name)s %(levelname)s %(message)s",
)
logger = logging.getLogger(__name__)

config = load_service_config("task")
app = FastAPI(title="AIAD Task Service", version="0.1.0")
router = APIRouter(prefix="/api/ad-intel", tags=["ad-intel"])

# 内存事件队列（生产环境应替换为 Redis Streams）
_event_queues: dict[str, stdlib_queue.Queue] = {}
_event_queue_created: dict[str, float] = {}
# 任务最终结果缓存
_task_results: dict[str, dict[str, Any]] = {}
# 任务中间状态（评论 + 已完成的广告文案 + NLP结果），供断线重连后恢复 reviewQueue 及实时看板
_task_partial: dict[str, dict[str, Any]] = {}


def _affinity_score(comment: dict[str, Any]) -> int:
    """根据评论内容和点赞数综合计算匹配度 (70–95)。
    点赞为主信号；内容长度和意图标记为副信号，解决 liked_count 全为0时分布扁平的问题。
    """
    if not isinstance(comment, dict):
        return 72
    content = str(comment.get("content", ""))
    likes = int(comment.get("liked_count", 0) or comment.get("likes", 0))
    # 点赞主信号（0点赞=0分，避免虚增基础分）
    like_score = min(18, int(math.log10(likes + 1) * 10)) if likes > 0 else 0
    # 内容长度副信号（区分零点赞评论）
    n = len(content.strip())
    len_score = 8 if n >= 80 else 5 if n >= 40 else 2 if n >= 15 else 0
    # 互动意图标记（问句/感叹句）
    intent_score = 2 if any(c in content for c in ["?", "？", "!", "！"]) else 0
    return min(95, 70 + like_score + len_score + intent_score)


@app.get("/health", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    return HealthResponse(service="task")


@app.on_event("startup")
async def _restore_tasks_from_db() -> None:
    """容器启动时从 SQLite 恢复已完成任务，使容器重启后历史结果不丢失。"""
    if not _DB_OK:
        return
    try:
        store = _TaskStore(_TASK_DB_PATH)
        restored = 0
        for record in store.list_recent(50):
            if record.status == _TaskStatus.SUCCESS and record.result:
                _task_results[record.task_id] = record.result
                restored += 1
        logger.info("从 SQLite 恢复了 %d 个已完成任务", restored)
    except Exception as exc:
        logger.warning("恢复历史任务失败（不影响服务启动）: %s", exc)


async def _stream_crawler_logs(task_id: str, emit: Any) -> None:
    """持续轮询爬虫日志并推送到 SSE。"""
    offset = 0
    while True:
        await asyncio.sleep(2)
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                resp = await client.get(
                    f"{config.crawler_service_url}/crawl/{task_id}/logs",
                    params={"offset": offset},
                )
                if resp.status_code == 200:
                    lines = resp.json().get("lines", [])
                    for line in lines:
                        emit({"type": "crawler_log", "line": line})
                    offset += len(lines)
        except Exception:
            pass


async def _run_pipeline_async(task_id: str, payload: dict[str, Any]) -> None:
    """
    完整管道（async）：
    1. 非阻塞启动爬虫
    2. 边轮询边推进度；攒够 ANALYSIS_BATCH 条就立即做 NLP + 风格文案 + 第一批回复
    3. 爬完后处理剩余评论的逐批回复
    """
    ANALYSIS_BATCH = 20  # 攒够多少条触发早期分析
    REPLY_BATCH = 15     # 每批回复数量

    event_q = _event_queues.get(task_id)

    def emit(event: dict[str, Any]) -> None:
        if event_q is not None:
            try:
                event_q.put_nowait(event)
            except stdlib_queue.Full:
                pass

    emit({"type": "progress", "stage": "init", "percent": 5, "message": "任务初始化中..."})

    # — 启动爬虫 —
    start_result = await _call_service(
        f"{config.crawler_service_url}/crawl",
        {
            "task_id": task_id,
            "platform": payload.get("platform", "xhs"),
            "keywords": payload.get("keywords", []),
            "limit": payload.get("limit", 20),
            "max_comments_per_note": payload.get("max_comments_per_note", 10),
            "enable_media_download": payload.get("enable_media_download", False),
        },
        timeout=90,  # 宽裕超时：crawler 冷启动时 embedding 模型加载需时
    )
    if start_result.get("status") == "error":
        emit({"type": "error", "message": f"启动爬虫失败: {start_result.get('message', '')}"})
        return

    immediate = start_result.get("status") == "done"
    log_task = asyncio.create_task(_stream_crawler_logs(task_id, emit))

    comment_offset = 0
    all_comments: list[dict[str, Any]] = []
    raw_comment_ads: dict[str, str] = {}
    analysis_result: dict[str, Any] = {}
    copy_result: dict[str, Any] = {}
    analysis_started = False
    early_batch_done_offset = 0  # 已完成 batch_reply 的评论偏移量（早期批次）
    # 实时快照：用引用跟踪，后续追加/更新自动反映
    _task_partial[task_id] = {"comments": all_comments, "comment_ads": raw_comment_ads}

    try:
        # — 轮询评论，边爬边分析 —
        while True:
            if not immediate:
                await asyncio.sleep(5)
            immediate = False

            try:
                async with httpx.AsyncClient(timeout=10) as client:
                    resp = await client.get(
                        f"{config.crawler_service_url}/crawl/{task_id}/poll",
                        params={"offset": comment_offset},
                    )
                if resp.status_code != 200:
                    continue
                data = resp.json()
            except Exception:
                continue

            new_comments = data.get("comments", [])
            status = data.get("status", "running")

            if new_comments:
                for nc in new_comments:
                    idx = len(all_comments)
                    all_comments.append(nc)
                    if isinstance(nc, dict) and nc.get("content", "").strip():
                        user_info = nc.get("user_info", {})
                        author = (
                            user_info.get("nickname", "") if isinstance(user_info, dict) else ""
                        ) or nc.get("user", "匿名")
                        likes_val = int(nc.get("liked_count", 0) or nc.get("likes", 0))
                        emit({
                            "type": "comment",
                            "data": {
                                "comment_id": f"{task_id}_{idx}",
                                "source_text": nc.get("content", ""),
                                "author": author,
                                "likes": likes_val,
                                "note_id": str(nc.get("note_id", "")),
                                "ad_text": "",
                                "focus": "",
                                "predicted_affinity": _affinity_score(nc),
                                "platform": "小红书",
                            },
                        })
                comment_offset = len(all_comments)
                emit({"type": "progress", "stage": "crawling", "percent": 15,
                      "message": f"已采集 {comment_offset} 条评论，持续抓取中..."})

            # 攒够 ANALYSIS_BATCH 条就先跑：NLP 分析、风格文案、第一批回复（只触发一次）
            if not analysis_started and len(all_comments) >= ANALYSIS_BATCH:
                analysis_started = True
                emit({"type": "progress", "stage": "analyzing", "percent": 35,
                      "message": f"已采集 {len(all_comments)} 条，开始 AI 分析..."})
                analysis_result = await _call_service(
                    f"{config.analysis_service_url}/analyze",
                    {
                        "task_id": task_id,
                        "media_paths": [],
                        "comments": all_comments[:ANALYSIS_BATCH],
                        "product_info": payload.get("product_info", ""),
                    },
                    timeout=600,
                )
                # NLP 结果存入 partial，供 insights 端点在运行中也能返回分析数据
                _task_partial[task_id]["nlp_analysis"] = analysis_result.get("nlp_analysis", {})

                # 风格文案提前生成（后台爬虫仍在继续）
                emit({"type": "progress", "stage": "copywriting", "percent": 60,
                      "message": "品牌风格文案生成中（后台持续采集）..."})
                copy_result = await _call_service(
                    f"{config.copywriter_service_url}/generate",
                    {
                        "task_id": task_id,
                        "request_info": payload,
                        "vision_analysis": analysis_result.get("vision_analysis", {}),
                        "nlp_analysis": analysis_result.get("nlp_analysis", {}),
                        "rag_references": analysis_result.get("rag_references", []),
                    },
                    timeout=300,
                )

                # 第一批 batch_reply（针对已有的 ANALYSIS_BATCH 条，不等爬虫完成）
                nlp_data = analysis_result.get("nlp_analysis", {})
                first_batch_comments = list(all_comments[:ANALYSIS_BATCH])
                n_first = max(1, (len(first_batch_comments) + REPLY_BATCH - 1) // REPLY_BATCH)
                for bidx in range(n_first):
                    if bidx > 0:
                        await asyncio.sleep(2)
                    b_start = bidx * REPLY_BATCH
                    batch = first_batch_comments[b_start:b_start + REPLY_BATCH]
                    emit({"type": "progress", "stage": "copywriting",
                          "percent": 65 + int((bidx + 1) / n_first * 10),
                          "message": f"早批回复生成中（{bidx + 1}/{n_first}，后台继续采集）..."})
                    batch_result = await _call_service(
                        f"{config.copywriter_service_url}/generate/batch_reply",
                        {
                            "task_id": task_id,
                            "comments": batch,
                            "nlp_analysis": nlp_data,
                            "request_info": payload,
                            "offset": b_start,
                        },
                        timeout=300,
                    )
                    ads = batch_result.get("comment_ads", {})
                    if ads:
                        raw_comment_ads.update(ads)
                        keyed = {f"{task_id}_{k}": v for k, v in ads.items() if v}
                        if keyed:
                            emit({"type": "comment_ads_partial", "comment_ads": keyed})
                early_batch_done_offset = len(first_batch_comments)

            if status in ("done", "error"):
                if status == "error":
                    emit({"type": "error", "message": data.get("error", "爬取失败")})
                    return
                break

        # — 爬完，补做 NLP + 风格文案（仅在评论太少、早期分析未触发时）—
        if not analysis_started:
            emit({"type": "progress", "stage": "analyzing", "percent": 50, "message": "AI 分析中..."})
            analysis_result = await _call_service(
                f"{config.analysis_service_url}/analyze",
                {
                    "task_id": task_id,
                    "media_paths": [],
                    "comments": all_comments,
                    "product_info": payload.get("product_info", ""),
                },
                timeout=600,
            )
            _task_partial[task_id]["nlp_analysis"] = analysis_result.get("nlp_analysis", {})

            emit({"type": "progress", "stage": "copywriting", "percent": 78, "message": "品牌风格文案生成中..."})
            copy_result = await _call_service(
                f"{config.copywriter_service_url}/generate",
                {
                    "task_id": task_id,
                    "request_info": payload,
                    "vision_analysis": analysis_result.get("vision_analysis", {}),
                    "nlp_analysis": analysis_result.get("nlp_analysis", {}),
                    "rag_references": analysis_result.get("rag_references", []),
                },
                timeout=300,
            )

        # — 逐评论回复（处理早批之后的剩余评论）—
        remaining_comments = all_comments[early_batch_done_offset:]
        nlp_data = analysis_result.get("nlp_analysis", {})
        n_remaining = max(1, (len(remaining_comments) + REPLY_BATCH - 1) // REPLY_BATCH) if remaining_comments else 0

        for batch_idx in range(n_remaining):
            if batch_idx > 0:
                await asyncio.sleep(2)  # 批次间隔，降低限流概率
            abs_start = early_batch_done_offset + batch_idx * REPLY_BATCH
            batch = all_comments[abs_start:abs_start + REPLY_BATCH]
            pct = 80 + int((batch_idx + 1) / max(1, n_remaining) * 18)
            emit({
                "type": "progress", "stage": "copywriting", "percent": pct,
                "message": f"逐评论回复生成中（{batch_idx + 1}/{n_remaining} 批，剩余 {len(remaining_comments)} 条）...",
            })
            batch_result = await _call_service(
                f"{config.copywriter_service_url}/generate/batch_reply",
                {
                    "task_id": task_id,
                    "comments": batch,
                    "nlp_analysis": nlp_data,
                    "request_info": payload,
                    "offset": abs_start,
                },
                timeout=300,
            )
            ads = batch_result.get("comment_ads", {})
            if ads:
                raw_comment_ads.update(ads)
                keyed = {f"{task_id}_{k}": v for k, v in ads.items() if v}
                if keyed:
                    emit({"type": "comment_ads_partial", "comment_ads": keyed})
            elif batch_result.get("status") == "error":
                logger.warning("批次 %d/%d 回复生成失败，跳过继续：%s",
                               batch_idx + 1, n_remaining, batch_result.get("message", ""))

        _task_partial.pop(task_id, None)  # 任务完成，最终结果存入 _task_results
        _task_results[task_id] = {
            "task_id": task_id,
            "status": "done",
            "final_ads": copy_result.get("final_ads", []),
            "comment_ads": raw_comment_ads,
            "vision_analysis": analysis_result.get("vision_analysis", {}),
            "nlp_analysis": analysis_result.get("nlp_analysis", {}),
            "rag_references": analysis_result.get("rag_references", []),
            "comments": all_comments,
        }
        # 持久化最终结果到 SQLite
        if _DB_OK:
            try:
                _TaskStore(_TASK_DB_PATH).upsert(_TaskRecord(
                    task_id=task_id,
                    status=_TaskStatus.SUCCESS,
                    params=payload,
                    result=_task_results[task_id],
                    created_at=datetime.now(),
                    updated_at=datetime.now(),
                ))
                logger.info("任务结果已持久化 task_id=%s", task_id)
            except Exception as db_exc:
                logger.warning("持久化任务结果失败（不影响结果可用性）: %s", db_exc)

        emit({"type": "done", "task_id": task_id})
        logger.info("任务管道完成 task_id=%s comments=%s", task_id, len(all_comments))

    except Exception as exc:
        logger.error("任务管道异常 task_id=%s error=%s", task_id, exc)
        if _DB_OK:
            try:
                _TaskStore(_TASK_DB_PATH).upsert(_TaskRecord(
                    task_id=task_id,
                    status=_TaskStatus.FAILED,
                    params=payload,
                    result={},
                    error_message=str(exc)[:500],
                    created_at=datetime.now(),
                    updated_at=datetime.now(),
                ))
            except Exception:
                pass
        emit({"type": "error", "message": "任务执行异常，请稍后重试"})
    finally:
        log_task.cancel()
        try:
            await log_task
        except asyncio.CancelledError:
            pass


async def _call_service(url: str, payload: dict[str, Any], timeout: float = 300) -> dict[str, Any]:
    """调用下游微服务。"""
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(url, json=payload)
            resp.raise_for_status()
            return resp.json()
    except Exception as exc:
        logger.error("调用下游服务失败 url=%s error=%s", url, exc)
        return {"status": "error", "message": str(exc)[:200]}



@router.post("/run")
def run_analysis(
    payload: dict[str, Any],
    background_tasks: BackgroundTasks,
) -> dict[str, Any]:
    """创建并启动分析任务。"""
    task_id = uuid4().hex
    now = time.time()

    # 清理过期队列
    stale_ids = [tid for tid, ts in _event_queue_created.items() if now - ts > 1800]
    for stale_id in stale_ids:
        _event_queues.pop(stale_id, None)
        _event_queue_created.pop(stale_id, None)
        _task_partial.pop(stale_id, None)

    event_q = stdlib_queue.Queue(maxsize=2000)
    _event_queues[task_id] = event_q
    _event_queue_created[task_id] = now

    background_tasks.add_task(_run_pipeline_async, task_id, payload)

    # 持久化 running 记录（任务启动时写入，后续由 pipeline 更新为 success/failed）
    if _DB_OK:
        try:
            _TaskStore(_TASK_DB_PATH).upsert(_TaskRecord(
                task_id=task_id,
                status=_TaskStatus.RUNNING,
                params=payload,
                result={},
                created_at=datetime.now(),
                updated_at=datetime.now(),
            ))
        except Exception as exc:
            logger.warning("写入 running 任务记录失败: %s", exc)

    return {"task_id": task_id, "status": "running", "message": "任务已提交"}


@router.get("/task/{task_id}/meta")
def get_task_meta(task_id: str) -> dict[str, Any]:
    """返回任务最终结果（pipeline 完成后可用）。"""
    return _task_results.get(task_id, {"task_id": task_id, "status": "pending"})


@router.get("/tasks")
def list_tasks() -> list[dict[str, Any]]:
    """返回最近 30 条任务列表（历史记录），从 SQLite 读取，容器重启后仍可用。"""
    if not _DB_OK:
        # 降级：仅返回当前内存中的任务（无统计，无 params）
        return [
            {"task_id": tid, "status": "success", "created_at": "", "params": {}, "stats": {}}
            for tid in list(_task_results)[-30:]
        ]
    try:
        records = _TaskStore(_TASK_DB_PATH).list_recent(30)
        result: list[dict[str, Any]] = []
        for r in records:
            res = r.result or {}
            result.append({
                "task_id": r.task_id,
                "status": r.status.value,
                "created_at": r.created_at.isoformat(),
                "params": r.params,
                "stats": {
                    "comment_count": len(res.get("comments", [])),
                    "final_ads_count": len(res.get("final_ads", [])),
                },
            })
        return result
    except Exception as exc:
        logger.warning("获取任务列表失败: %s", exc)
        return []


@router.get("/task/{task_id}/insights")
def get_task_insights(task_id: str) -> dict[str, Any]:
    """返回任务洞察数据，供前端 review 页渲染。运行中时从 partial 快照返回实时数据。"""
    result = _task_results.get(task_id, {})
    if not result:
        # 检查是否有运行中的中间快照
        partial = _task_partial.get(task_id)
        if partial:
            comments: list[dict[str, Any]] = list(partial.get("comments", []))
            comment_ads: dict[str, str] = dict(partial.get("comment_ads", {}))
            nlp: dict[str, Any] = partial.get("nlp_analysis", {})
            focus = nlp.get("keyword_summary", [""])[0] if nlp.get("keyword_summary") else ""
            partial_queue: list[dict[str, Any]] = []
            for i, c in enumerate(comments):
                if isinstance(c, dict):
                    user_info = c.get("user_info", {})
                    author = (
                        user_info.get("nickname", "") if isinstance(user_info, dict) else ""
                    ) or c.get("user", "匿名")
                    source_text = c.get("content", "")
                    likes = int(c.get("liked_count", 0) or c.get("likes", 0))
                    note_id = str(c.get("note_id", ""))
                else:
                    author, source_text, likes, note_id = "匿名", str(c), 0, ""
                if not source_text:
                    continue
                partial_queue.append({
                    "comment_id": f"{task_id}_{i}",
                    "source_text": source_text,
                    "ad_text": comment_ads.get(str(i), ""),
                    "author": author,
                    "likes": likes,
                    "note_id": note_id,
                    "focus": focus,
                    "predicted_affinity": _affinity_score(c if isinstance(c, dict) else {}),
                    "platform": "小红书",
                })
            note_ids = {
                str(c.get("note_id", ""))
                for c in comments
                if isinstance(c, dict) and c.get("note_id")
            }
            done_ads = sum(1 for v in comment_ads.values() if v)
            dispatch_eff = int(done_ads / max(1, len(partial_queue)) * 100) if partial_queue else 0
            emotion = nlp.get("main_emotion", "")
            if any(w in emotion for w in ["积极", "正面", "好评", "热情", "种草"]):
                pos_val, neg_val, neu_val = 72, 12, 16
            elif any(w in emotion for w in ["消极", "负面", "差评", "抱怨", "失望"]):
                pos_val, neg_val, neu_val = 18, 64, 18
            else:
                pos_val, neg_val, neu_val = 48, 18, 34
            return {
                "review_queue": partial_queue,
                "comment_ads_status": "processing",
                "comment_ads_progress": {"done": done_ads, "total": len(partial_queue)},
                "progress": {
                    "step": {"current": 2, "total": 4, "label": "分析与生成中", "percent": 60},
                    "metrics": {"posts_scanned": len(note_ids), "comments_read": len(comments)},
                    "logs": [],
                },
                "analytics": {
                    "kpis": {
                        "comment_count": len(comments),
                        "content_count": len(note_ids),
                        "dispatch_efficiency": dispatch_eff,
                        "completed_tasks": 0,
                    },
                    "sentiment_bars": [
                        {"label": "积极情感", "value": pos_val, "colorClass": "bg-green-500"},
                        {"label": "中性情感", "value": neu_val, "colorClass": "bg-slate-400"},
                        {"label": "消极情感", "value": neg_val, "colorClass": "bg-red-400"},
                    ] if emotion else [],
                    "topic_cloud": nlp.get("keyword_summary", []),
                    "insight": emotion or "",
                },
            }
        # 任务尚未完成且无中间快照时返回空状态
        return {
            "review_queue": [],
            "comment_ads_status": "pending",
            "comment_ads_progress": {"done": 0, "total": 0},
            "progress": {
                "step": {"current": 1, "total": 4, "label": "任务等待中", "percent": 0},
                "metrics": {"posts_scanned": 0, "comments_read": 0},
                "logs": [],
            },
            "analytics": {
                "kpis": {"comment_count": 0, "content_count": 0, "dispatch_efficiency": 0, "completed_tasks": 0},
                "sentiment_bars": [],
                "topic_cloud": [],
                "insight": "",
            },
        }

    nlp = result.get("nlp_analysis", {})
    comment_ads: dict[str, str] = result.get("comment_ads", {})
    comments = result.get("comments", [])
    focus = nlp.get("keyword_summary", [""])[0] if nlp.get("keyword_summary") else ""

    review_queue: list[dict[str, Any]] = []
    for i, c in enumerate(comments):
        if isinstance(c, dict):
            user_info = c.get("user_info", {})
            author = (
                user_info.get("nickname", "") if isinstance(user_info, dict) else ""
            ) or c.get("user", "匿名")
            source_text = c.get("content", "")
            likes = int(c.get("liked_count", 0) or c.get("likes", 0))
            note_id = str(c.get("note_id", ""))
        else:
            author, source_text, likes, note_id = "匿名", str(c), 0, ""

        if not source_text:
            continue

        ad_text = comment_ads.get(str(i), "")

        review_queue.append({
            "comment_id": f"{task_id}_{i}",
            "source_text": source_text,
            "ad_text": ad_text,
            "author": author,
            "likes": likes,
            "note_id": note_id,
            "focus": focus,
            "predicted_affinity": _affinity_score(c if isinstance(c, dict) else {}),
            "platform": "小红书",
        })

    # 统计 note_id 去重数（帖子数）
    note_ids = {
        str(c.get("note_id", ""))
        for c in comments
        if isinstance(c, dict) and c.get("note_id")
    }

    # 情感指数：根据 main_emotion 关键词简单派生
    emotion = nlp.get("main_emotion", "")
    if any(w in emotion for w in ["积极", "正面", "好评", "热情", "种草"]):
        pos_val, neg_val, neu_val = 72, 12, 16
    elif any(w in emotion for w in ["消极", "负面", "差评", "抱怨", "失望"]):
        pos_val, neg_val, neu_val = 18, 64, 18
    else:
        pos_val, neg_val, neu_val = 48, 18, 34

    # 真实派发效率：已生成文案的评论占比
    done_ads = sum(1 for v in comment_ads.values() if v)
    dispatch_eff = int(done_ads / max(1, len(review_queue)) * 100) if review_queue else 85

    return {
        "review_queue": review_queue,
        "comment_ads_status": "complete",
        "comment_ads_progress": {"done": len(review_queue), "total": len(review_queue)},
        "progress": {
            "step": {"current": 4, "total": 4, "label": "分析完成", "percent": 100},
            "metrics": {"posts_scanned": len(note_ids), "comments_read": len(comments)},
            "logs": [],
        },
        "analytics": {
            "kpis": {
                "comment_count": len(comments),
                "content_count": len(note_ids),
                "dispatch_efficiency": dispatch_eff,
                "completed_tasks": 1 if result else 0,
            },
            "sentiment_bars": [
                {"label": "积极情感", "value": pos_val, "colorClass": "bg-green-500"},
                {"label": "中性情感", "value": neu_val, "colorClass": "bg-slate-400"},
                {"label": "消极情感", "value": neg_val, "colorClass": "bg-red-400"},
            ],
            "topic_cloud": nlp.get("keyword_summary", []),
            "insight": emotion,
        },
    }



@router.get("/task/{task_id}/status")
def get_task_status_api(task_id: str) -> dict[str, str]:
    """返回任务状态：done / running / not_found。"""
    if task_id in _task_results:
        return {"status": "done"}
    if task_id in _event_queues:
        return {"status": "running"}
    return {"status": "not_found"}


@router.get("/task/{task_id}/partial")
def get_task_partial(task_id: str) -> dict[str, Any]:
    """返回任务运行中的中间快照（评论列表 + 已完成的广告文案），供断线重连后恢复 reviewQueue。"""
    if task_id in _task_results:
        result = _task_results[task_id]
        return {"comments": result.get("comments", []), "comment_ads": result.get("comment_ads", {})}
    partial = _task_partial.get(task_id)
    if partial:
        return {"comments": list(partial["comments"]), "comment_ads": dict(partial.get("comment_ads", {}))}
    return {"comments": [], "comment_ads": {}}


@router.get("/task/{task_id}/stream")
async def stream_task_events(task_id: str, request: Request) -> StreamingResponse:
    """SSE 端点：实时推送任务进度。支持断线重连（断连时不删 queue）。"""
    event_q = _event_queues.get(task_id)

    async def generator():
        if event_q is None:
            yield f"data: {json.dumps({'type': 'error', 'message': '任务不存在'}, ensure_ascii=False)}\n\n"
            return

        completed = False
        last_heartbeat = time.time()
        try:
            while True:
                if await request.is_disconnected():
                    logger.info("SSE 客户端断开 task_id=%s，queue 保留等待重连", task_id)
                    break
                try:
                    event = event_q.get_nowait()
                    yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
                    if event.get("type") in ("done", "error"):
                        completed = True
                        break
                except stdlib_queue.Empty:
                    # 每 30s 发一次心跳注释行，防止中间层因静默超时断连
                    now = time.time()
                    if now - last_heartbeat >= 30:
                        yield ": heartbeat\n\n"
                        last_heartbeat = now
                    await asyncio.sleep(0.1)
        finally:
            # 只有任务正常结束时才清理 queue；断连时保留，供客户端重连消费
            if completed:
                _event_queues.pop(task_id, None)
                _event_queue_created.pop(task_id, None)

    return StreamingResponse(
        generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no", "Connection": "keep-alive"},
    )


app.include_router(router)

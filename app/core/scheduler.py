from __future__ import annotations

import logging
import queue as stdlib_queue
import threading
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.core.config import Settings, get_settings
from app.services.keyword_cache import KeywordCache, build_keyword_cache

logger = logging.getLogger(__name__)


def _run_trend_crawl(settings: Settings, keyword_cache: KeywordCache) -> None:
    """
    APScheduler job 函数（同步）。
    接收全局共享的 keyword_cache 单例，避免重建 Chroma 客户端。
    """
    try:
        from app.services.trend_agent import TrendAgent
        agent = TrendAgent(settings, keyword_cache=keyword_cache)
        cached = agent.crawl_trends()
        logger.info("定时趋势预热完成 cached_keywords=%s", cached)
    except Exception as exc:
        logger.error("定时趋势预热异常 error=%s", exc, exc_info=True)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """
    FastAPI lifespan 上下文管理器。
    负责：
    1. 初始化全局 KeywordCache 单例（唯一 Chroma 客户端 + 唯一 embedding 模型）
    2. 初始化 in-flight 关键词去重结构（防止并发重复爬取）
    3. 启动 APScheduler 定时趋势预热
    """
    from apscheduler.schedulers.asyncio import AsyncIOScheduler
    from apscheduler.triggers.interval import IntervalTrigger

    settings = get_settings()

    # 全局 KeywordCache 单例：整个进程内只有一个 Chroma 客户端和一个 embedding 模型实例
    keyword_cache = build_keyword_cache(settings)
    app.state.keyword_cache = keyword_cache

    # in-flight 去重：记录正在爬取的关键词，后来者等待而非重复爬取
    app.state.inflight_keywords = {}  # dict[str, threading.Event]
    app.state.inflight_lock = threading.Lock()

    # SSE 事件队列：每个 task_id 对应一个 Queue，后台线程写入，SSE 端点消费
    app.state.task_event_queues = {}  # dict[str, stdlib_queue.Queue]

    scheduler = AsyncIOScheduler()
    scheduler.add_job(
        _run_trend_crawl,
        trigger=IntervalTrigger(hours=settings.trend_crawl_interval_hours),
        args=[settings, keyword_cache],
        id="trend_crawl",
        replace_existing=True,
        misfire_grace_time=300,
    )
    scheduler.start()
    logger.info(
        "APScheduler 已启动 interval_hours=%s trend_keywords_file=%s",
        settings.trend_crawl_interval_hours,
        settings.trend_keywords_file,
    )

    try:
        yield
    finally:
        scheduler.shutdown(wait=False)
        logger.info("APScheduler 已停止")

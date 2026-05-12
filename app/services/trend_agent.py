from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any
from uuid import uuid4

from app.core.config import Settings
from app.services.crawler_runner import run_crawler
from app.services.keyword_cache import CacheHit, KeywordCache, build_keyword_cache
from app.services.task_store import TaskStore

logger = logging.getLogger(__name__)


class TrendAgent:
    """
    定时主动抓取热门话题，将结果写入关键词语义缓存。

    只执行 爬取 + 写缓存，不触发完整的 LangGraph pipeline，
    避免无效 LLM 调用（用户命中缓存后自行跑 agents）。
    """

    def __init__(self, settings: Settings, keyword_cache: KeywordCache | None = None) -> None:
        self._settings = settings
        # 优先使用传入的全局共享缓存单例，避免重建 Chroma 客户端和 embedding 模型
        self._cache: KeywordCache | None = keyword_cache

    def _get_cache(self) -> KeywordCache:
        if self._cache is None:
            self._cache = build_keyword_cache(self._settings)
        return self._cache

    def _load_trend_config(self) -> dict[str, Any]:
        """读取 trend_keywords.json，返回 {keywords, platform}。文件缺失时返回空配置。"""
        path: Path = self._settings.trend_keywords_file
        try:
            if path.exists():
                data: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
                return data
            logger.warning("trend_keywords.json 不存在 path=%s", path)
        except Exception as exc:
            logger.warning("读取 trend_keywords.json 失败 error=%s", exc)
        return {"keywords": [], "platform": "xhs"}

    def crawl_trends(self, keywords: list[str] | None = None) -> list[str]:
        """
        对关键词列表逐一爬取并写入缓存。
        keywords 为 None 时从 trend_keywords.json 读取。
        返回成功写入缓存的关键词列表。
        """
        config = self._load_trend_config()
        raw_kws = config.get("keywords", [])
        kw_list: list[str] = keywords if keywords is not None else [str(k) for k in raw_kws if isinstance(raw_kws, list)]
        platform: str = str(config.get("platform", "xhs"))

        if not kw_list:
            logger.info("trend_agent: 无待爬关键词，跳过本轮")
            return []

        logger.info("trend_agent: 开始本轮预热 keywords=%s platform=%s", kw_list, platform)
        cached: list[str] = []
        for kw in kw_list:
            if self._crawl_single(kw, platform):
                cached.append(kw)
        logger.info("trend_agent: 本轮预热完成 cached=%s", cached)
        return cached

    def _crawl_single(self, keyword: str, platform: str) -> bool:
        """
        爬取单个关键词并存入缓存。
        若已有未过期缓存则跳过；爬取失败时记录错误并返回 False。
        """
        try:
            cache = self._get_cache()
            hit: CacheHit | None = cache.lookup(
                keyword,
                platform,
                ttl_hours=self._settings.keyword_cache_ttl_hours,
            )
            if hit is not None:
                logger.info(
                    "trend_agent: 缓存命中，跳过爬取 keyword=%s distance=%.4f",
                    keyword, hit.distance,
                )
                return False

            task_id = f"trend_{uuid4().hex[:8]}"
            task_store = TaskStore(self._settings.task_store_file)

            crawler = run_crawler(
                settings=self._settings,
                task_store=task_store,
                platform=platform,
                keywords=[keyword],
                limit=20,
                max_comments_per_note=5,
                enable_media_download=False,
                task_id=task_id,
            )

            if not crawler.output_files.get("content_file"):
                logger.warning("trend_agent: 爬取无输出 keyword=%s", keyword)
                return False

            content_file = crawler.output_files["content_file"]
            comment_file = crawler.output_files.get("comment_file", "")

            # 统计内容行数
            result_count = 0
            try:
                result_count = sum(
                    1 for line in Path(content_file).read_text(encoding="utf-8").splitlines()
                    if line.strip()
                )
            except Exception:
                pass

            cache.store(
                task_id=task_id,
                keyword=keyword,
                platform=platform,
                content_file=content_file,
                comment_file=comment_file,
                result_count=result_count,
            )
            logger.info(
                "trend_agent: 关键词预热完成 keyword=%s result_count=%s", keyword, result_count
            )
            return True

        except Exception as exc:
            logger.error(
                "trend_agent: 爬取异常 keyword=%s error=%s", keyword, exc, exc_info=True
            )
            return False

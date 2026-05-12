from __future__ import annotations

import logging
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from app.services.memory.config import get_agent4_settings
from app.services.memory.embedder import Embedder, build_embedder
from app.services.memory.memory_store import MemoryStore
from app.services.memory.schemas import MemoryDoc

logger = logging.getLogger(__name__)

COLLECTION_NAME = "keyword_cache"


@dataclass
class CacheHit:
    """语义缓存命中结果。"""

    task_id: str
    keyword: str
    platform: str
    content_file: str
    comment_file: str
    result_count: int
    crawl_timestamp: float
    distance: float


class KeywordCache:
    """
    关键词语义缓存。

    复用 Agent4 的 MemoryStore + embedder，在同一 Chroma persist_dir 下
    新建名为 keyword_cache 的 collection，通过向量相似度判断是否可以跳过爬虫。
    """

    def __init__(
        self,
        memory_store: MemoryStore,
        embedder: Embedder,
        similarity_threshold: float = 0.35,
    ) -> None:
        self._store = memory_store
        self._embedder = embedder
        self._threshold = similarity_threshold
        self._write_lock = threading.Lock()  # 序列化并发写入，防止重复 upsert

    def lookup(
        self,
        keyword: str,
        platform: str,
        ttl_hours: float = 24.0,
    ) -> CacheHit | None:
        """
        语义检索缓存。

        - 对 keyword 做向量化后查询 keyword_cache collection
        - 过滤：platform 匹配 + distance < threshold + TTL 未过期 + content_file 文件存在
        - 返回距离最小的第一个合格缓存项，否则返回 None
        - 任何异常均记录 warning 后返回 None，不阻断主流程
        """
        try:
            vector = self._embedder.embed([keyword])[0]
            hits = self._store.query(
                COLLECTION_NAME,
                query_vector=vector,
                top_k=5,
                where={"platform": platform},
            )
            now_ts = datetime.now(timezone.utc).timestamp()
            for hit in hits:
                # 已按距离升序排列，第一个超阈值即可停止
                if hit.distance >= self._threshold:
                    break
                meta = hit.metadata
                crawl_ts = float(meta.get("crawl_timestamp", 0.0))
                if now_ts - crawl_ts > ttl_hours * 3600:
                    continue
                content_file = meta.get("content_file", "")
                if not content_file or not Path(content_file).exists():
                    continue
                return CacheHit(
                    task_id=str(meta.get("task_id", "")),
                    keyword=str(meta.get("keyword", keyword)),
                    platform=str(meta.get("platform", platform)),
                    content_file=content_file,
                    comment_file=str(meta.get("comment_file", "")),
                    result_count=int(meta.get("result_count", 0)),
                    crawl_timestamp=crawl_ts,
                    distance=hit.distance,
                )
        except Exception as exc:
            logger.warning("keyword_cache.lookup 异常（非致命）keyword=%s error=%s", keyword, exc)
        return None

    def store(
        self,
        task_id: str,
        keyword: str,
        platform: str,
        content_file: str,
        comment_file: str,
        result_count: int,
    ) -> None:
        """
        将一次成功爬取写入缓存 collection。
        写入失败时记录 warning，不 raise。
        """
        with self._write_lock:
            try:
                doc = MemoryDoc(
                    id=f"kwcache:{task_id}",
                    content=keyword,
                    metadata={
                        "task_id": task_id,
                        "keyword": keyword,
                        "platform": platform,
                        "crawl_timestamp": datetime.now(timezone.utc).timestamp(),
                        "result_count": result_count,
                        "content_file": content_file,
                        "comment_file": comment_file,
                    },
                )
                self._store.upsert_docs(COLLECTION_NAME, [doc])
                logger.info(
                    "keyword_cache.store 完成 task_id=%s keyword=%s result_count=%s",
                    task_id, keyword, result_count,
                )
            except Exception as exc:
                logger.warning(
                    "keyword_cache.store 异常（非致命）task_id=%s error=%s", task_id, exc
                )


def build_keyword_cache(settings: object) -> KeywordCache:
    """
    工厂函数：从 app.core.config.Settings 构造 KeywordCache。
    复用 Agent4 的 persist_dir 和 embedder 配置，无需新建 Chroma 实例。
    """
    agent4_settings = get_agent4_settings()
    embedder = build_embedder(agent4_settings)
    store = MemoryStore(agent4_settings, embedder)
    threshold: float = getattr(settings, "keyword_cache_similarity_threshold", 0.35)
    return KeywordCache(store, embedder, threshold)

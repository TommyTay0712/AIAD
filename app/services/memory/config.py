"""Agent 4 独立配置。

故意不继承 ``app.core.config.Settings``，走独立的 ``AGENT4_*`` 环境变量前缀，
避免侵入 Agent 6 维护的全局 Settings。
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv
from pydantic import BaseModel, Field


class Agent4Settings(BaseModel):
    """Agent 4 的所有可调参数。"""

    project_root: Path
    persist_dir: Path = Field(
        description="Chroma 持久化目录，与 chroma_store.py 共享但使用独立 collection 名前缀",
    )
    seed_dir: Path = Field(description="种子数据目录，存放 jsonl/txt 文件")

    collection_prefix: str = Field(default="agent4_")
    collection_ad_examples: str = Field(default="agent4_ad_examples")
    collection_product_knowledge: str = Field(default="agent4_product_knowledge")

    embedding_provider: str = Field(default="local-bge")
    embedding_model: str = Field(default="BAAI/bge-small-zh-v1.5")
    embedding_base_url: str = Field(default="")
    embedding_api_key: str = Field(default="")
    embedding_query_prefix: str = Field(
        default="为这个句子生成表示以用于检索相关文章：",
        description="bge 官方推荐在 query 端添加的前缀；入库端不加",
    )

    top_k_recall: int = Field(default=20, ge=1, le=100)
    top_k_final: int = Field(default=5, ge=1, le=20)
    mmr_lambda: float = Field(default=0.7, ge=0.0, le=1.0)
    max_per_style: int = Field(default=2, ge=1, le=10)

    min_quality_score: float = Field(default=0.0, ge=0.0, le=1.0)


def get_agent4_settings() -> Agent4Settings:
    """读取 .env 并构造 Agent4Settings。每次调用返回新实例，便于测试替换。"""
    load_dotenv()
    project_root = Path(__file__).resolve().parents[3]
    persist_dir = project_root / os.getenv("AGENT4_PERSIST_DIR", "data/chroma")
    seed_dir = project_root / os.getenv("AGENT4_SEED_DIR", "assets/seeds")
    settings = Agent4Settings(
        project_root=project_root,
        persist_dir=persist_dir,
        seed_dir=seed_dir,
        collection_prefix=os.getenv("AGENT4_COLLECTION_PREFIX", "agent4_"),
        collection_ad_examples=os.getenv(
            "AGENT4_COLLECTION_AD_EXAMPLES", "agent4_ad_examples"
        ),
        collection_product_knowledge=os.getenv(
            "AGENT4_COLLECTION_PRODUCT_KNOWLEDGE", "agent4_product_knowledge"
        ),
        embedding_provider=os.getenv("AGENT4_EMBEDDING_PROVIDER", "local-bge"),
        embedding_model=os.getenv(
            "AGENT4_EMBEDDING_MODEL", "BAAI/bge-small-zh-v1.5"
        ),
        embedding_base_url=os.getenv("AGENT4_EMBEDDING_BASE_URL", ""),
        embedding_api_key=os.getenv("AGENT4_EMBEDDING_API_KEY", ""),
        embedding_query_prefix=os.getenv(
            "AGENT4_EMBEDDING_QUERY_PREFIX",
            "为这个句子生成表示以用于检索相关文章：",
        ),
        top_k_recall=int(os.getenv("AGENT4_TOP_K_RECALL", "20")),
        top_k_final=int(os.getenv("AGENT4_TOP_K_FINAL", "5")),
        mmr_lambda=float(os.getenv("AGENT4_MMR_LAMBDA", "0.7")),
        max_per_style=int(os.getenv("AGENT4_MAX_PER_STYLE", "2")),
        min_quality_score=float(os.getenv("AGENT4_MIN_QUALITY_SCORE", "0.0")),
    )
    settings.persist_dir.mkdir(parents=True, exist_ok=True)
    settings.seed_dir.mkdir(parents=True, exist_ok=True)
    return settings

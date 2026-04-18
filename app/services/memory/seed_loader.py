"""从 data/seeds/ 目录读取种子文件并灌入 Chroma。"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from app.services.memory.config import Agent4Settings
from app.services.memory.schemas import MemoryDoc

logger = logging.getLogger(__name__)

AD_EXAMPLES_FILENAME = "ad_examples.jsonl"
PRODUCT_KNOWLEDGE_FILENAME = "product_knowledge.jsonl"
FORBIDDEN_FILENAME = "forbidden_phrases.txt"


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            text = line.strip()
            if not text or text.startswith("#"):
                continue
            try:
                rows.append(json.loads(text))
            except json.JSONDecodeError as exc:
                logger.warning(
                    "seed JSONL 解析失败 file=%s err=%s line=%s",
                    path,
                    exc,
                    text[:120],
                )
    return rows


def load_forbidden_phrases(settings: Agent4Settings) -> list[str]:
    """读取风控词表。不存在或空行都安全跳过。"""
    path = settings.seed_dir / FORBIDDEN_FILENAME
    if not path.exists():
        return []
    phrases: list[str] = []
    seen: set[str] = set()
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            word = line.strip()
            if not word or word.startswith("#"):
                continue
            if word in seen:
                continue
            seen.add(word)
            phrases.append(word)
    return phrases


def _row_to_ad_example_doc(row: dict[str, Any], idx: int) -> MemoryDoc | None:
    content = str(row.get("content", "")).strip()
    if not content:
        return None
    doc_id = str(row.get("id") or f"ad-{idx:05d}")
    metadata: dict[str, Any] = {
        "source_type": "ad_example",
        "style": str(row.get("style", "")).strip(),
        "scene": str(row.get("scene", "")).strip(),
        "vibe": str(row.get("vibe", "")).strip(),
        "product_category": str(row.get("product_category", "")).strip(),
        "platform": str(row.get("platform", "小红书")).strip() or "小红书",
        "language_style": str(row.get("language_style", "")).strip(),
        "quality_score": float(row.get("quality_score", 0.5) or 0.5),
        "source": str(row.get("source", "")).strip(),
    }
    pains = row.get("pain_point_tags")
    if isinstance(pains, list):
        metadata["pain_point_tags"] = pains
    elif isinstance(pains, str) and pains.strip():
        metadata["pain_point_tags"] = [
            p.strip() for p in pains.split("|") if p.strip()
        ]
    return MemoryDoc(id=doc_id, content=content, metadata=metadata)


def _row_to_product_knowledge_doc(
    row: dict[str, Any], idx: int
) -> MemoryDoc | None:
    point = str(row.get("point", "")).strip()
    if not point:
        return None
    doc_id = str(row.get("id") or f"pk-{idx:05d}")
    metadata: dict[str, Any] = {
        "source_type": "product_knowledge",
        "brand": str(row.get("brand", "")).strip(),
        "product": str(row.get("product", "")).strip(),
        "evidence": str(row.get("evidence", "")).strip(),
        "evidence_type": str(row.get("evidence_type", "")).strip(),
        "allowed_claim": bool(row.get("allowed_claim", True)),
        "platform": str(row.get("platform", "小红书")).strip() or "小红书",
    }
    fit = row.get("scene_fit")
    if isinstance(fit, list):
        metadata["scene_fit"] = fit
    elif isinstance(fit, str) and fit.strip():
        metadata["scene_fit"] = [p.strip() for p in fit.split("|") if p.strip()]
    return MemoryDoc(id=doc_id, content=point, metadata=metadata)


def load_seeds_into_memory(
    settings: Agent4Settings | None = None,
    *,
    force: bool = False,
) -> dict[str, int]:
    """把 data/seeds/ 的两份 jsonl 灌进 Chroma。返回每个 collection 的写入条数。

    force=True 时会先删除同名 collection 再重建；否则默认 upsert。
    forbidden_phrases.txt 不进库，由 run_rag_agent 运行时按需读取。
    """
    # 延迟 import，避免 CLI help 命令触发 torch 加载
    from app.services.memory.embedder import build_embedder
    from app.services.memory.memory_store import MemoryStore

    settings = settings or _load_settings_lazily()
    embedder = build_embedder(settings)
    store = MemoryStore(settings, embedder)

    if force:
        store.recreate(settings.collection_ad_examples)
        store.recreate(settings.collection_product_knowledge)
    else:
        store.ensure_collections()

    counts: dict[str, int] = {}

    ad_rows = _read_jsonl(settings.seed_dir / AD_EXAMPLES_FILENAME)
    ad_docs: list[MemoryDoc] = []
    for idx, row in enumerate(ad_rows):
        doc = _row_to_ad_example_doc(row, idx)
        if doc:
            ad_docs.append(doc)
    counts[settings.collection_ad_examples] = store.upsert_docs(
        settings.collection_ad_examples, ad_docs
    )

    pk_rows = _read_jsonl(settings.seed_dir / PRODUCT_KNOWLEDGE_FILENAME)
    pk_docs: list[MemoryDoc] = []
    for idx, row in enumerate(pk_rows):
        doc = _row_to_product_knowledge_doc(row, idx)
        if doc:
            pk_docs.append(doc)
    counts[settings.collection_product_knowledge] = store.upsert_docs(
        settings.collection_product_knowledge, pk_docs
    )

    logger.info("load_seeds_into_memory 完成 counts=%s force=%s", counts, force)
    return counts


def _load_settings_lazily() -> Agent4Settings:
    from app.services.memory.config import get_agent4_settings

    return get_agent4_settings()

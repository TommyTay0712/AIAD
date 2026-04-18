"""可选的调试用 FastAPI Router。

Agent 4 不强行挂载；Agent 6 在合适的时机可以调 attach_to(app) 接入主服务。
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, FastAPI, HTTPException

from app.services.memory.config import get_agent4_settings
from app.services.memory.rag_agent import run_rag_agent

memory_router = APIRouter(prefix="/api/ad-intel/memory", tags=["agent4-memory"])


@memory_router.post("/probe")
def probe(payload: dict[str, Any]) -> dict[str, Any]:
    """接收一份 global_state JSON，返回 RagOutput（便于前端/Agent5 联调）。"""
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="payload 必须是 JSON 对象")
    state = {"global_state": payload}
    result = run_rag_agent(state)
    return result.get("global_state", {})


@memory_router.get("/status")
def status() -> dict[str, Any]:
    """查看 Agent 4 当前 collection 状态。"""
    from app.services.memory.embedder import build_embedder
    from app.services.memory.memory_store import MemoryStore

    settings = get_agent4_settings()
    embedder = build_embedder(settings)
    store = MemoryStore(settings, embedder)
    store.ensure_collections()
    return {
        "persist_dir": str(settings.persist_dir),
        "seed_dir": str(settings.seed_dir),
        "embedding_provider": settings.embedding_provider,
        "embedding_model": settings.embedding_model,
        "collections": {
            settings.collection_ad_examples: store.count(
                settings.collection_ad_examples
            ),
            settings.collection_product_knowledge: store.count(
                settings.collection_product_knowledge
            ),
        },
    }


def attach_to(app: FastAPI) -> None:
    """由 Agent 6 在自己的 main.py 里决定是否调用此函数挂载路由。"""
    app.include_router(memory_router)

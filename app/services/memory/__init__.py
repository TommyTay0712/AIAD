"""Agent 4: RAG & Memory 包的公共入口。

对外只暴露以下符号，内部实现细节对其他 Agent 不可见。
其他 Agent 只应以 ``from app.services.memory import run_rag_agent`` 的形式使用。
"""

from app.services.memory.rag_agent import run_rag_agent
from app.services.memory.schemas import (
    MemoryDoc,
    QuerySpec,
    RagOutput,
    RetrievalHit,
)
from app.services.memory.seed_loader import load_seeds_into_memory

__all__ = [
    "run_rag_agent",
    "load_seeds_into_memory",
    "RagOutput",
    "RetrievalHit",
    "QuerySpec",
    "MemoryDoc",
]

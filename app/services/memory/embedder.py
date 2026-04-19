"""统一 embedding 抽象。

- 默认使用本地 sentence-transformers + BAAI/bge-small-zh-v1.5。
- 保留 OpenAI 兼容接口（阿里云/Ollama embedding 模式）作为第二实现，未配置则不启用。
- 模型采用 lazy init：首次 embed 才加载权重，避免 app 启动阻塞。
"""

from __future__ import annotations

import logging
from typing import Any, Protocol, cast, runtime_checkable

import httpx

from app.services.memory.config import Agent4Settings

logger = logging.getLogger(__name__)


@runtime_checkable
class Embedder(Protocol):
    """Embedding 接口协议。"""

    model_name: str

    def embed(self, texts: list[str]) -> list[list[float]]:
        ...

    def get_dimension(self) -> int:
        ...


class _SentenceTransformerLike(Protocol):
    def encode(self, *args: Any, **kwargs: Any) -> Any:
        ...

    def get_sentence_embedding_dimension(self) -> int:
        ...


class LocalBgeEmbedder:
    """本地 sentence-transformers 实现。默认模型 BAAI/bge-small-zh-v1.5。"""

    def __init__(self, model_name: str) -> None:
        self.model_name = model_name
        self._model: _SentenceTransformerLike | None = None
        self._dim: int | None = None

    def _ensure_loaded(self) -> None:
        if self._model is not None:
            return
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as exc:
            raise RuntimeError(
                "未安装 sentence-transformers；请先 pip install sentence-transformers"
            ) from exc
        logger.info("加载 embedding 模型 model=%s (首次加载耗时较长)", self.model_name)
        self._model = cast(_SentenceTransformerLike, SentenceTransformer(self.model_name))
        self._dim = int(self._model.get_sentence_embedding_dimension())
        logger.info("embedding 模型加载完成 dim=%s", self._dim)

    def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        self._ensure_loaded()
        assert self._model is not None
        vectors = self._model.encode(
            texts,
            normalize_embeddings=True,
            convert_to_numpy=True,
        )
        return [vec.tolist() for vec in vectors]

    def get_dimension(self) -> int:
        self._ensure_loaded()
        assert self._dim is not None
        return self._dim


class OpenAICompatibleEmbedder:
    """调用 OpenAI 兼容的 /embeddings 接口。"""

    def __init__(
        self,
        *,
        base_url: str,
        model_name: str,
        api_key: str,
        timeout: int = 30,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model_name = model_name
        self.api_key = api_key
        self.timeout = timeout
        self._dim: int | None = None

    def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        payload = {"model": self.model_name, "input": texts}
        with httpx.Client(timeout=self.timeout) as client:
            resp = client.post(
                f"{self.base_url}/embeddings", json=payload, headers=headers
            )
            resp.raise_for_status()
            body = resp.json()
        vectors = [item["embedding"] for item in body.get("data", [])]
        if vectors and self._dim is None:
            self._dim = len(vectors[0])
        return vectors

    def get_dimension(self) -> int:
        if self._dim is not None:
            return self._dim
        vec = self.embed(["dim_probe"])
        if not vec:
            raise RuntimeError("无法通过 embedding 接口探测向量维度")
        return len(vec[0])


def build_embedder(settings: Agent4Settings) -> Embedder:
    """根据配置构造 embedder。provider 未识别时回退到本地 bge。"""
    provider = settings.embedding_provider.strip().lower()
    if provider in {"local-bge", "local", "bge", ""}:
        return LocalBgeEmbedder(model_name=settings.embedding_model)
    if provider in {"openai", "openai-compatible", "ollama"}:
        if not settings.embedding_base_url:
            raise ValueError(
                "embedding_provider 选择了远端接口但未配置 AGENT4_EMBEDDING_BASE_URL"
            )
        return OpenAICompatibleEmbedder(
            base_url=settings.embedding_base_url,
            model_name=settings.embedding_model,
            api_key=settings.embedding_api_key,
        )
    logger.warning(
        "未知 embedding_provider=%s，回退到 local-bge", settings.embedding_provider
    )
    return LocalBgeEmbedder(model_name=settings.embedding_model)

"""用于测试的确定性 Embedder。

不加载真实模型，基于字符 n-gram 生成 hash-based 向量。
相似文本的 hash 分布有一定重叠，在小样本上能展示 "相近句子相似度更高" 的定性效果。
"""

from __future__ import annotations

import hashlib
import math


DIM = 32


def _hash_vec(text: str, dim: int = DIM) -> list[float]:
    acc = [0.0] * dim
    tokens: list[str] = []
    for i in range(len(text)):
        tokens.append(text[i : i + 2])
        tokens.append(text[i : i + 3])
    if not tokens:
        tokens = [text or "_"]
    for tok in tokens:
        digest = hashlib.md5(tok.encode("utf-8")).digest()
        idx = digest[0] % dim
        sign = 1.0 if (digest[1] & 1) else -1.0
        acc[idx] += sign
    norm = math.sqrt(sum(x * x for x in acc)) or 1.0
    return [x / norm for x in acc]


class FakeEmbedder:
    """与 LocalBgeEmbedder 接口一致，供单测使用。"""

    model_name = "fake-hash-32"

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [_hash_vec(t) for t in texts]

    def get_dimension(self) -> int:
        return DIM

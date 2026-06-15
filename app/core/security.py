from __future__ import annotations

import hashlib
import hmac
import logging
import os
import time
from collections import defaultdict
from typing import Any

from fastapi import Depends, HTTPException, Request, Security
from fastapi.security import APIKeyHeader

logger = logging.getLogger(__name__)

# ============================================================
# SEC-02: API Key 认证中间件
# ============================================================

_API_KEY_HEADER = APIKeyHeader(name="X-API-Key", auto_error=False)

# 从环境变量加载合法 API Key 列表（逗号分隔）
# 若未设置，开发模式下跳过认证
_VALID_API_KEYS: set[str] | None = None


def _load_api_keys() -> set[str] | None:
    """延迟加载合法 API Key 集合。未配置时返回 None（开发模式跳过认证）。"""
    raw = os.getenv("AIAD_API_KEYS", "").strip()
    if not raw:
        return None
    return {key.strip() for key in raw.split(",") if key.strip()}


def _get_valid_keys() -> set[str] | None:
    global _VALID_API_KEYS
    if _VALID_API_KEYS is None:
        _VALID_API_KEYS = _load_api_keys()
    return _VALID_API_KEYS


def _constant_time_compare(a: str, b: str) -> bool:
    """常量时间比较，防止计时攻击。"""
    return hmac.compare_digest(a.encode(), b.encode())


async def verify_api_key(api_key: str | None = Security(_API_KEY_HEADER)) -> str | None:
    """
    API Key 认证依赖。

    - 若环境变量 AIAD_API_KEYS 未设置，跳过认证（开发模式）
    - 若已设置，请求必须携带有效的 X-API-Key 头
    """
    valid_keys = _get_valid_keys()
    if valid_keys is None:
        # 开发模式：未配置 API Key，不强制认证
        return None
    if api_key is None:
        raise HTTPException(
            status_code=401,
            detail={"error_code": "AUTH_REQUIRED", "message": "缺少 X-API-Key 请求头"},
        )
    if not any(_constant_time_compare(api_key, k) for k in valid_keys):
        logger.warning("认证失败 api_key_prefix=%s", api_key[:8] if len(api_key) >= 8 else "***")
        raise HTTPException(
            status_code=403,
            detail={"error_code": "AUTH_INVALID", "message": "API Key 无效"},
        )
    return api_key


# ============================================================
# SEC-03: 内存速率限制
# ============================================================

class RateLimiter:
    """
    基于滑动窗口的内存速率限制器。

    支持按客户端 IP 限制请求频率，防止资源滥用与 DDoS 攻击。
    """

    def __init__(self, max_requests: int = 30, window_seconds: int = 60) -> None:
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._requests: dict[str, list[float]] = defaultdict(list)

    def _client_key(self, request: Request) -> str:
        """提取客户端标识（优先 X-Forwarded-For，兜底 client.host）。"""
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            return forwarded.split(",")[0].strip()
        return request.client.host if request.client else "unknown"

    def _cleanup(self, key: str, now: float) -> None:
        """清理滑动窗口外的过期记录。"""
        cutoff = now - self.window_seconds
        self._requests[key] = [t for t in self._requests[key] if t > cutoff]

    def check(self, request: Request) -> None:
        """检查请求是否超出频率限制，超出则抛出 429。"""
        now = time.time()
        key = self._client_key(request)
        self._cleanup(key, now)

        if len(self._requests[key]) >= self.max_requests:
            logger.warning(
                "速率限制触发 client=%s count=%d window=%ds",
                key, len(self._requests[key]), self.window_seconds,
            )
            raise HTTPException(
                status_code=429,
                detail={
                    "error_code": "RATE_LIMITED",
                    "message": f"请求过于频繁，每 {self.window_seconds} 秒最多 {self.max_requests} 次",
                },
            )
        self._requests[key].append(now)


# 全局限流器实例（可按需在不同路由使用不同实例）
global_limiter = RateLimiter(max_requests=60, window_seconds=60)      # 全局：60/分
run_limiter = RateLimiter(max_requests=5, window_seconds=60)          # /run 端点：5/分
agent_limiter = RateLimiter(max_requests=10, window_seconds=60)       # Agent 端点：10/分


def check_global_rate(request: Request) -> None:
    """全局速率限制依赖。"""
    global_limiter.check(request)


def check_run_rate(request: Request) -> None:
    """/run 端点速率限制依赖。"""
    run_limiter.check(request)


def check_agent_rate(request: Request) -> None:
    """Agent 端点速率限制依赖。"""
    agent_limiter.check(request)

from __future__ import annotations

"""
API Gateway 微服务

职责：
- 统一入口，代理请求到下游微服务
- 认证中间件（API Key）
- 速率限制
- 请求日志与审计
- 前端静态资源服务
"""

import logging

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from starlette.middleware.base import BaseHTTPMiddleware

from services.shared.config import load_service_config
from services.shared.schemas import HealthResponse

logger = logging.getLogger(__name__)

config = load_service_config("gateway")

app = FastAPI(title="AIAD Gateway", version="0.1.0")


# ─── 认证中间件 ──────────────────────────────────────────────

class AuthMiddleware(BaseHTTPMiddleware):
    """基于 X-API-Key 的认证中间件。"""

    _SKIP_PATHS = {"/", "/health", "/docs", "/openapi.json", "/redoc"}

    async def dispatch(self, request: Request, call_next):  # type: ignore[override]
        if request.url.path in self._SKIP_PATHS:
            return await call_next(request)

        valid_keys = {k.strip() for k in config.api_keys.split(",") if k.strip()}
        if not valid_keys:
            # 未配置 API Key → 开发模式，跳过认证
            return await call_next(request)

        api_key = request.headers.get("X-API-Key", "")
        if api_key not in valid_keys:
            return JSONResponse(
                status_code=401,
                content={"error_code": "AUTH_REQUIRED", "message": "缺少或无效的 X-API-Key"},
            )
        return await call_next(request)


app.add_middleware(AuthMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization", "X-API-Key", "X-AI-Model"],
)


# ─── 健康检查 ──────────────────────────────────────────────

@app.get("/health", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    return HealthResponse(service="gateway")


# ─── 代理路由 ──────────────────────────────────────────────

async def _proxy_request(
    service_url: str,
    path: str,
    request: Request,
) -> JSONResponse:
    """将请求代理到下游微服务（JSON 响应）。"""
    url = f"{service_url}{path}"
    headers = dict(request.headers)
    headers.pop("host", None)

    try:
        async with httpx.AsyncClient(timeout=300) as client:
            if request.method == "GET":
                resp = await client.get(url, headers=headers)
            elif request.method == "POST":
                body = await request.body()
                resp = await client.post(url, content=body, headers=headers)
            else:
                raise HTTPException(status_code=405, detail="Method not allowed")
        try:
            content = resp.json() if resp.text else {}
        except Exception:
            content = {"raw": resp.text}
        return JSONResponse(status_code=resp.status_code, content=content)
    except httpx.ConnectError:
        logger.error("下游服务连接失败 url=%s", url)
        return JSONResponse(
            status_code=503,
            content={"error_code": "SERVICE_UNAVAILABLE", "message": "下游服务不可用"},
        )


async def _proxy_stream(service_url: str, path: str, request: Request) -> StreamingResponse:
    """将 SSE 流式请求透传到下游微服务。"""
    url = f"{service_url}{path}"
    headers = dict(request.headers)
    headers.pop("host", None)

    # SSE 长连接期间不能有 read timeout，只限制 connect
    client = httpx.AsyncClient(timeout=httpx.Timeout(connect=30.0, read=None, write=None, pool=None))

    async def generator():
        try:
            async with client.stream("GET", url, headers=headers) as resp:
                async for chunk in resp.aiter_bytes():
                    yield chunk
        except httpx.ConnectError:
            logger.error("SSE 下游服务连接失败 url=%s", url)
            yield b"data: {\"type\": \"error\", \"message\": \"service unavailable\"}\n\n"
        finally:
            await client.aclose()

    return StreamingResponse(
        generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no", "Connection": "keep-alive"},
    )


@app.api_route("/api/ad-intel/{path:path}", methods=["GET", "POST"])
async def proxy_to_task_service(path: str, request: Request):
    """代理 ad-intel API 到 Task Service。"""
    if path.endswith("/stream"):
        return await _proxy_stream(config.task_service_url, f"/api/ad-intel/{path}", request)
    return await _proxy_request(config.task_service_url, f"/api/ad-intel/{path}", request)



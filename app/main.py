from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

from app.api.routes import router
from app.core.config import get_settings
from app.core.logging_config import configure_logging
from app.core.scheduler import lifespan


# SEC-16: 请求体大小限制中间件（10MB）
_MAX_BODY_SIZE = 10 * 1024 * 1024  # 10MB


class RequestBodySizeLimitMiddleware(BaseHTTPMiddleware):
    """拒绝超过 10MB 的请求体，防止资源耗尽攻击。"""

    async def dispatch(self, request: Request, call_next):  # type: ignore[override]
        content_length = request.headers.get("content-length")
        if content_length and int(content_length) > _MAX_BODY_SIZE:
            return JSONResponse(
                status_code=413,
                content={"error_code": "PAYLOAD_TOO_LARGE", "message": "请求体过大（最大 10MB）"},
            )
        return await call_next(request)


settings = get_settings()
configure_logging(settings.logs_dir, settings.log_level)

app = FastAPI(title="AIAD API", version="0.1.0", lifespan=lifespan)
app.add_middleware(RequestBodySizeLimitMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization", "X-AI-Model"],
)
app.include_router(router)

frontend_dir = Path(__file__).resolve().parents[1] / "frontend"
app.mount("/static", StaticFiles(directory=frontend_dir), name="static")


@app.get("/")
def index() -> FileResponse:
    """返回前端页面。"""
    return FileResponse(frontend_dir / "index.html")

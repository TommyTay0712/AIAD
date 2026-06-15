from __future__ import annotations

"""
共享 Pydantic 数据模型 — 各微服务间通信使用的统一 schema。

保持与原 app/models/schemas.py 一致，但仅包含跨服务通信所需的类型。
"""

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class TaskStatus(str, Enum):
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"


class ErrorCode(str, Enum):
    LOGIN_REQUIRED = "LOGIN_REQUIRED"
    INVALID_INPUT = "INVALID_INPUT"
    CRAWLER_ERROR = "CRAWLER_ERROR"
    INTERNAL_ERROR = "INTERNAL_ERROR"
    AUTH_REQUIRED = "AUTH_REQUIRED"
    RATE_LIMITED = "RATE_LIMITED"


class VisionAnalysis(BaseModel):
    scene: str = ""
    vibe: str = ""
    detected_items: list[str] = Field(default_factory=list)
    people_emotions: list[str] = Field(default_factory=list)
    visual_highlights: list[str] = Field(default_factory=list)
    risk_flags: list[str] = Field(default_factory=list)
    source_media_count: int = 0
    model_provider: str = ""
    model_name: str = ""


class NLPAnalysis(BaseModel):
    main_emotion: str = ""
    pain_points: list[str] = Field(default_factory=list)
    language_style: str = ""
    ad_angles: list[str] = Field(default_factory=list)
    keyword_summary: list[str] = Field(default_factory=list)


class AdDraft(BaseModel):
    style: str = ""
    content: str = ""


class CrawlRequest(BaseModel):
    """Crawler Service 请求体。"""
    task_id: str
    platform: str = "xhs"
    keywords: list[str] = Field(default_factory=list)
    limit: int = Field(default=20, ge=1, le=200)
    max_comments_per_note: int = Field(default=10, ge=1, le=200)
    enable_media_download: bool = False


class CrawlResult(BaseModel):
    """Crawler Service 响应体。"""
    task_id: str
    status: TaskStatus
    content_file: str = ""
    comment_file: str = ""
    media_root_dir: str = ""
    error_code: ErrorCode | None = None
    error_message: str = ""
    # 评论数据内联返回，避免 Docker 容器无法访问宿主机文件路径
    comments: list[dict[str, Any]] = Field(default_factory=list)


class AnalysisRequest(BaseModel):
    """Analysis Service 请求体。"""
    task_id: str
    media_paths: list[str] = Field(default_factory=list)
    comments: list[dict[str, Any]] = Field(default_factory=list)
    product_info: str = ""


class AnalysisResult(BaseModel):
    """Analysis Service 响应体。"""
    task_id: str
    vision_analysis: VisionAnalysis = Field(default_factory=VisionAnalysis)
    nlp_analysis: NLPAnalysis = Field(default_factory=NLPAnalysis)
    rag_references: list[str] = Field(default_factory=list)


class CopywriterRequest(BaseModel):
    """Copywriter Service 请求体。"""
    task_id: str
    request_info: dict[str, Any] = Field(default_factory=dict)
    vision_analysis: dict[str, Any] = Field(default_factory=dict)
    nlp_analysis: dict[str, Any] = Field(default_factory=dict)
    rag_references: list[str] = Field(default_factory=list)
    styles: list[str] = Field(default_factory=list)
    comments: list[dict[str, Any]] = Field(default_factory=list)


class CopywriterResult(BaseModel):
    """Copywriter Service 响应体。"""
    task_id: str
    final_ads: list[AdDraft] = Field(default_factory=list)
    review_score: int = 0
    comment_ads: dict[str, str] = Field(default_factory=dict)


class HealthResponse(BaseModel):
    """健康检查响应。"""
    service: str
    status: str = "ok"
    version: str = "0.1.0"

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, field_validator


class TaskStatus(str, Enum):
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"


class ErrorCode(str, Enum):
    LOGIN_REQUIRED = "LOGIN_REQUIRED"
    INVALID_INPUT = "INVALID_INPUT"
    CRAWLER_ERROR = "CRAWLER_ERROR"
    INTERNAL_ERROR = "INTERNAL_ERROR"


class RunRequest(BaseModel):
    """分析请求入参。"""

    ad_type: str = Field(min_length=1)
    keywords: list[str] = Field(default_factory=list)
    platform: str = Field(default="xhs")
    limit: int = Field(default=20, ge=1, le=200)
    time_range: str = Field(default="")

    @field_validator("keywords")
    @classmethod
    def normalize_keywords(cls, value: list[str]) -> list[str]:
        return [item.strip() for item in value if item.strip()]


class TaskResponse(BaseModel):
    task_id: str
    status: TaskStatus
    error_code: ErrorCode | None = None
    message: str = ""


class AnalyzeOutput(BaseModel):
    summary: dict[str, Any]
    content_table: list[dict[str, Any]]
    comment_table: list[dict[str, Any]]
    feature_table: list[dict[str, Any]]


class TaskRecord(BaseModel):
    task_id: str
    created_at: datetime
    updated_at: datetime
    status: TaskStatus
    params: dict[str, Any]
    output_files: dict[str, str] = Field(default_factory=dict)
    error_code: ErrorCode | None = None
    error_message: str = ""
    result: dict[str, Any] = Field(default_factory=dict)

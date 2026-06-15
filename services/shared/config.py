from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv
from pydantic import BaseModel, Field


load_dotenv()


class ServiceConfig(BaseModel):
    """微服务通用配置基类。"""

    service_name: str = Field(default="unknown")
    service_port: int = Field(default=8000)
    log_level: str = Field(default="INFO")
    redis_url: str = Field(default="redis://localhost:6379/0")
    api_keys: str = Field(default="")

    # 跨服务通信基础 URL
    gateway_url: str = Field(default="http://localhost:8000")
    task_service_url: str = Field(default="http://localhost:8001")
    crawler_service_url: str = Field(default="http://localhost:8002")
    analysis_service_url: str = Field(default="http://localhost:8003")
    copywriter_service_url: str = Field(default="http://localhost:8004")

    # LLM 配置（Analysis + Copywriter 服务共享）
    llm_provider: str = Field(default="modelscope")
    llm_base_url: str = Field(default="https://api-inference.modelscope.cn/v1")
    llm_model: str = Field(default="Qwen/Qwen3.5-397B-A17B")
    llm_api_key: str = Field(default="")
    llm_timeout_seconds: int = Field(default=300)
    llm_temperature: float = Field(default=0.7)
    llm_max_tokens: int = Field(default=3000)


def load_service_config(service_name: str) -> ServiceConfig:
    """从环境变量加载微服务配置。"""
    prefix = service_name.upper().replace("-", "_")
    return ServiceConfig(
        service_name=service_name,
        service_port=int(os.getenv(f"{prefix}_PORT", os.getenv("SERVICE_PORT", "8000"))),
        log_level=os.getenv("LOG_LEVEL", "INFO"),
        redis_url=os.getenv("REDIS_URL", "redis://localhost:6379/0"),
        api_keys=os.getenv("AIAD_API_KEYS", ""),
        gateway_url=os.getenv("GATEWAY_URL", "http://localhost:8000"),
        task_service_url=os.getenv("TASK_SERVICE_URL", "http://localhost:8001"),
        crawler_service_url=os.getenv("CRAWLER_SERVICE_URL", "http://localhost:8002"),
        analysis_service_url=os.getenv("ANALYSIS_SERVICE_URL", "http://localhost:8003"),
        copywriter_service_url=os.getenv("COPYWRITER_SERVICE_URL", "http://localhost:8004"),
        llm_provider=os.getenv("LLM_PROVIDER", "modelscope"),
        llm_base_url=os.getenv("LLM_BASE_URL", "https://api-inference.modelscope.cn/v1"),
        llm_model=os.getenv("LLM_MODEL", "Qwen/Qwen3.5-397B-A17B"),
        llm_api_key=os.getenv("LLM_API_KEY", ""),
        llm_timeout_seconds=int(os.getenv("LLM_TIMEOUT_SECONDS", "300")),
        llm_temperature=float(os.getenv("LLM_TEMPERATURE", "0.7")),
        llm_max_tokens=int(os.getenv("LLM_MAX_TOKENS", "3000")),
    )

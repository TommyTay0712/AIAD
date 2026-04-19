from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

from dotenv import load_dotenv
from pydantic import BaseModel, Field


def _resolve_path(project_root: Path, env_name: str, default: str) -> Path:
    raw_value = os.getenv(env_name, default)
    path = Path(raw_value).expanduser()
    return path if path.is_absolute() else project_root / path


def _resolve_executable(project_root: Path, env_name: str, default: str) -> Path:
    raw_value = os.getenv(env_name, default).strip()
    if not raw_value:
        return Path(default)
    resolved = shutil.which(raw_value)
    if resolved:
        return Path(resolved)
    path = Path(raw_value).expanduser()
    return path if path.is_absolute() else project_root / path


class Settings(BaseModel):
    """应用配置对象。"""

    project_root: Path = Field(default=Path(__file__).resolve().parents[2])
    aiad_python_exe: Path = Field(default=Path(sys.executable))
    media_crawler_dir: Path = Field(
        default=Path(__file__).resolve().parents[2] / "vendor" / "MediaCrawler"
    )
    crawler_output_dir: Path = Field(default=Path(__file__).resolve().parents[2] / "data" / "raw")
    processed_output_dir: Path = Field(
        default=Path(__file__).resolve().parents[2] / "data" / "processed"
    )
    logs_dir: Path = Field(default=Path(__file__).resolve().parents[2] / "logs")
    task_store_file: Path = Field(
        default=Path(__file__).resolve().parents[2] / "data" / "tasks.json"
    )
    chroma_persist_dir: Path = Field(
        default=Path(__file__).resolve().parents[2] / "data" / "chroma"
    )
    mediacrawler_python_exe: Path = Field(default=Path(sys.executable))
    playwright_browsers_path: Path = Field(
        default=Path(__file__).resolve().parents[2] / ".ms-playwright"
    )
    log_level: str = Field(default="INFO")
    vision_provider: str = Field(default="mock")
    vision_model: str = Field(default="Qwen/Qwen3.5-397B-A17B")
    vision_api_base: str = Field(default="https://api-inference.modelscope.cn/v1")
    vision_api_key: str = Field(default="")
    vision_timeout_seconds: int = Field(default=45)
    vision_enable_mock_fallback: bool = Field(default=True)
    vision_max_media_count: int = Field(default=6)
    vision_video_frame_sample_count: int = Field(default=3)
    llm_provider: str = Field(default="disabled")
    llm_base_url: str = Field(default="http://127.0.0.1:11434/v1")
    llm_model: str = Field(default="qwen2.5:3b-instruct")
    llm_api_key: str = Field(default="local-dev")
    llm_timeout_seconds: int = Field(default=120)
    llm_temperature: float = Field(default=0.7)
    llm_max_tokens: int = Field(default=1200)


def get_settings() -> Settings:
    """加载环境变量并返回配置。"""
    load_dotenv()
    project_root = Path(__file__).resolve().parents[2]
    settings = Settings(
        project_root=project_root,
        aiad_python_exe=_resolve_executable(project_root, "AIAD_PYTHON_EXE", sys.executable),
        media_crawler_dir=_resolve_path(project_root, "MEDIA_CRAWLER_DIR", "vendor/MediaCrawler"),
        crawler_output_dir=_resolve_path(project_root, "CRAWLER_OUTPUT_DIR", "data/raw"),
        processed_output_dir=_resolve_path(project_root, "PROCESSED_OUTPUT_DIR", "data/processed"),
        logs_dir=_resolve_path(project_root, "LOGS_DIR", "logs"),
        task_store_file=_resolve_path(project_root, "TASK_STORE_FILE", "data/tasks.json"),
        chroma_persist_dir=_resolve_path(project_root, "CHROMA_PERSIST_DIR", "data/chroma"),
        mediacrawler_python_exe=_resolve_executable(
            project_root, "MEDIACRAWLER_PYTHON_EXE", sys.executable
        ),
        playwright_browsers_path=_resolve_path(
            project_root, "PLAYWRIGHT_BROWSERS_PATH", ".ms-playwright"
        ),
        log_level=os.getenv("LOG_LEVEL", "INFO"),
        vision_provider=os.getenv("VISION_PROVIDER", "mock"),
        vision_model=os.getenv("VISION_MODEL", "Qwen/Qwen3.5-397B-A17B"),
        vision_api_base=os.getenv("VISION_API_BASE", "https://api-inference.modelscope.cn/v1"),
        vision_api_key=os.getenv("VISION_API_KEY", ""),
        vision_timeout_seconds=int(os.getenv("VISION_TIMEOUT_SECONDS", "45")),
        vision_enable_mock_fallback=os.getenv("VISION_ENABLE_MOCK_FALLBACK", "true").lower()
        in {"1", "true", "yes", "y"},
        vision_max_media_count=int(os.getenv("VISION_MAX_MEDIA_COUNT", "6")),
        vision_video_frame_sample_count=int(os.getenv("VISION_VIDEO_FRAME_SAMPLE_COUNT", "3")),
        llm_provider=os.getenv("LLM_PROVIDER", "disabled"),
        llm_base_url=os.getenv("LLM_BASE_URL", "http://127.0.0.1:11434/v1"),
        llm_model=os.getenv("LLM_MODEL", "qwen2.5:3b-instruct"),
        llm_api_key=os.getenv("LLM_API_KEY", "local-dev"),
        llm_timeout_seconds=int(os.getenv("LLM_TIMEOUT_SECONDS", "120")),
        llm_temperature=float(os.getenv("LLM_TEMPERATURE", "0.7")),
        llm_max_tokens=int(os.getenv("LLM_MAX_TOKENS", "1200")),
    )
    settings.crawler_output_dir.mkdir(parents=True, exist_ok=True)
    settings.processed_output_dir.mkdir(parents=True, exist_ok=True)
    settings.logs_dir.mkdir(parents=True, exist_ok=True)
    settings.chroma_persist_dir.mkdir(parents=True, exist_ok=True)
    settings.playwright_browsers_path.mkdir(parents=True, exist_ok=True)
    settings.task_store_file.parent.mkdir(parents=True, exist_ok=True)
    if not settings.task_store_file.exists():
        settings.task_store_file.write_text("{}", encoding="utf-8")
    return settings

from __future__ import annotations

import functools
import os
import shutil
import sys
from pathlib import Path

from dotenv import load_dotenv
from pydantic import BaseModel, Field


def _clean_text(value: str) -> str:
    """清理环境变量中的多余空白与反引号。"""
    return value.strip().strip("`").strip("'").strip('"').strip()


def _resolve_text(env_name: str, default: str) -> str:
    return _clean_text(os.getenv(env_name, default))


def _resolve_path(project_root: Path, env_name: str, default: str) -> Path:
    raw_value = _resolve_text(env_name, default)
    path = Path(raw_value).expanduser()
    return path if path.is_absolute() else project_root / path


def _resolve_executable(project_root: Path, env_name: str, default: str) -> Path:
    raw_value = _resolve_text(env_name, default)
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
        default=Path(__file__).resolve().parents[2] / "data" / "tasks.db"
    )
    chroma_persist_dir: Path = Field(
        default=Path(__file__).resolve().parents[2] / "data" / "chroma"
    )
    mediacrawler_python_exe: Path = Field(default=Path(sys.executable))
    playwright_browsers_path: Path = Field(
        default=Path(__file__).resolve().parents[2] / ".ms-playwright"
    )
    headless_browser: bool = Field(default=False)
    log_level: str = Field(default="INFO")
    vision_provider: str = Field(default="mock")
    vision_model: str = Field(default="Qwen/Qwen3.5-397B-A17B")
    vision_api_base: str = Field(default="https://api-inference.modelscope.cn/v1")
    vision_api_key: str = Field(default="")
    vision_timeout_seconds: int = Field(default=45)
    vision_enable_mock_fallback: bool = Field(default=True)
    vision_max_media_count: int = Field(default=6)
    vision_video_frame_sample_count: int = Field(default=3)
    llm_provider: str = Field(default="modelscope")
    llm_base_url: str = Field(default="https://api-inference.modelscope.cn/v1")
    llm_model: str = Field(default="Qwen/Qwen3.5-397B-A17B")
    llm_api_key: str = Field(default="")
    llm_timeout_seconds: int = Field(default=300)
    llm_temperature: float = Field(default=0.7)
    llm_max_tokens: int = Field(default=3000)
    keyword_cache_ttl_hours: int = Field(default=24)
    keyword_cache_similarity_threshold: float = Field(default=0.35)
    trend_crawl_interval_hours: int = Field(default=6)
    trend_keywords_file: Path = Field(
        default=Path(__file__).resolve().parents[2] / "data" / "trend_keywords.json"
    )


def validate_path_sandbox(path: Path, allowed_root: Path) -> Path:
    """SEC-12: 校验路径是否在允许的根目录内，防止路径穿越攻击。"""
    resolved = path.resolve()
    root = allowed_root.resolve()
    if not str(resolved).startswith(str(root)):
        raise ValueError(f"路径越界：{resolved} 不在允许的根目录 {root} 内")
    return resolved


@functools.lru_cache(maxsize=1)
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
        task_store_file=_resolve_path(project_root, "TASK_STORE_FILE", "data/tasks.db"),
        chroma_persist_dir=_resolve_path(project_root, "CHROMA_PERSIST_DIR", "data/chroma"),
        mediacrawler_python_exe=_resolve_executable(
            project_root, "MEDIACRAWLER_PYTHON_EXE", sys.executable
        ),
        playwright_browsers_path=_resolve_path(
            project_root, "PLAYWRIGHT_BROWSERS_PATH", ".ms-playwright"
        ),
        headless_browser=os.getenv("HEADLESS_BROWSER", "false").lower() in {"1", "true", "yes"},
        log_level=_resolve_text("LOG_LEVEL", "INFO"),
        vision_provider=_resolve_text("VISION_PROVIDER", "modelscope"),
        vision_model=_resolve_text("VISION_MODEL", "Qwen/Qwen3.5-397B-A17B"),
        vision_api_base=_resolve_text(
            "VISION_API_BASE", "https://api-inference.modelscope.cn/v1"
        ),
        vision_api_key=_resolve_text("VISION_API_KEY", ""),
        vision_timeout_seconds=int(os.getenv("VISION_TIMEOUT_SECONDS", "45")),
        vision_enable_mock_fallback=os.getenv("VISION_ENABLE_MOCK_FALLBACK", "true").lower()
        in {"1", "true", "yes", "y"},
        vision_max_media_count=int(os.getenv("VISION_MAX_MEDIA_COUNT", "6")),
        vision_video_frame_sample_count=int(os.getenv("VISION_VIDEO_FRAME_SAMPLE_COUNT", "3")),
        llm_provider=_resolve_text("LLM_PROVIDER", "modelscope"),
        llm_base_url=_resolve_text("LLM_BASE_URL", "https://api-inference.modelscope.cn/v1"),
        llm_model=_resolve_text("LLM_MODEL", "Qwen/Qwen3.5-397B-A17B"),
        llm_api_key=_resolve_text("LLM_API_KEY", ""),
        llm_timeout_seconds=int(os.getenv("LLM_TIMEOUT_SECONDS", "300")),
        llm_temperature=float(os.getenv("LLM_TEMPERATURE", "0.7")),
        llm_max_tokens=int(os.getenv("LLM_MAX_TOKENS", "3000")),
        keyword_cache_ttl_hours=int(os.getenv("KEYWORD_CACHE_TTL_HOURS", "24")),
        keyword_cache_similarity_threshold=float(
            os.getenv("KEYWORD_CACHE_SIMILARITY_THRESHOLD", "0.35")
        ),
        trend_crawl_interval_hours=int(os.getenv("TREND_CRAWL_INTERVAL_HOURS", "6")),
        trend_keywords_file=_resolve_path(
            project_root, "TREND_KEYWORDS_FILE", "data/trend_keywords.json"
        ),
    )
    settings.crawler_output_dir.mkdir(parents=True, exist_ok=True)
    settings.processed_output_dir.mkdir(parents=True, exist_ok=True)
    settings.logs_dir.mkdir(parents=True, exist_ok=True)
    settings.chroma_persist_dir.mkdir(parents=True, exist_ok=True)
    settings.playwright_browsers_path.mkdir(parents=True, exist_ok=True)
    settings.task_store_file.parent.mkdir(parents=True, exist_ok=True)
    # SQLite 文件由 TaskStore._init_db() 在首次实例化时自动创建，此处无需预建
    return settings

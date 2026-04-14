from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv
from pydantic import BaseModel, Field


def _resolve_project_path(project_root: Path, raw_value: str) -> Path:
    path = Path(raw_value).expanduser()
    return path if path.is_absolute() else project_root / path


def _default_python_in_prefix(prefix: Path) -> Path:
    return prefix / ("python.exe" if os.name == "nt" else "bin/python")


class Settings(BaseModel):
    """应用配置对象。"""

    project_root: Path = Field(default=Path(__file__).resolve().parents[2])
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
    mediacrawler_python_exe: Path = Field(
        default=_default_python_in_prefix(
            Path(__file__).resolve().parents[2] / ".conda" / "mediacrawler"
        )
    )
    playwright_browsers_path: Path = Field(
        default=Path(__file__).resolve().parents[2] / ".ms-playwright"
    )


def get_settings() -> Settings:
    """加载环境变量并返回配置。"""
    load_dotenv()
    project_root = Path(__file__).resolve().parents[2]
    settings = Settings(
        project_root=project_root,
        media_crawler_dir=_resolve_project_path(
            project_root, os.getenv("MEDIA_CRAWLER_DIR", "vendor/MediaCrawler")
        ),
        crawler_output_dir=_resolve_project_path(
            project_root, os.getenv("CRAWLER_OUTPUT_DIR", "data/raw")
        ),
        processed_output_dir=_resolve_project_path(
            project_root, os.getenv("PROCESSED_OUTPUT_DIR", "data/processed")
        ),
        logs_dir=_resolve_project_path(project_root, os.getenv("LOGS_DIR", "logs")),
        task_store_file=_resolve_project_path(
            project_root, os.getenv("TASK_STORE_FILE", "data/tasks.json")
        ),
        chroma_persist_dir=_resolve_project_path(
            project_root, os.getenv("CHROMA_PERSIST_DIR", "data/chroma")
        ),
        mediacrawler_python_exe=_resolve_project_path(
            project_root,
            os.getenv(
                "MEDIACRAWLER_PYTHON_EXE",
                str(_default_python_in_prefix(Path(".conda") / "mediacrawler")),
            ),
        ),
        playwright_browsers_path=_resolve_project_path(
            project_root, os.getenv("PLAYWRIGHT_BROWSERS_PATH", ".ms-playwright")
        ),
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

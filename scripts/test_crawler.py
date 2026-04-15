from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))

from app.core.config import get_settings
from app.services.crawler_runner import run_crawler
from app.services.task_store import TaskStore

logger = logging.getLogger(__name__)


def main() -> None:
    settings = get_settings()
    task_store = TaskStore(settings.task_store_file)

    logger.info("开始执行爬虫调试任务")
    result = run_crawler(
        settings=settings,
        task_store=task_store,
        platform="xhs",
        keywords=["流浪地球"],
        limit=20,
        max_comments_per_note=15,
        enable_media_download=True,
    )

    logger.info("task_id=%s status=%s", result.task_id, result.status)
    if result.error_message:
        logger.error("crawler_error=%s", result.error_message)
    logger.info("output_files=%s", json.dumps(result.output_files, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
    main()

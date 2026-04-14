import sys
from pathlib import Path
import asyncio
import json

# Add the project root to sys.path
sys.path.append(str(Path(__file__).resolve().parent.parent))

from app.core.config import get_settings
from app.services.crawler_runner import run_crawler
from app.services.task_store import TaskStore

def main():
    settings = get_settings()
    task_store = TaskStore(settings.task_store_file)
    
    print("Starting crawler task...")
    result = run_crawler(
        settings=settings,
        task_store=task_store,
        platform="xhs",
        keywords=["流浪地球"],
        limit=20,
        max_comments_per_note=15,
        enable_media_download=True,
    )
    
    print(f"Task ID: {result.task_id}")
    print(f"Status: {result.status}")
    if result.error_message:
        print(f"Error: {result.error_message}")
    print("Output files:")
    print(json.dumps(result.output_files, indent=2, ensure_ascii=False))

if __name__ == "__main__":
    main()

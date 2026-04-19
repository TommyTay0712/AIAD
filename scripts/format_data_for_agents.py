from __future__ import annotations

import json
import logging
import shutil
import sys
from pathlib import Path

logger = logging.getLogger(__name__)


def format_crawler_data(task_id: str, base_dir: Path | None = None) -> None:
    """将爬虫输出整理为各 Agent 可直接消费的 mock_state。"""
    root = base_dir or Path(__file__).resolve().parents[1] / "data" / "raw"
    content_file = root / f"{task_id}_search_contents.jsonl"
    comment_file = root / f"{task_id}_search_comments.jsonl"
    media_dir = root / "_runs" / task_id / "xhs"

    if not content_file.exists():
        logger.error("未找到内容文件: %s", content_file)
        return

    comments_by_post: dict[str, list[dict[str, object]]] = {}
    if comment_file.exists():
        with comment_file.open("r", encoding="utf-8") as handle:
            for line in handle:
                if not line.strip():
                    continue
                data = json.loads(line)
                post_id = str(data.get("note_id", "")).strip()
                if not post_id:
                    continue
                comments_by_post.setdefault(post_id, []).append(
                    {
                        "user": data.get("nickname", "Unknown"),
                        "content": data.get("content", ""),
                        "likes": data.get("like_count", 0),
                    }
                )

    with content_file.open("r", encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            data = json.loads(line)
            post_id = str(data.get("note_id", "")).strip()
            if not post_id:
                continue

            post_dir = root / post_id
            post_dir.mkdir(parents=True, exist_ok=True)
            post_media_dir = post_dir / "media"
            post_media_dir.mkdir(parents=True, exist_ok=True)

            src_images = media_dir / "images" / post_id
            if src_images.exists():
                for image_file in src_images.glob("*"):
                    shutil.copy2(image_file, post_media_dir / image_file.name)

            src_videos = media_dir / "videos" / post_id
            if src_videos.exists():
                for video_file in src_videos.glob("*"):
                    shutil.copy2(video_file, post_media_dir / video_file.name)

            post_comments = comments_by_post.get(post_id, [])
            (post_dir / "comments.json").write_text(
                json.dumps(post_comments, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

            mock_state = {
                "request_info": {
                    "post_url": f"https://www.xiaohongshu.com/explore/{post_id}",
                    "product_info": "待定",
                    "target_style": "自然安利风",
                },
                "raw_data": {
                    "post_content": data.get("desc", ""),
                    "media_paths": [str(path.resolve()) for path in post_media_dir.glob("*")],
                    "comments": post_comments,
                },
                "vision_analysis": {
                    "scene": "",
                    "vibe": "",
                    "detected_items": [],
                    "people_emotions": [],
                    "visual_highlights": [],
                    "risk_flags": [],
                    "source_media_count": 0,
                    "model_provider": "",
                    "model_name": "",
                },
                "nlp_analysis": {},
                "rag_references": [],
                "final_ads": [],
                "review_score": 0,
            }
            (post_dir / "mock_state.json").write_text(
                json.dumps(mock_state, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            logger.info("已生成 mock_state: %s", post_id)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
    if len(sys.argv) <= 1:
        logger.error("请提供 task_id")
        raise SystemExit(1)
    format_crawler_data(sys.argv[1])

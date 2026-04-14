import json
import os
import shutil
from pathlib import Path

def format_crawler_data(task_id: str):
    base_dir = Path(f"e:/AIAD/data/raw")
    content_file = base_dir / f"{task_id}_search_contents.jsonl"
    comment_file = base_dir / f"{task_id}_search_comments.jsonl"
    media_dir = base_dir / "_runs" / task_id / "xhs"
    
    if not content_file.exists():
        print(f"Content file {content_file} not found.")
        return

    # Parse comments first
    comments_by_post = {}
    if comment_file.exists():
        with open(comment_file, "r", encoding="utf-8") as f:
            for line in f:
                if not line.strip(): continue
                data = json.loads(line)
                post_id = data.get("note_id")
                if not post_id: continue
                if post_id not in comments_by_post:
                    comments_by_post[post_id] = []
                comments_by_post[post_id].append({
                    "user": data.get("nickname", "Unknown"),
                    "content": data.get("content", ""),
                    "likes": data.get("like_count", 0)
                })

    # Process each post
    with open(content_file, "r", encoding="utf-8") as f:
        for line in f:
            if not line.strip(): continue
            data = json.loads(line)
            post_id = data.get("note_id")
            if not post_id: continue
            
            # Create post directory
            post_dir = base_dir / post_id
            post_dir.mkdir(parents=True, exist_ok=True)
            
            # Copy media
            post_media_dir = post_dir / "media"
            post_media_dir.mkdir(parents=True, exist_ok=True)
            
            # MediaCrawler might save images in `images/{post_id}` or `videos/{post_id}`
            src_images = media_dir / "images" / post_id
            if src_images.exists():
                for img in src_images.glob("*"):
                    shutil.copy2(img, post_media_dir / img.name)
            
            src_videos = media_dir / "videos" / post_id
            if src_videos.exists():
                for vid in src_videos.glob("*"):
                    shutil.copy2(vid, post_media_dir / vid.name)
                    
            # Save comments
            post_comments = comments_by_post.get(post_id, [])
            with open(post_dir / "comments.json", "w", encoding="utf-8") as cf:
                json.dump(post_comments, cf, ensure_ascii=False, indent=2)
                
            # Create a mock state for this post
            mock_state = {
              "request_info": {
                "post_url": f"https://www.xiaohongshu.com/explore/{post_id}",
                "product_info": "待定",
                "target_style": "待定"
              },
              "raw_data": {
                "post_content": data.get("desc", ""),
                "media_paths": [str(p) for p in post_media_dir.glob("*")],
                "comments": post_comments
              },
              "vision_analysis": {},
              "nlp_analysis": {},
              "rag_references": [],
              "final_ads": [],
              "review_score": 0
            }
            with open(post_dir / "mock_state.json", "w", encoding="utf-8") as sf:
                json.dump(mock_state, sf, ensure_ascii=False, indent=2)
            
            print(f"Successfully formatted data for post: {post_id}")

if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        format_crawler_data(sys.argv[1])
    else:
        print("Please provide task_id")

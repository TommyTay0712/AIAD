import json
from pathlib import Path

from app.core.config import Settings
from app.services.chroma_store import ChromaStore
from app.services.normalize import normalize_dataset
from app.workflows.data_graph import run_data_workflow


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    """写入测试用JSONL文件。"""
    lines = [json.dumps(row, ensure_ascii=False) for row in rows]
    path.write_text("\n".join(lines), encoding="utf-8")


def test_data_pipeline_normalize_and_graph(tmp_path: Path) -> None:
    """验证标准化与LangGraph整理链路可正常输出。"""
    content_file = tmp_path / "search_contents_demo.jsonl"
    comment_file = tmp_path / "search_comments_demo.jsonl"
    media_root_dir = tmp_path / "media_root"
    image_dir = media_root_dir / "images" / "n1"
    image_dir.mkdir(parents=True, exist_ok=True)
    (image_dir / "beach_hat.jpg").write_bytes(b"fake-image")
    _write_jsonl(
        content_file,
        [
            {
                "note_id": "n1",
                "title": "敏感肌修护精华",
                "desc": "成分党推荐，预算友好",
                "liked_count": "1.2万",
                "comments_count": "356",
                "collected_count": "999",
                "share_count": "33",
                "nickname": "作者A",
                "url": "https://xhs.example/n1",
                "time": "2025-10-01",
            }
        ],
    )
    _write_jsonl(
        comment_file,
        [
            {
                "comment_id": "c1",
                "note_id": "n1",
                "content": "学生党觉得价格可以，效果也不错",
                "create_time": "2025-10-01 10:00:00",
                "like_count": "88",
                "ip_location": "上海",
            }
        ],
    )
    normalized = normalize_dataset(
        platform="xhs",
        source_keyword="修护,敏感肌",
        content_file=content_file,
        comment_file=comment_file,
        media_root_dir=media_root_dir,
        product_info="敏感肌修护精华",
    )
    settings = Settings(
        project_root=tmp_path,
        aiad_python_exe=Path("/usr/bin/python3"),
        media_crawler_dir=tmp_path / "vendor" / "MediaCrawler",
        crawler_output_dir=tmp_path / "data" / "raw",
        processed_output_dir=tmp_path / "data" / "processed",
        logs_dir=tmp_path / "logs",
        task_store_file=tmp_path / "data" / "tasks.json",
        chroma_persist_dir=tmp_path / "data" / "chroma",
        mediacrawler_python_exe=Path("/usr/bin/python3"),
        playwright_browsers_path=tmp_path / ".ms-playwright",
        vision_provider="mock",
        vision_model="mock-vision",
    )
    output = run_data_workflow(normalized, settings=settings)
    assert output["summary"]["content_count"] == 1
    assert output["content_table"][0]["like_count"] == 12000
    assert output["comment_table"][0]["comment_id"] == "c1"
    assert "feature_table" in output
    assert output["vision_analysis"]["source_media_count"] == 1
    assert output["vision_analysis"]["model_provider"] == "mock"


def test_data_pipeline_chromadb_persist(tmp_path: Path) -> None:
    """验证整理结果可写入 ChromaDB。"""
    payload = {
        "summary": {"platform": "xhs", "content_count": 1, "comment_count": 1, "feature_count": 1},
        "content_table": [{"platform": "xhs", "note_id": "n1", "title": "t"}],
        "comment_table": [{"platform": "xhs", "note_id": "n1", "comment_id": "c1"}],
        "feature_table": [{"platform": "xhs", "note_id": "n1", "topic_cluster": "general"}],
    }
    store = ChromaStore(tmp_path / "chroma")
    counts = store.write_task_payload("task1", payload)
    assert counts["summary_count"] == 1
    assert counts["content_count"] == 1
    assert counts["comment_count"] == 1
    assert counts["feature_count"] == 1

from pathlib import Path
from typing import Any

from app.core.config import Settings
from app.services.vision import VisionAgent


def _build_settings(tmp_path: Path, **overrides: object) -> Settings:
    payload: dict[str, Any] = {
        "project_root": tmp_path,
        "aiad_python_exe": Path("/usr/bin/python3"),
        "media_crawler_dir": tmp_path / "vendor" / "MediaCrawler",
        "crawler_output_dir": tmp_path / "data" / "raw",
        "processed_output_dir": tmp_path / "data" / "processed",
        "logs_dir": tmp_path / "logs",
        "task_store_file": tmp_path / "data" / "tasks.json",
        "chroma_persist_dir": tmp_path / "data" / "chroma",
        "mediacrawler_python_exe": Path("/usr/bin/python3"),
        "playwright_browsers_path": tmp_path / ".ms-playwright",
        "vision_provider": "mock",
        "vision_model": "mock-vision",
    }
    payload.update(overrides)
    return Settings(**payload)


def test_vision_agent_mock_analysis_for_images(tmp_path: Path) -> None:
    image_path = tmp_path / "beach_hat.jpg"
    image_path.write_bytes(b"fake-image")

    agent = VisionAgent(_build_settings(tmp_path))
    result = agent.analyze([str(image_path)])

    assert result.scene == "海边/沙滩"
    assert "帽子" in result.detected_items
    assert result.source_media_count == 1
    assert result.model_provider == "mock"


def test_vision_agent_returns_fallback_for_missing_media(tmp_path: Path) -> None:
    agent = VisionAgent(_build_settings(tmp_path))
    result = agent.analyze([str(tmp_path / "missing.png")])

    assert result.source_media_count == 0
    assert any("媒体文件不存在" in item for item in result.risk_flags)
    assert any("媒体为空" in item for item in result.risk_flags)


def test_vision_agent_video_frame_failure_uses_mock_fallback(tmp_path: Path, monkeypatch) -> None:
    video_path = tmp_path / "travel.mp4"
    video_path.write_bytes(b"fake-video")

    agent = VisionAgent(_build_settings(tmp_path))

    def _fake_extract(_: Path, __: Path) -> tuple[list[Path], list[str]]:
        return [], ["视频抽帧失败: travel.mp4"]

    monkeypatch.setattr(agent, "_extract_video_frames", _fake_extract)
    result = agent.analyze([str(video_path)])

    assert result.model_provider == "mock"
    assert any("视频抽帧失败" in item for item in result.risk_flags)


def test_vision_agent_normalizes_list_like_text_fields(tmp_path: Path) -> None:
    agent = VisionAgent(_build_settings(tmp_path))
    result = agent._normalize_analysis(
        {
            "scene": "['科幻电影宣传场景']",
            "vibe": ["神秘", "高端", "科技感"],
            "detected_items": ["宇航员头盔"],
            "people_emotions": ["专注"],
            "visual_highlights": ["头盔细节设计"],
            "risk_flags": ["广告植入明显"],
        }
    )

    assert result.scene == "科幻电影宣传场景"
    assert result.vibe == "神秘, 高端, 科技感"

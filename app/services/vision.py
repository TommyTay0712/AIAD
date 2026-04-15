from __future__ import annotations

import ast
import base64
import json
import logging
import mimetypes
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from openai import OpenAI

from app.core.config import Settings
from app.models.schemas import VisionAnalysis

logger = logging.getLogger(__name__)

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}
VIDEO_EXTENSIONS = {".mp4", ".mov", ".m4v", ".avi", ".mkv", ".webm"}


class VisionAgent:
    """多模态视觉理解智能体。"""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def analyze(self, media_paths: list[str]) -> VisionAnalysis:
        """分析媒体列表并输出结构化视觉报告。"""
        with tempfile.TemporaryDirectory(prefix="vision-agent-") as temp_dir_raw:
            temp_dir = Path(temp_dir_raw)
            prepared_media, preparation_flags = self._prepare_media_paths(media_paths, temp_dir)
            if not prepared_media:
                return self._build_mock_analysis(
                    prepared_media,
                    preparation_flags + ["未检测到可分析的本地媒体文件"],
                    reason="媒体为空，返回默认视觉分析结果",
                )

            if self._should_call_remote_model():
                try:
                    analysis = self._call_remote_model(prepared_media)
                    analysis.risk_flags = list(
                        dict.fromkeys(preparation_flags + analysis.risk_flags)
                    )
                    analysis.source_media_count = len(prepared_media)
                    analysis.model_provider = self.settings.vision_provider
                    analysis.model_name = self.settings.vision_model
                    logger.info(
                        "视觉分析完成 provider=%s model=%s media_count=%s",
                        self.settings.vision_provider,
                        self.settings.vision_model,
                        len(prepared_media),
                    )
                    return analysis
                except Exception as exc:
                    logger.error("视觉模型调用失败 error=%s", str(exc))
                    if not self.settings.vision_enable_mock_fallback:
                        raise
                    preparation_flags.append(f"远程视觉模型调用失败: {str(exc)[:160]}")

            return self._build_mock_analysis(
                prepared_media,
                preparation_flags,
                reason="未配置远程视觉模型或已启用 Mock 回退",
            )

    def _should_call_remote_model(self) -> bool:
        provider = self.settings.vision_provider.strip().lower()
        return provider not in {"", "mock"} and bool(self.settings.vision_api_key.strip())

    def _prepare_media_paths(
        self,
        media_paths: list[str],
        temp_dir: Path,
    ) -> tuple[list[Path], list[str]]:
        prepared: list[Path] = []
        risk_flags: list[str] = []
        seen: set[Path] = set()

        for raw_path in media_paths:
            path = Path(raw_path).expanduser()
            if path in seen:
                continue
            seen.add(path)
            if not path.exists() or not path.is_file():
                risk_flags.append(f"媒体文件不存在: {path.name}")
                continue

            suffix = path.suffix.lower()
            if suffix in IMAGE_EXTENSIONS:
                prepared.append(path)
            elif suffix in VIDEO_EXTENSIONS:
                frames, frame_risks = self._extract_video_frames(path, temp_dir)
                prepared.extend(frames)
                risk_flags.extend(frame_risks)
            else:
                risk_flags.append(f"跳过不支持的媒体类型: {path.name}")

            if len(prepared) >= self.settings.vision_max_media_count:
                break

        limited = prepared[: self.settings.vision_max_media_count]
        if len(prepared) > len(limited):
            risk_flags.append("媒体数量超出上限，已截断分析样本")
        return limited, list(dict.fromkeys(risk_flags))

    def _extract_video_frames(
        self,
        video_path: Path,
        temp_dir: Path,
    ) -> tuple[list[Path], list[str]]:
        risk_flags: list[str] = []
        ffmpeg = shutil.which("ffmpeg")
        if not ffmpeg:
            return [], [f"未检测到 ffmpeg，跳过视频抽帧: {video_path.name}"]

        frame_count = max(1, self.settings.vision_video_frame_sample_count)
        output_pattern = temp_dir / f"{video_path.stem}_frame_%02d.jpg"
        command = [
            ffmpeg,
            "-y",
            "-i",
            str(video_path),
            "-vf",
            f"fps={frame_count}",
            "-frames:v",
            str(frame_count),
            str(output_pattern),
        ]
        try:
            subprocess.run(command, check=True, capture_output=True, text=True)
        except subprocess.CalledProcessError as exc:
            logger.error("视频抽帧失败 video=%s error=%s", video_path, exc.stderr[-240:])
            return [], [f"视频抽帧失败: {video_path.name}"]

        frames = sorted(temp_dir.glob(f"{video_path.stem}_frame_*.jpg"))
        if not frames:
            risk_flags.append(f"视频抽帧结果为空: {video_path.name}")
        return frames[:frame_count], risk_flags

    def _call_remote_model(self, media_paths: list[Path]) -> VisionAnalysis:
        content_parts: list[dict[str, Any]] = [
            {
                "type": "text",
                "text": (
                    "请分析这些小红书帖子相关媒体，输出 JSON。"
                    "字段必须包含：scene, vibe, detected_items, people_emotions, "
                    "visual_highlights, risk_flags。所有列表字段必须是字符串数组。"
                    "请聚焦广告植入场景、商品线索、人物情绪和整体氛围。"
                ),
            }
        ]
        for media_path in media_paths:
            content_parts.append(
                {
                    "type": "image_url",
                    "image_url": {"url": self._to_data_url(media_path)},
                }
            )

        client = OpenAI(
            base_url=self.settings.vision_api_base,
            api_key=self.settings.vision_api_key,
            timeout=self.settings.vision_timeout_seconds,
        )
        messages: Any = [
            {
                "role": "system",
                "content": (
                    "你是小红书广告场景视觉分析助手。"
                    "必须仅返回合法 JSON，不要输出 Markdown 或额外解释。"
                ),
            },
            {"role": "user", "content": content_parts},
        ]
        stream = client.chat.completions.create(
            model=self.settings.vision_model,
            messages=messages,
            temperature=0.2,
            stream=True,
        )

        content = self._collect_stream_content(stream)
        payload_dict = self._parse_json_content(content)
        analysis = self._normalize_analysis(payload_dict)
        analysis.source_media_count = len(media_paths)
        return analysis

    def _collect_stream_content(self, stream: Any) -> str:
        chunks: list[str] = []
        for chunk in stream:
            if not getattr(chunk, "choices", None):
                continue
            delta = chunk.choices[0].delta
            content = getattr(delta, "content", None)
            if isinstance(content, str) and content:
                chunks.append(content)
            elif isinstance(content, list):
                for item in content:
                    if isinstance(item, dict):
                        text = item.get("text", "")
                        if text:
                            chunks.append(str(text))
        if not chunks:
            raise ValueError("视觉模型流式响应为空")
        return "".join(chunks)

    def _parse_json_content(self, content: str) -> dict[str, Any]:
        cleaned = content.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.strip("`")
            cleaned = cleaned.replace("json", "", 1).strip()
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start == -1 or end == -1 or end < start:
            raise ValueError("视觉模型未返回 JSON 对象")
        return json.loads(cleaned[start : end + 1])

    def _normalize_analysis(self, payload: dict[str, Any]) -> VisionAnalysis:
        def _normalize_text(value: Any) -> str:
            if isinstance(value, list):
                return ", ".join(str(item).strip() for item in value if str(item).strip())
            text = str(value).strip()
            if not text:
                return ""
            if text.startswith("[") and text.endswith("]"):
                try:
                    parsed = ast.literal_eval(text)
                except (SyntaxError, ValueError):
                    return text
                if isinstance(parsed, list):
                    return ", ".join(
                        str(item).strip() for item in parsed if str(item).strip()
                    )
            return text

        def _string_list(key: str) -> list[str]:
            value = payload.get(key, [])
            if isinstance(value, str):
                return [value] if value.strip() else []
            if isinstance(value, list):
                return [str(item).strip() for item in value if str(item).strip()]
            return []

        return VisionAnalysis(
            scene=_normalize_text(payload.get("scene", "")),
            vibe=_normalize_text(payload.get("vibe", "")),
            detected_items=_string_list("detected_items"),
            people_emotions=_string_list("people_emotions"),
            visual_highlights=_string_list("visual_highlights"),
            risk_flags=_string_list("risk_flags"),
        )

    def _to_data_url(self, media_path: Path) -> str:
        mime_type, _ = mimetypes.guess_type(media_path.name)
        mime_type = mime_type or "image/jpeg"
        encoded = base64.b64encode(media_path.read_bytes()).decode("utf-8")
        return f"data:{mime_type};base64,{encoded}"

    def _build_mock_analysis(
        self,
        media_paths: list[Path],
        risk_flags: list[str],
        *,
        reason: str,
    ) -> VisionAnalysis:
        names = " ".join(path.stem.lower() for path in media_paths)
        scene = "日常生活场景"
        vibe = "真实、轻松、适合自然种草"
        detected_items = ["人物", "生活用品"]
        people_emotions = ["自然", "放松"]
        visual_highlights = ["画面具备真实使用感", "适合结合体验式广告文案"]

        keyword_scene_map = {
            "beach": "海边/沙滩",
            "sea": "海边/沙滩",
            "camp": "露营/户外",
            "outdoor": "露营/户外",
            "food": "探店/美食",
            "makeup": "美妆展示",
            "skin": "护肤场景",
            "travel": "旅行记录",
        }
        keyword_item_map = {
            "hat": "帽子",
            "bag": "包袋",
            "phone": "手机",
            "lip": "口红",
            "sun": "防晒用品",
            "skin": "护肤品",
        }
        for keyword, mapped_scene in keyword_scene_map.items():
            if keyword in names:
                scene = mapped_scene
                break
        for keyword, item in keyword_item_map.items():
            if keyword in names and item not in detected_items:
                detected_items.append(item)

        if any(path.suffix.lower() in VIDEO_EXTENSIONS for path in media_paths):
            visual_highlights.append("视频帧可用于捕捉动态使用情境")
        if reason:
            risk_flags = list(dict.fromkeys(risk_flags + [reason]))

        logger.info(
            "使用Mock视觉分析 media_count=%s provider=%s",
            len(media_paths),
            self.settings.vision_provider,
        )
        return VisionAnalysis(
            scene=scene,
            vibe=vibe,
            detected_items=detected_items,
            people_emotions=people_emotions,
            visual_highlights=visual_highlights,
            risk_flags=list(dict.fromkeys(risk_flags)),
            source_media_count=len(media_paths),
            model_provider="mock"
            if self.settings.vision_provider.strip().lower() in {"", "mock"}
            else f"{self.settings.vision_provider}:mock-fallback",
            model_name=self.settings.vision_model,
        )

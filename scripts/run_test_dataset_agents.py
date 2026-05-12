from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any
from dotenv import load_dotenv

from app.core.config import get_settings
from app.models.schemas import NLPAnalysis, RawComment, RequestInfo, VisionAnalysis
from app.services.context_agent import ContextAgent
from app.services.copywriter import run_copywriter_agent
from app.services.copywriter_agent import CopywriterAgent
from app.services.llm_gateway import build_llm_gateway
from app.services.rag_agent import RagAgent
from app.services.vision import VisionAgent

logger = logging.getLogger("run_test_dataset_agents")


def setup_logging() -> None:
    """初始化日志配置。"""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )


def _safe_read_json(file_path: Path, default: Any) -> Any:
    """安全读取 JSON 文件，失败时返回默认值。"""
    try:
        return json.loads(file_path.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.error("读取 JSON 失败 file=%s error=%s", file_path, exc)
        return default


def _normalize_like_value(value: Any) -> int:
    """将点赞字段统一转为整数。"""
    try:
        return int(str(value).strip())
    except Exception:
        return 0


def _resolve_media_paths(
    raw_paths: list[str],
    note_dir: Path,
    project_root: Path,
) -> list[str]:
    """修正媒体路径，兼容 test 数据目录中的相对/绝对差异。"""
    resolved: list[str] = []
    media_dir = note_dir / "media"
    for raw_path in raw_paths:
        path = Path(str(raw_path))
        if path.exists():
            resolved.append(str(path))
            continue
        guessed = project_root / str(path).replace("e:\\AIAD\\", "").replace(
            "\\", "/"
        )
        if guessed.exists():
            resolved.append(str(guessed))
            continue
        fallback = media_dir / path.name
        if fallback.exists():
            resolved.append(str(fallback))
    # 去重，保持顺序
    deduped: list[str] = []
    seen: set[str] = set()
    for item in resolved:
        if item in seen:
            continue
        seen.add(item)
        deduped.append(item)
    return deduped


def _build_raw_comments(comments: list[dict[str, Any]]) -> list[RawComment]:
    """将 comments.json 数据转换为 Agent3 所需结构。"""
    parsed: list[RawComment] = []
    for row in comments:
        if not isinstance(row, dict):
            continue
        parsed.append(
            RawComment(
                user=str(row.get("user", "")),
                content=str(row.get("content", "")),
                likes=_normalize_like_value(row.get("likes", 0)),
            )
        )
    return parsed


def _run_single_note(
    note_dir: Path,
    project_root: Path,
) -> dict[str, Any]:
    """执行单条真实样本的 Agent2-6 处理流程。"""
    settings = get_settings()
    mock_state_path = note_dir / "mock_state.json"
    comments_path = note_dir / "comments.json"
    if not mock_state_path.exists() or not comments_path.exists():
        return {
            "note_id": note_dir.name,
            "status": "skipped",
            "error": "mock_state.json 或 comments.json 缺失",
        }

    mock_state = _safe_read_json(mock_state_path, {})
    comments_data = _safe_read_json(comments_path, [])
    request_info_raw = mock_state.get("request_info", {})
    raw_data = mock_state.get("raw_data", {})
    media_paths_raw = raw_data.get("media_paths", [])
    media_paths = _resolve_media_paths(
        media_paths_raw if isinstance(media_paths_raw, list) else [],
        note_dir,
        project_root,
    )
    comments = _build_raw_comments(comments_data if isinstance(comments_data, list) else [])
    request_info = RequestInfo(
        post_url=str(request_info_raw.get("post_url", "")),
        product_info=str(request_info_raw.get("product_info", "") or "SK-II小灯泡美白精华"),
        target_style=str(request_info_raw.get("target_style", "") or "测评风"),
    )

    vision_agent = VisionAgent(settings)
    context_agent = ContextAgent()
    rag_agent = RagAgent()
    copywriter_agent = CopywriterAgent()

    try:
        vision = vision_agent.analyze(media_paths)
        nlp = context_agent.analyze(comments, request_info.product_info)
        rag_refs = rag_agent.retrieve(vision, nlp, top_k=5)
        llm_state = {
            "request_info": request_info.model_dump(),
            "raw_data": {
                "post_content": str(raw_data.get("post_content", "")),
                "media_paths": media_paths,
                "comments": [item.model_dump() for item in comments],
            },
            "vision_analysis": vision.model_dump(),
            "nlp_analysis": nlp.model_dump(),
            "rag_references": rag_refs,
            "final_ads": [],
            "review_score": 0,
        }
        llm_output = run_copywriter_agent(
            llm_state,
            llm_gateway=build_llm_gateway(settings),
        )
        llm_ads = llm_output.get("final_ads", [])
        fallback_ads = copywriter_agent.generate(
            request_info=request_info,
            vision_analysis=VisionAnalysis.model_validate(vision),
            nlp_analysis=NLPAnalysis.model_validate(nlp),
            rag_references=rag_refs,
            styles=["测评风", "随口安利风", "科普风"],
        )
        final_ads = llm_ads if llm_ads else [item.model_dump() for item in fallback_ads]
        return {
            "note_id": note_dir.name,
            "status": "success",
            "request_info": request_info.model_dump(),
            "media_count": len(media_paths),
            "comment_count": len(comments),
            "vision_analysis": vision.model_dump(),
            "nlp_analysis": nlp.model_dump(),
            "rag_references": rag_refs,
            "final_ads": final_ads,
            "review_score": int(llm_output.get("review_score", 0) or 0),
            "llm_status": str(llm_output.get("llm_result", {}).get("status", "unknown")),
        }
    except Exception as exc:
        logger.exception("处理样本失败 note_id=%s", note_dir.name)
        return {
            "note_id": note_dir.name,
            "status": "failed",
            "error": str(exc),
        }


def run_batch(test_root: Path, limit: int = 20) -> dict[str, Any]:
    """批量执行 test 数据目录中的 Agent2-6 流程。"""
    project_root = Path(__file__).resolve().parents[1]
    note_dirs = sorted([item for item in test_root.iterdir() if item.is_dir()])[:limit]
    logger.info("开始批量测试 samples=%s path=%s", len(note_dirs), test_root)

    results: list[dict[str, Any]] = []
    for index, note_dir in enumerate(note_dirs, start=1):
        logger.info("处理第 %s/%s 条 note_id=%s", index, len(note_dirs), note_dir.name)
        results.append(_run_single_note(note_dir, project_root))

    success_count = len([item for item in results if item.get("status") == "success"])
    failed_count = len([item for item in results if item.get("status") == "failed"])
    skipped_count = len([item for item in results if item.get("status") == "skipped"])
    return {
        "summary": {
            "total": len(results),
            "success": success_count,
            "failed": failed_count,
            "skipped": skipped_count,
            "generated_at": datetime.now().isoformat(),
            "test_root": str(test_root),
        },
        "results": results,
    }


def main() -> None:
    """脚本入口：执行 test 数据批处理并落盘结果。"""
    load_dotenv()
    setup_logging()
    project_root = Path(__file__).resolve().parents[1]
    test_root = project_root / "data" / "raw" / "test"
    output_dir = project_root / "data" / "processed"
    output_dir.mkdir(parents=True, exist_ok=True)

    report = run_batch(test_root, limit=30)
    report_file = output_dir / f"test_agent_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    report_file.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info("批量测试完成 report=%s", report_file)
    logger.info("汇总信息: %s", report["summary"])


if __name__ == "__main__":
    main()

from __future__ import annotations

"""
Copywriter Service 微服务

职责：
- 软植入文案生成（Copywriter Agent）
- 单批评论回复生成（供 Task Service 逐批调用）
"""

import asyncio
import logging
from pathlib import Path
from typing import Any

from fastapi import APIRouter, FastAPI
from pydantic import BaseModel, Field

from services.shared.config import load_service_config
from services.shared.schemas import CopywriterRequest, CopywriterResult, HealthResponse

import sys
sys.path.append(str(Path(__file__).resolve().parents[2]))

from app.services.copywriter_agent import CopywriterAgent
from app.services.llm_gateway import build_llm_gateway
from app.models.schemas import RequestInfo, VisionAnalysis, NLPAnalysis
from app.core.config import get_settings

logger = logging.getLogger(__name__)

config = load_service_config("copywriter")
app = FastAPI(title="AIAD Copywriter Service", version="0.1.0")
router = APIRouter(prefix="/generate", tags=["copywriter"])


class BatchReplyRequest(BaseModel):
    task_id: str
    comments: list[dict[str, Any]] = Field(default_factory=list)
    nlp_analysis: dict[str, Any] = Field(default_factory=dict)
    request_info: dict[str, Any] = Field(default_factory=dict)
    offset: int = 0


@app.get("/health", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    return HealthResponse(service="copywriter")


@router.post("", response_model=CopywriterResult)
async def generate(request: CopywriterRequest) -> CopywriterResult:
    """生成风格文案（不含逐评论回复，由 Task Service 逐批调用 /batch_reply）。"""
    logger.info("收到文案生成任务 task_id=%s", request.task_id)
    try:
        settings = get_settings()
        gateway = build_llm_gateway(settings)
        agent = CopywriterAgent(gateway=gateway)
        ads = await asyncio.to_thread(
            agent.generate,
            request_info=RequestInfo(**request.request_info),
            vision_analysis=VisionAnalysis(**request.vision_analysis),
            nlp_analysis=NLPAnalysis(**request.nlp_analysis),
            rag_references=request.rag_references,
            styles=request.styles or None,
        )
        return CopywriterResult(
            task_id=request.task_id,
            final_ads=[{"style": d.style, "content": d.content} for d in ads],
            review_score=85,
        )
    except Exception as exc:
        logger.error("文案生成异常 task_id=%s error=%s", request.task_id, exc)
        return CopywriterResult(task_id=request.task_id)


@router.post("/batch_reply")
async def batch_reply(request: BatchReplyRequest) -> dict[str, Any]:
    """为一批评论生成个性化回复，返回 {index_str: reply_text}。"""
    logger.info("批量回复 task_id=%s offset=%s count=%s",
                request.task_id, request.offset, len(request.comments))
    try:
        settings = get_settings()
        gateway = build_llm_gateway(settings)
        agent = CopywriterAgent(gateway=gateway)
        result = await asyncio.to_thread(
            agent.batch_reply_slice,
            batch=request.comments,
            offset=request.offset,
            nlp_analysis=NLPAnalysis(**request.nlp_analysis),
            request_info=RequestInfo(**request.request_info),
        )
        return {"comment_ads": result}
    except Exception as exc:
        logger.error("批量回复异常 task_id=%s error=%s", request.task_id, exc)
        return {"comment_ads": {}}


app.include_router(router)

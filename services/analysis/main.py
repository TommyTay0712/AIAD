from __future__ import annotations

"""
Analysis Service 微服务

职责：
- 视觉理解（Vision Agent）
- 评论区语境 NLP（Context Agent）
- RAG 检索（Rag Agent）
"""

import asyncio
import logging
from pathlib import Path
from fastapi import APIRouter, FastAPI

from services.shared.config import load_service_config
from services.shared.schemas import AnalysisRequest, AnalysisResult, HealthResponse

import sys
sys.path.append(str(Path(__file__).resolve().parents[2]))

from app.models.schemas import NLPAnalysis, RawComment, VisionAnalysis
from app.services.vision import VisionAgent
from app.services.context_agent import ContextAgent
from app.services.rag_agent import RagAgent
from app.services.llm_gateway import build_llm_gateway
from app.core.config import get_settings

logger = logging.getLogger(__name__)

config = load_service_config("analysis")
app = FastAPI(title="AIAD Analysis Service", version="0.1.0")
router = APIRouter(prefix="/analyze", tags=["analysis"])


@app.get("/health", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    return HealthResponse(service="analysis")


@router.post("", response_model=AnalysisResult)
async def analyze(request: AnalysisRequest) -> AnalysisResult:
    logger.info("收到分析任务 task_id=%s", request.task_id)
    settings = get_settings()
    
    try:
        # 并发执行视觉分析和文本分析
        async def run_vision() -> VisionAnalysis:
            if not request.media_paths:
                return VisionAnalysis()
            agent = VisionAgent(settings)
            result = await asyncio.to_thread(agent.analyze, request.media_paths)
            if isinstance(result, dict):
                return VisionAnalysis(**result)
            return result

        async def run_nlp() -> NLPAnalysis:
            if not request.comments:
                return NLPAnalysis()
            gateway = build_llm_gateway(settings)
            agent = ContextAgent(gateway=gateway)
            raw_comments: list[RawComment] = []
            for c in request.comments:
                if isinstance(c, dict):
                    user_info = c.get("user_info", {})
                    user = (
                        user_info.get("nickname", "") if isinstance(user_info, dict) else ""
                    ) or c.get("user", "")
                    likes = int(c.get("liked_count", 0) or c.get("likes", 0))
                    raw_comments.append(RawComment(user=user, content=c.get("content", ""), likes=likes))
                else:
                    raw_comments.append(c)
            return await asyncio.to_thread(agent.analyze, raw_comments, request.product_info)
            
        vision_res, nlp_res = await asyncio.gather(run_vision(), run_nlp())
        
        # 串行执行 RAG
        rag_refs = []
        if vision_res or nlp_res:
            rag_agent = RagAgent()
            rag_refs = await asyncio.to_thread(rag_agent.retrieve, vision_res, nlp_res)
            
        return AnalysisResult(
            task_id=request.task_id,
            vision_analysis=vision_res.model_dump(),
            nlp_analysis=nlp_res.model_dump(),
            rag_references=rag_refs,
        )
        
    except Exception as exc:
        logger.error("分析任务异常 task_id=%s error=%s", request.task_id, exc)
        # 容错：即使部分失败也返回默认空数据，以保证流水线继续
        return AnalysisResult(task_id=request.task_id)

app.include_router(router)

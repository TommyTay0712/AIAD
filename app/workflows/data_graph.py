from __future__ import annotations

import logging
from typing import Any, Literal, TypedDict, cast

from langgraph.graph import END, START, StateGraph

from app.core.config import Settings, get_settings
from app.models.schemas import VisionAnalysis
from app.services.agent3_context_nlp import ContextNLPAgent
from app.services.copywriter import LLMGateway, run_copywriter_agent
from app.services.state_builder import build_global_state
from app.services.vision import VisionAgent

logger = logging.getLogger(__name__)


class DataState(TypedDict):
    request_info: dict[str, Any]
    raw_data: dict[str, Any]
    normalized: dict[str, Any]
    vision_analysis: dict[str, Any]
    global_state: dict[str, Any]
    output: dict[str, Any]
    llm_gateway: LLMGateway | None


def _prepare_state(state: DataState) -> DataState:
    normalized = state["normalized"]
    return {
        "request_info": state.get("request_info") or normalized.get("request_info", {}),
        "raw_data": normalized.get("raw_data", {}),
        "normalized": normalized,
        "vision_analysis": state.get("vision_analysis", {}),
        "global_state": state.get("global_state", {}),
        "output": state.get("output", {}),
        "llm_gateway": state.get("llm_gateway"),
    }


def _vision_node_factory(settings: Settings):
    agent = VisionAgent(settings)

    def _vision_node(state: DataState) -> DataState:
        media_paths = state.get("raw_data", {}).get("media_paths", [])
        analysis = agent.analyze(media_paths if isinstance(media_paths, list) else [])
        return {
            "request_info": state["request_info"],
            "raw_data": state["raw_data"],
            "normalized": state["normalized"],
            "vision_analysis": analysis.model_dump(),
            "global_state": state.get("global_state", {}),
            "output": state["output"],
            "llm_gateway": state["llm_gateway"],
        }

    return _vision_node


def _package_output(state: DataState) -> DataState:
    vision_analysis = VisionAnalysis.model_validate(state.get("vision_analysis", {})).model_dump()
    global_state = build_global_state(
        normalized=state["normalized"],
        request_info=state["request_info"],
    )
    global_state["vision_analysis"] = vision_analysis

    output = {
        "request_info": global_state["request_info"],
        "summary": state["normalized"]["summary"],
        "content_table": state["normalized"]["content_table"],
        "comment_table": state["normalized"]["comment_table"],
        "feature_table": state["normalized"]["feature_table"],
        "vision_analysis": vision_analysis,
        "global_state": global_state,
        "final_ads": global_state["final_ads"],
        "review_score": global_state["review_score"],
    }
    return {
        "request_info": state["request_info"],
        "raw_data": state["raw_data"],
        "normalized": state["normalized"],
        "vision_analysis": vision_analysis,
        "global_state": global_state,
        "output": output,
        "llm_gateway": state["llm_gateway"],
    }


def _generate_copy_prompt(state: DataState) -> DataState:
    global_state = run_copywriter_agent(
        state["global_state"],
        llm_gateway=state["llm_gateway"],
    )
    output = dict(state["output"])
    output["global_state"] = global_state
    output["prompt_bundle"] = global_state.get("prompt_bundle", {})
    output["llm_result"] = global_state.get("llm_result", {})
    output["final_ads"] = global_state.get("final_ads", [])
    output["review_score"] = global_state.get("review_score", 0)
    output["vision_analysis"] = global_state.get("vision_analysis", output.get("vision_analysis", {}))
    return {
        "request_info": state["request_info"],
        "raw_data": state["raw_data"],
        "normalized": state["normalized"],
        "vision_analysis": state["vision_analysis"],
        "global_state": global_state,
        "output": output,
        "llm_gateway": state["llm_gateway"],
    }


def run_data_workflow(
    normalized: dict[str, Any],
    request_info: dict[str, Any] | None = None,
    settings: Settings | None = None,
    llm_gateway: LLMGateway | None = None,
) -> dict[str, Any]:
    """执行基于 LangGraph 的数据整理流程。"""
    runtime_settings = settings or get_settings()
    graph = StateGraph(DataState)
    graph.add_node("prepare_state", _prepare_state)
    graph.add_node("vision_analysis", _vision_node_factory(runtime_settings))
    graph.add_node("package_output", _package_output)
    graph.add_node("generate_copy_prompt", _generate_copy_prompt)
    graph.add_edge(START, "prepare_state")
    graph.add_edge("prepare_state", "vision_analysis")
    graph.add_edge("vision_analysis", "package_output")
    graph.add_edge("package_output", "generate_copy_prompt")
    graph.add_edge("generate_copy_prompt", END)
    chain = graph.compile()
    initial_state: DataState = {
        "request_info": request_info or normalized.get("request_info", {}),
        "raw_data": normalized.get("raw_data", {}),
        "normalized": normalized,
        "vision_analysis": {},
        "global_state": {},
        "output": {},
        "llm_gateway": llm_gateway,
    }
    chain_runtime = cast(Any, chain)
    result = cast(DataState, chain_runtime.invoke(initial_state))
    return result["output"]


class AgentGraphState(TypedDict, total=False):
    """路线规划版 Agent1～5 的全局 State（占位实现）。"""

    request_id: str
    post_urls: list[str]
    options: dict[str, Any]
    product: dict[str, Any]

    # 兼容现状（可选）
    task_id: str

    # 运行态
    status: Literal["running", "success", "failed"]
    error_code: str | None
    error_message: str
    retry_count: int
    eval_score: float

    # Agent 产物
    harvest_result: dict[str, Any]
    vision_report: dict[str, Any]
    comment_context: dict[str, Any]
    rag_result: dict[str, Any]
    copy_result: dict[str, Any]


def _extract_comments_from_state(state: AgentGraphState) -> list[dict[str, Any]]:
    """从 state 中提取评论列表。"""
    # 方式1：从 harvest_result 中获取
    harvest = state.get("harvest_result", {})
    if isinstance(harvest, dict):
        comments = harvest.get("comments", [])
        if comments:
            return comments

    # 方式2：从 raw_data 中获取
    raw_data = state.get("raw_data", {})
    if isinstance(raw_data, dict):
        comments = raw_data.get("comments", [])
        if comments:
            return comments

    # 方式3：直接字段
    if "comments" in state:
        return state["comments"]

    return []


def _map_emotion_to_label(emotion_text: str) -> str:
    """中文情绪描述 -> 简短标签。"""
    text = emotion_text.lower()
    if any(w in text for w in ["积极", "正面", "兴趣", "喜欢"]):
        return "positive"
    if any(w in text for w in ["消极", "负面", "不满", "批评"]):
        return "negative"
    return "neutral"


def _placeholder_agent3_output(state: AgentGraphState) -> AgentGraphState:
    return {
        "comment_context": {
            "request_id": state.get("request_id", ""),
            "sentiment": {"label": "neutral"},
            "themes": [],
            "pain_points": [],
            "language_style": {"emoji_heavy": False},
            "ad_angle": "",
            "placeholder": True,
        }
    }


def _node_agent1_data_harvester(state: AgentGraphState) -> AgentGraphState:
    """Agent 1（占位）：数据采集与清洗。"""
    request_id = state.get("request_id", "")
    post_urls = state.get("post_urls", [])
    logger.info("Agent1 DataHarvester start request_id=%s post_urls=%s", request_id, len(post_urls))

    harvest_result = {
        "request_id": request_id,
        "posts": [],
        "errors": [],
        "harvest_meta": {"placeholder": True},
    }
    return {
        "status": "success",
        "error_code": None,
        "error_message": "",
        "harvest_result": harvest_result,
        "retry_count": int(state.get("retry_count", 0)),
    }


def _node_agent2_vision_analyst(state: AgentGraphState) -> AgentGraphState:
    """Agent 2（占位）：多模态视觉理解。"""
    logger.info("Agent2 VisionAnalyst start request_id=%s", state.get("request_id", ""))
    vision_report = {
        "request_id": state.get("request_id", ""),
        "items": [],
        "summary": "",
        "placeholder": True,
    }
    return {"vision_report": vision_report}


def _node_agent3_context_nlp(state: AgentGraphState) -> AgentGraphState:
    """Agent 3：评论区语境与情感分析（真实 LLM 调用）。"""
    request_id = state.get("request_id", "")
    logger.info("Agent3 ContextNLP start request_id=%s", request_id)

    # 提取评论
    comments = _extract_comments_from_state(state)
    if not comments:
        logger.warning("Agent3 未找到评论数据，返回占位结果")
        return _placeholder_agent3_output(state)

    # 初始化 Agent3
    settings = get_settings()
    if settings.llm_provider in ("", "disabled", "none", "null"):
        logger.warning("LLM 未配置，Agent3 使用占位输出")
        return _placeholder_agent3_output(state)

    agent = ContextNLPAgent(settings)

    try:
        analysis = agent.analyze_comments(comments)
    except Exception as e:
        logger.error("Agent3 调用失败: %s", e, exc_info=True)
        return _placeholder_agent3_output(state)

    # 映射结果
    comment_context = {
        "request_id": request_id,
        "sentiment": {"label": _map_emotion_to_label(analysis.get("main_emotion", ""))},
        "themes": analysis.get("pain_points", [])[:3],
        "pain_points": analysis.get("pain_points", []),
        "language_style": {
            "description": analysis.get("language_style", ""),
            "emoji_heavy": any(e in analysis.get("language_style", "") for e in ["emoji", "表情", "doge"]),
        },
        "ad_angle": analysis.get("best_angle_suggestion", ""),
        "placeholder": False,
    }
    return {"comment_context": comment_context}


def _node_agent4_rag_retrieve(state: AgentGraphState) -> AgentGraphState:
    """Agent 4（占位）：RAG 检索。"""
    logger.info("Agent4 RAGRetrieve start request_id=%s", state.get("request_id", ""))
    rag_result = {
        "request_id": state.get("request_id", ""),
        "retrieved": [],
        "citations": [],
        "placeholder": True,
    }
    return {"rag_result": rag_result}


def _node_agent5_copywriter(state: AgentGraphState) -> AgentGraphState:
    """Agent 5（占位）：核心文案生成。"""
    logger.info(
        "Agent5 Copywriter start request_id=%s retry_count=%s",
        state.get("request_id", ""),
        state.get("retry_count", 0),
    )
    copy_result = {
        "request_id": state.get("request_id", ""),
        "candidates": [
            {
                "candidate_id": "placeholder-001",
                "style": "测评风",
                "text": "（占位）这里将由 LLM 生成自然植入式评论。",
                "rationale": "placeholder",
            }
        ],
        "selected": None,
        "ranking": ["placeholder-001"],
        "placeholder": True,
    }
    return {"copy_result": copy_result}


def _node_eval_copy(state: AgentGraphState) -> AgentGraphState:
    """内部评估节点（占位）：给文案一个评分，触发条件路由。"""
    eval_score = float(state.get("eval_score", 0.9))
    logger.info("EvalCopy request_id=%s score=%s", state.get("request_id", ""), eval_score)
    return {"eval_score": eval_score}


def _route_after_harvest(state: AgentGraphState) -> str:
    if state.get("status") == "failed":
        return "end"
    return "fanout"


def _route_after_eval(state: AgentGraphState) -> str:
    threshold = 0.75
    max_retries = 2
    score = float(state.get("eval_score", 1.0))
    retry_count = int(state.get("retry_count", 0))
    if score < threshold and retry_count < max_retries:
        return "rewrite"
    return "end"


def build_agent_workflow() -> Any:
    """构建路线规划版 Agent1～5 的 LangGraph（真实 Agent3 已接入）。"""
    graph = StateGraph(AgentGraphState)
    graph.add_node("node_data_harvester", _node_agent1_data_harvester)
    graph.add_node("node_vision_analyst", _node_agent2_vision_analyst)
    graph.add_node("node_context_nlp", _node_agent3_context_nlp)
    graph.add_node("node_rag_retrieve", _node_agent4_rag_retrieve)
    graph.add_node("node_copywriter", _node_agent5_copywriter)
    graph.add_node("node_eval_copy", _node_eval_copy)

    graph.add_edge(START, "node_data_harvester")

    graph.add_conditional_edges(
        "node_data_harvester",
        _route_after_harvest,
        {"fanout": "node_vision_analyst", "end": END},
    )
    graph.add_edge("node_data_harvester", "node_context_nlp")

    graph.add_edge("node_vision_analyst", "node_rag_retrieve")
    graph.add_edge("node_context_nlp", "node_rag_retrieve")

    graph.add_edge("node_rag_retrieve", "node_copywriter")
    graph.add_edge("node_copywriter", "node_eval_copy")

    graph.add_conditional_edges(
        "node_eval_copy",
        _route_after_eval,
        {"rewrite": "node_copywriter", "end": END},
    )
    return graph.compile()


def run_agent_workflow(initial_state: AgentGraphState) -> AgentGraphState:
    """执行路线规划版 LangGraph。"""
    chain = cast(Any, build_agent_workflow())
    result = cast(AgentGraphState, chain.invoke(initial_state))
    return result

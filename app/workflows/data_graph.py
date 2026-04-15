from __future__ import annotations

from typing import Any, TypedDict, cast

from langgraph.graph import END, START, StateGraph

from app.core.config import Settings, get_settings
from app.models.schemas import VisionAnalysis
from app.services.vision import VisionAgent


class DataState(TypedDict):
    request_info: dict[str, Any]
    raw_data: dict[str, Any]
    normalized: dict[str, Any]
    vision_analysis: dict[str, Any]
    output: dict[str, Any]


def _prepare_state(state: DataState) -> DataState:
    normalized = state["normalized"]
    return {
        "request_info": normalized.get("request_info", {}),
        "raw_data": normalized.get("raw_data", {}),
        "normalized": normalized,
        "vision_analysis": state.get("vision_analysis", {}),
        "output": state.get("output", {}),
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
            "output": state["output"],
        }

    return _vision_node


def _package_output(state: DataState) -> DataState:
    output = {
        "summary": state["normalized"]["summary"],
        "content_table": state["normalized"]["content_table"],
        "comment_table": state["normalized"]["comment_table"],
        "feature_table": state["normalized"]["feature_table"],
        "vision_analysis": VisionAnalysis.model_validate(
            state.get("vision_analysis", {})
        ).model_dump(),
    }
    return {
        "request_info": state["request_info"],
        "raw_data": state["raw_data"],
        "normalized": state["normalized"],
        "vision_analysis": state["vision_analysis"],
        "output": output,
    }


def run_data_workflow(
    normalized: dict[str, Any],
    settings: Settings | None = None,
) -> dict[str, Any]:
    """执行基于LangGraph的数据整理流程。"""
    runtime_settings = settings or get_settings()
    graph = StateGraph(DataState)
    graph.add_node("prepare_state", _prepare_state)
    graph.add_node("vision_analysis", _vision_node_factory(runtime_settings))
    graph.add_node("package_output", _package_output)
    graph.add_edge(START, "prepare_state")
    graph.add_edge("prepare_state", "vision_analysis")
    graph.add_edge("vision_analysis", "package_output")
    graph.add_edge("package_output", END)
    chain = graph.compile()
    initial_state: DataState = {
        "request_info": normalized.get("request_info", {}),
        "raw_data": normalized.get("raw_data", {}),
        "normalized": normalized,
        "vision_analysis": {},
        "output": {},
    }
    chain_runtime = cast(Any, chain)
    result = cast(DataState, chain_runtime.invoke(initial_state))
    return result["output"]

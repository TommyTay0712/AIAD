from __future__ import annotations

from typing import Any, TypedDict, cast

from langgraph.graph import END, START, StateGraph

from app.services.copywriter import LLMGateway, run_copywriter_agent
from app.services.state_builder import build_global_state


class DataState(TypedDict):
    request_info: dict[str, Any]
    normalized: dict[str, Any]
    global_state: dict[str, Any]
    output: dict[str, Any]
    llm_gateway: LLMGateway | None


def _package_output(state: DataState) -> DataState:
    global_state = build_global_state(
        normalized=state["normalized"],
        request_info=state["request_info"],
    )
    output = {
        "request_info": global_state["request_info"],
        "summary": state["normalized"]["summary"],
        "content_table": state["normalized"]["content_table"],
        "comment_table": state["normalized"]["comment_table"],
        "feature_table": state["normalized"]["feature_table"],
        "global_state": global_state,
        "final_ads": global_state["final_ads"],
        "review_score": global_state["review_score"],
    }
    return {
        "request_info": state["request_info"],
        "normalized": state["normalized"],
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
    return {
        "request_info": state["request_info"],
        "normalized": state["normalized"],
        "global_state": global_state,
        "output": output,
        "llm_gateway": state["llm_gateway"],
    }


def run_data_workflow(
    normalized: dict[str, Any],
    request_info: dict[str, Any],
    llm_gateway: LLMGateway | None = None,
) -> dict[str, Any]:
    """执行基于LangGraph的数据整理流程。"""
    graph = StateGraph(DataState)
    graph.add_node("package_output", _package_output)
    graph.add_node("generate_copy_prompt", _generate_copy_prompt)
    graph.add_edge(START, "package_output")
    graph.add_edge("package_output", "generate_copy_prompt")
    graph.add_edge("generate_copy_prompt", END)
    chain = graph.compile()
    initial_state: DataState = {
        "request_info": request_info,
        "normalized": normalized,
        "global_state": {},
        "output": {},
        "llm_gateway": llm_gateway,
    }
    chain_runtime = cast(Any, chain)
    result = cast(DataState, chain_runtime.invoke(initial_state))
    return result["output"]

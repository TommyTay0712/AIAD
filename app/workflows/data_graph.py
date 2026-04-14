from __future__ import annotations

from typing import Any, TypedDict, cast

from langgraph.graph import END, START, StateGraph

from app.services.copywriter import build_agent5_output


class DataState(TypedDict):
    ad_type: str
    normalized: dict[str, Any]
    output: dict[str, Any]


def _package_output(state: DataState) -> DataState:
    output = {
        "summary": state["normalized"]["summary"],
        "content_table": state["normalized"]["content_table"],
        "comment_table": state["normalized"]["comment_table"],
        "feature_table": state["normalized"]["feature_table"],
    }
    return {"ad_type": state["ad_type"], "normalized": state["normalized"], "output": output}


def _generate_copy_prompt(state: DataState) -> DataState:
    output = dict(state["output"])
    output.update(build_agent5_output(state["ad_type"], output))
    return {"ad_type": state["ad_type"], "normalized": state["normalized"], "output": output}


def run_data_workflow(normalized: dict[str, Any], ad_type: str) -> dict[str, Any]:
    """执行基于LangGraph的数据整理流程。"""
    graph = StateGraph(DataState)
    graph.add_node("package_output", _package_output)
    graph.add_node("generate_copy_prompt", _generate_copy_prompt)
    graph.add_edge(START, "package_output")
    graph.add_edge("package_output", "generate_copy_prompt")
    graph.add_edge("generate_copy_prompt", END)
    chain = graph.compile()
    initial_state: DataState = {"ad_type": ad_type, "normalized": normalized, "output": {}}
    chain_runtime = cast(Any, chain)
    result = cast(DataState, chain_runtime.invoke(initial_state))
    return result["output"]

from __future__ import annotations

from typing import Any, TypedDict, cast

from langgraph.graph import END, START, StateGraph


class DataState(TypedDict):
    normalized: dict[str, Any]
    output: dict[str, Any]


def _package_output(state: DataState) -> DataState:
    output = {
        "summary": state["normalized"]["summary"],
        "content_table": state["normalized"]["content_table"],
        "comment_table": state["normalized"]["comment_table"],
        "feature_table": state["normalized"]["feature_table"],
    }
    return {"normalized": state["normalized"], "output": output}


def run_data_workflow(normalized: dict[str, Any]) -> dict[str, Any]:
    """执行基于LangGraph的数据整理流程。"""
    graph = StateGraph(DataState)
    graph.add_node("package_output", _package_output)
    graph.add_edge(START, "package_output")
    graph.add_edge("package_output", END)
    chain = graph.compile()
    initial_state: DataState = {"normalized": normalized, "output": {}}
    chain_runtime = cast(Any, chain)
    result = cast(DataState, chain_runtime.invoke(initial_state))
    return result["output"]

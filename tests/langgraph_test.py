from __future__ import annotations

from typing import Any, cast

from app.workflows.data_graph import AgentGraphState, build_agent_workflow


def test_build_agent_workflow_runs_and_returns_required_fields() -> None:
    """验证 build_agent_workflow() 可编译并跑通占位链路。"""

    chain = cast(Any, build_agent_workflow())
    initial_state: AgentGraphState = {
        "request_id": "req-test-001",
        "post_urls": ["https://xhs.example/post/1"],
        "options": {"enable_media_download": False},
        "product": {"name": "示例产品", "selling_points": ["卖点A", "卖点B"]},
        "retry_count": 0,
        # 默认高分，不触发重写
        "eval_score": 0.9,
    }

    result = cast(dict[str, Any], chain.invoke(initial_state))

    # Agent1
    assert result.get("status") == "success"
    assert "harvest_result" in result

    # Agent2/3 -> Agent4
    assert "vision_report" in result
    assert "comment_context" in result
    assert "rag_result" in result

    # Agent5 + eval
    assert "copy_result" in result
    assert "eval_score" in result
    assert float(result["eval_score"]) >= 0.0

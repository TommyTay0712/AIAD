from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

# 修正：当前文件在 tests/context_nlp/ 下，需要向上两级到达项目根目录
project_root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(project_root))

from app.core.config import get_settings
from app.services.agent3_context_nlp import ContextNLPAgent


@pytest.fixture(scope="module")
def nlp_agent():
    """初始化 Agent3 实例，复用项目配置。"""
    settings = get_settings()
    if settings.llm_provider in ("", "disabled", "none", "null"):
        pytest.skip("LLM 未配置，跳过 Agent3 测试")
    return ContextNLPAgent(settings)


def load_fixture(filename: str) -> dict | list:
    """加载 fixtures 目录下的 JSON 测试数据。"""
    # fixtures 目录与测试文件同级，即 tests/context_nlp/fixtures/
    fixture_path = Path(__file__).parent / "fixtures" / filename
    if not fixture_path.exists():
        raise FileNotFoundError(f"测试数据文件不存在: {fixture_path}")
    with open(fixture_path, "r", encoding="utf-8") as f:
        return json.load(f)


def test_agent3_with_comments_json(nlp_agent):
    comments = load_fixture("comments.json")
    assert isinstance(comments, list)
    assert len(comments) > 0
    result = nlp_agent.analyze_comments(comments)
    assert "main_emotion" in result
    assert "pain_points" in result
    assert "language_style" in result
    print("\n✅ Agent3 分析结果（comments.json）:")
    print(json.dumps(result, ensure_ascii=False, indent=2))


def test_agent3_with_mock_state(nlp_agent):
    state = load_fixture("mock_state.json")
    comments = state.get("raw_data", {}).get("comments", [])
    assert len(comments) > 0
    result = nlp_agent.analyze_comments(comments)
    assert "main_emotion" in result
    print("\n✅ Agent3 分析结果（mock_state.json）:")
    print(json.dumps(result, ensure_ascii=False, indent=2))


def test_agent3_empty_comments(nlp_agent):
    result = nlp_agent.analyze_comments([])
    assert result["main_emotion"] == "中性讨论"
    assert result["pain_points"] == ["需求待挖掘"]
    assert result["language_style"] == "日常交流"


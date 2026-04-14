from app.services.copywriter import (
    build_agent5_output,
    build_copywriter_context,
    build_generation_prompts,
)


def test_copywriter_build_context() -> None:
    payload = {
        "content_table": [{"title": "敏感肌通勤护肤", "desc": "最近换季有点泛红"}],
        "feature_table": [
            {
                "ad_fit_score": 1.2,
                "audience_profile": "学生党",
                "topic_cluster": "beauty_care",
                "pain_points": ["低敏诉求", "价格敏感"],
                "intent_labels": ["成分", "场景"],
                "risk_flags": ["合规表述风险"],
            }
        ],
    }
    context = build_copywriter_context("修护精华", payload)
    assert context["ad_type"] == "修护精华"
    assert context["audience"] == "学生党"
    assert context["pain_points"][0] == "低敏诉求"
    assert context["intent_labels"][0] == "成分"


def test_copywriter_build_agent5_output_default_llm_placeholder() -> None:
    payload = {
        "content_table": [{"title": "敏感肌通勤护肤", "desc": "最近换季有点泛红"}],
        "feature_table": [
            {
                "ad_fit_score": 1.2,
                "audience_profile": "学生党",
                "topic_cluster": "beauty_care",
                "pain_points": ["低敏诉求", "价格敏感"],
                "intent_labels": ["成分", "场景"],
                "risk_flags": [],
            }
        ],
    }
    output = build_agent5_output("修护精华", payload)
    assert output["copywriter_context"]["ad_type"] == "修护精华"
    assert output["prompt_bundle"]["prompt_version"] == "agent5-v3"
    assert output["llm_result"]["status"] == "not_configured"
    assert output["copy_candidates"] == []


def test_copywriter_build_generation_prompts() -> None:
    context = {
        "ad_type": "修护精华",
        "audience": "学生党",
        "topic_cluster": "beauty_care",
        "pain_points": ["低敏诉求", "价格敏感"],
        "intent_labels": ["成分", "场景"],
        "risk_flags": ["合规表述风险"],
        "scene_hint": "敏感肌通勤护肤",
    }
    prompts = build_generation_prompts(context)
    assert "结构化 JSON 数组" in prompts["system_prompt"]
    assert "<example>" in prompts["system_prompt"]
    assert "生成 6 条不同风格" in prompts["user_prompt"]
    assert "不要出现购买链接" in prompts["user_prompt"]
    assert prompts["prompt_version"] == "agent5-v3"


class _FakeLLMGateway:
    def generate(self, prompt_bundle: dict[str, str]) -> dict[str, object]:
        return {
            "status": "success",
            "provider": "mock",
            "model": "fake-model",
            "copy_candidates": [
                {
                    "style": "测评风",
                    "ad_text": "这是一条模型输出的测试文案。",
                    "reason": "测试",
                    "risk_flags": [],
                }
            ],
            "raw_response": "{\"ok\": true}",
            "message": "mock success",
            "prompt_version": prompt_bundle["prompt_version"],
        }


def test_copywriter_build_agent5_output_with_fake_llm() -> None:
    payload = {
        "content_table": [{"title": "敏感肌通勤护肤", "desc": "最近换季有点泛红"}],
        "feature_table": [
            {
                "ad_fit_score": 1.2,
                "audience_profile": "学生党",
                "topic_cluster": "beauty_care",
                "pain_points": ["低敏诉求", "价格敏感"],
                "intent_labels": ["成分", "场景"],
                "risk_flags": [],
            }
        ],
    }
    output = build_agent5_output("修护精华", payload, llm_gateway=_FakeLLMGateway())
    assert output["llm_result"]["status"] == "success"
    assert output["llm_result"]["provider"] == "mock"
    assert len(output["copy_candidates"]) == 1
    assert output["copy_candidates"][0]["style"] == "测评风"

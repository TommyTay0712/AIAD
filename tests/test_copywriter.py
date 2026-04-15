from app.services.copywriter import (
    build_copywriter_context,
    build_generation_prompts,
    run_copywriter_agent,
)


def _mock_state() -> dict:
    return {
        "request_info": {
            "post_url": "https://www.xiaohongshu.com/explore/xxxx",
            "product_info": "蕉下防晒霜，特点：水润不假白，适合敏感肌",
            "target_style": "测评风",
        },
        "raw_data": {
            "post_content": "今天去海边玩啦，太阳好大，想找个温和点的防晒。",
            "media_paths": ["./data/raw/xxxx/media/1.jpg"],
            "comments": [{"user": "A", "content": "求博主的防晒！", "likes": 120}],
        },
        "vision_analysis": {
            "scene": "海边/沙滩",
            "vibe": "轻松/夏日/度假",
            "detected_items": ["草帽", "墨镜"],
        },
        "nlp_analysis": {
            "main_emotion": "积极，对防晒产品有强需求",
            "pain_points": ["怕晒黑", "需要海边适用的高倍防晒"],
            "language_style": "带大量Emoji，网感强",
        },
        "rag_references": [
            "姐妹们听我的，海边一定要带这款防晒，我涂了完全没黑！",
            "这个场景绝了，顺便安利一个我空管无数次的防晒霜~",
        ],
        "final_ads": [],
        "review_score": 0,
    }


def test_copywriter_build_context() -> None:
    context = build_copywriter_context(_mock_state())
    assert context["product_info"].startswith("蕉下防晒霜")
    assert context["scene"] == "海边/沙滩"
    assert context["pain_points"][0] == "怕晒黑"
    assert context["language_style"] == "带大量Emoji，网感强"


def test_copywriter_run_agent_default_llm_placeholder() -> None:
    state = run_copywriter_agent(_mock_state())
    assert state["prompt_bundle"]["prompt_version"] == "agent5-v4"
    assert state["llm_result"]["status"] == "not_configured"
    assert state["final_ads"] == []
    assert state["review_score"] == 0


def test_copywriter_build_generation_prompts() -> None:
    context = build_copywriter_context(_mock_state())
    prompts = build_generation_prompts(context)
    assert "style、content" in prompts["system_prompt"]
    assert "<example>" in prompts["system_prompt"]
    assert "生成 3 条以上不同风格" in prompts["user_prompt"]
    assert "不要出现购买链接" in prompts["user_prompt"]
    assert prompts["prompt_version"] == "agent5-v4"


class _FakeLLMGateway:
    def generate(self, prompt_bundle: dict[str, str]) -> dict[str, object]:
        return {
            "status": "success",
            "provider": "mock",
            "model": "fake-model",
            "final_ads": [
                {
                    "style": "测评风",
                    "content": "这是一条模型输出的测试文案。",
                }
            ],
            "raw_response": "{\"ok\": true}",
            "message": "mock success",
            "prompt_version": prompt_bundle["prompt_version"],
            "review_score": 90,
        }


def test_copywriter_run_agent_with_fake_llm() -> None:
    state = run_copywriter_agent(_mock_state(), llm_gateway=_FakeLLMGateway())
    assert state["llm_result"]["status"] == "success"
    assert state["llm_result"]["provider"] == "mock"
    assert len(state["final_ads"]) == 1
    assert state["final_ads"][0]["style"] == "测评风"
    assert state["review_score"] == 90

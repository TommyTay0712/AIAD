import httpx

from app.core.config import Settings
from app.services.llm_gateway import OpenAICompatibleGateway, build_llm_gateway


def test_build_llm_gateway_disabled() -> None:
    settings = Settings(llm_provider="disabled")
    gateway = build_llm_gateway(settings)
    assert gateway is None


def test_build_llm_gateway_enabled() -> None:
    settings = Settings(
        llm_provider="local",
        llm_base_url="http://127.0.0.1:11434/v1",
        llm_model="qwen2.5:3b-instruct",
        llm_api_key="local-dev",
    )
    gateway = build_llm_gateway(settings)
    assert gateway is not None
    assert gateway.provider == "local"
    assert gateway.model == "qwen2.5:3b-instruct"


def test_openai_compatible_gateway_parse_final_ads() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/chat/completions")
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": (
                                '[{"style":"测评风","content":"海边这种场景我会更看重防晒的肤感和稳定性。"}]'
                            )
                        }
                    }
                ]
            },
        )

    transport = httpx.MockTransport(handler)
    gateway = OpenAICompatibleGateway(
        base_url="http://127.0.0.1:11434/v1",
        model="qwen2.5:3b-instruct",
        api_key="local-dev",
        timeout_seconds=30,
        temperature=0.7,
        max_tokens=1200,
        provider="local",
        transport=transport,
    )
    result = gateway.generate(
        {
            "prompt_version": "agent5-v4",
            "system_prompt": "sys",
            "user_prompt": "usr",
        }
    )
    assert result["status"] == "success"
    assert result["provider"] == "local"
    assert result["final_ads"][0]["style"] == "测评风"


def test_openai_compatible_gateway_parse_wrapped_json() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": (
                                '```json\n{"final_ads":[{"style":"随口安利风","content":"这条更像朋友安利。"}],"review_score":88}\n```'
                            )
                        }
                    }
                ]
            },
        )

    transport = httpx.MockTransport(handler)
    gateway = OpenAICompatibleGateway(
        base_url="http://127.0.0.1:11434/v1",
        model="qwen2.5:3b-instruct",
        api_key="local-dev",
        timeout_seconds=30,
        temperature=0.7,
        max_tokens=1200,
        provider="local",
        transport=transport,
    )
    result = gateway.generate(
        {
            "prompt_version": "agent5-v4",
            "system_prompt": "sys",
            "user_prompt": "usr",
        }
    )
    assert result["status"] == "success"
    assert result["final_ads"][0]["style"] == "随口安利风"
    assert result["review_score"] == 88

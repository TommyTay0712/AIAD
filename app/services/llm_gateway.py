from __future__ import annotations

import json
import logging
import re
import time
from typing import Any

import httpx

from app.core.config import Settings

logger = logging.getLogger(__name__)


def _strip_code_fence(text: str) -> str:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    return cleaned.strip()


def _extract_json_payload(text: str) -> Any:
    cleaned = _strip_code_fence(text)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass

    decoder = json.JSONDecoder()
    index = 0
    values: list[Any] = []
    while index < len(cleaned):
        while index < len(cleaned) and cleaned[index].isspace():
            index += 1
        if index >= len(cleaned):
            break
        try:
            value, end = decoder.raw_decode(cleaned, index)
        except json.JSONDecodeError:
            values = []
            break
        values.append(value)
        index = end
    if values:
        return values if len(values) > 1 else values[0]


    array_match = re.search(r"(\[[\s\S]*\])", cleaned)
    if array_match:
        candidate = array_match.group(1)
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            pass
    object_match = re.search(r"(\{[\s\S]*\})", cleaned)
    if object_match:
        candidate = object_match.group(1)
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            pass
    raise ValueError("LLM 输出中未提取到有效 JSON")


def _normalize_ad_item(item: dict[str, Any]) -> dict[str, str] | None:
    style = str(item.get("style", "")).strip()
    content = str(item.get("content") or item.get("ad_text") or "").strip()
    if not style or not content:
        return None
    return {"style": style, "content": content}


def _normalize_final_ads(payload: Any) -> list[dict[str, str]]:
    if isinstance(payload, (list, tuple)):
        normalized: list[dict[str, str]] = []
        for item in payload:
            if isinstance(item, dict):
                ad_item = _normalize_ad_item(item)
                if ad_item:
                    normalized.append(ad_item)
            elif isinstance(item, (list, tuple, dict)):
                normalized.extend(_normalize_final_ads(item))
        return normalized

    if isinstance(payload, dict):
        for key in ("final_ads", "ads", "items", "results"):
            if key in payload:
                return _normalize_final_ads(payload[key])

    return []


class OpenAICompatibleGateway:
    """调用本地或远端 OpenAI 兼容接口。"""

    def __init__(
        self,
        *,
        base_url: str,
        model: str,
        api_key: str,
        timeout_seconds: int,
        temperature: float,
        max_tokens: int,
        provider: str = "openai-compatible",
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.api_key = api_key
        self.timeout_seconds = timeout_seconds
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.provider = provider
        self._transport = transport

    def _post_with_retry(self, request_payload: dict[str, Any]) -> Any:
        """发送请求，遇到限流（choices=null）自动重试，最多 3 次，指数退避。"""
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        max_retries = 3
        for attempt in range(max_retries):
            with httpx.Client(timeout=self.timeout_seconds, transport=self._transport) as client:
                response = client.post(
                    f"{self.base_url}/chat/completions",
                    json=request_payload,
                    headers=headers,
                )
                response.raise_for_status()
            payload = response.json()
            choices = payload.get("choices")
            if choices:  # 正常响应
                return payload
            # choices 为 null/[] 视为限流，等待后重试
            wait = 2 ** attempt * 5  # 5s, 10s, 20s
            logger.warning(
                "LLM 返回空 choices（疑似限流），第 %d/%d 次重试，等待 %ds",
                attempt + 1, max_retries, wait,
            )
            if attempt < max_retries - 1:
                time.sleep(wait)
        return payload  # 最后一次结果，调用方判断

    def chat(self, system_prompt: str, user_prompt: str) -> str:
        """通用 LLM 调用，返回原始输出文本（不做 final_ads 解析）。"""
        request_payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
        }
        try:
            payload = self._post_with_retry(request_payload)
            choices = payload.get("choices") or []
            if not choices:
                logger.error("LLM chat 重试后仍返回空 choices model=%s", self.model)
                return ""
            return choices[0].get("message", {}).get("content", "")
        except Exception as exc:
            logger.error("LLM chat 请求失败 model=%s error=%s", self.model, exc)
            return ""

    def generate(self, prompt_bundle: dict[str, Any]) -> dict[str, Any]:
        request_payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": prompt_bundle["system_prompt"]},
                {"role": "user", "content": prompt_bundle["user_prompt"]},
            ],
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
        }
        try:
            payload = self._post_with_retry(request_payload)
        except httpx.HTTPError as exc:
            logger.error(
                "LLM HTTP 请求失败 provider=%s model=%s prompt_version=%s error=%s",
                self.provider,
                self.model,
                prompt_bundle.get("prompt_version", ""),
                str(exc),
            )
            return {
                "status": "error",
                "provider": self.provider,
                "model": self.model,
                "final_ads": [],
                "raw_response": "",
                "message": f"LLM 请求失败: {exc}",
                "prompt_version": prompt_bundle.get("prompt_version", ""),
                "review_score": 0,
            }

        raw_response = json.dumps(payload)
        try:
            choices = payload.get("choices")
            if not choices or not isinstance(choices, list):
                raise ValueError(f"无效的 choices 结构: {payload}")
            
            content = (
                choices[0]
                .get("message", {})
                .get("content", "")
            )
            parsed = _extract_json_payload(content)
            final_ads = _normalize_final_ads(parsed)
            review_score = 0
            if isinstance(parsed, dict):
                review_score = int(parsed.get("review_score", 0) or 0)
            status = "success" if final_ads else "empty"
            message = "LLM 生成成功" if final_ads else "LLM 已返回，但未解析出 final_ads"
            return {
                "status": status,
                "provider": self.provider,
                "model": self.model,
                "final_ads": final_ads,
                "raw_response": raw_response,
                "message": message,
                "prompt_version": prompt_bundle.get("prompt_version", ""),
                "review_score": review_score,
            }
        except (ValueError, json.JSONDecodeError, KeyError, IndexError) as exc:
            return {
                "status": "parse_error",
                "provider": self.provider,
                "model": self.model,
                "final_ads": [],
                "raw_response": raw_response,
                "message": f"LLM 返回解析失败: {exc}",
                "prompt_version": prompt_bundle.get("prompt_version", ""),
                "review_score": 0,
            }


def build_llm_gateway(settings: Settings) -> OpenAICompatibleGateway | None:
    provider = settings.llm_provider.strip().lower()
    if provider in {"", "disabled", "none", "null"}:
        return None
    if not settings.llm_api_key.strip():
        return None
    return OpenAICompatibleGateway(
        base_url=settings.llm_base_url,
        model=settings.llm_model,
        api_key=settings.llm_api_key,
        timeout_seconds=settings.llm_timeout_seconds,
        temperature=settings.llm_temperature,
        max_tokens=settings.llm_max_tokens,
        provider=provider,
    )

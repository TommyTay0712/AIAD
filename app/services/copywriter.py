from __future__ import annotations

from collections import Counter
from typing import Any, Protocol

STYLE_GUIDES = [
    {
        "style": "测评风",
        "tone": "理性、像真实体验总结",
        "instruction": "围绕使用体验、适配场景和长期感受来写，避免硬性推销。",
    },
    {
        "style": "随口安利风",
        "tone": "自然、像朋友顺手推荐",
        "instruction": "用轻松口语表达，像顺手分享，不要像销售话术。",
    },
    {
        "style": "科普风",
        "tone": "克制、像懂行用户解释选择逻辑",
        "instruction": "先解释怎么选，再自然带出产品方向，强调客观建议。",
    },
    {
        "style": "痛点回应风",
        "tone": "针对问题、先共情再建议",
        "instruction": "先接住用户顾虑，再给低压迫感建议，减少营销感。",
    },
    {
        "style": "情绪共鸣风",
        "tone": "有代入感、强调感受和情绪",
        "instruction": "多写真实困扰和改善后的轻松感，但避免夸张承诺。",
    },
    {
        "style": "问答解惑风",
        "tone": "像在评论区回复提问",
        "instruction": "用一问一答或解释口吻，优先回答高频疑问。",
    },
]

FEW_SHOT_EXAMPLES = [
    {
        "input": {
            "style": "测评风",
            "pain_point": "低敏诉求",
            "intent": "成分",
            "ad_type": "修护精华",
        },
        "output": "我自己更看重修护精华的温和度和持续使用感，尤其是有低敏诉求的时候，先看成分逻辑和肤感，反而比单看宣传词更有参考价值。",
    },
    {
        "input": {
            "style": "随口安利风",
            "pain_point": "价格敏感",
            "intent": "场景",
            "ad_type": "防晒",
        },
        "output": "如果你也是通勤随手补防晒那种，其实可以看看这种更轻一点的，价格也没那么有压力，日常带着补涂会顺手很多。",
    },
]


class LLMGateway(Protocol):
    """真实 LLM 接入协议，占位阶段只约束输入输出形状。"""

    def generate(self, prompt_bundle: dict[str, Any]) -> dict[str, Any]:
        ...


class NullLLMGateway:
    """默认空实现：不调用模型，只返回占位结果。"""

    def generate(self, prompt_bundle: dict[str, Any]) -> dict[str, Any]:
        return {
            "status": "not_configured",
            "provider": "",
            "model": "",
            "copy_candidates": [],
            "raw_response": "",
            "message": "LLM 接口已预留，当前未配置真实模型。",
            "prompt_version": prompt_bundle.get("prompt_version", ""),
        }


def _pick_primary_feature(feature_table: list[dict[str, Any]]) -> dict[str, Any]:
    if not feature_table:
        return {}
    return max(feature_table, key=lambda item: float(item.get("ad_fit_score", 0)))


def _collect_top_labels(feature_table: list[dict[str, Any]], field: str, limit: int = 3) -> list[str]:
    values: list[str] = []
    for row in feature_table:
        raw = row.get(field, [])
        if isinstance(raw, list):
            values.extend(str(item).strip() for item in raw if str(item).strip())
        elif raw:
            values.append(str(raw).strip())
    return [item for item, _ in Counter(values).most_common(limit)]


def _collect_scene_hint(content_table: list[dict[str, Any]]) -> str:
    for row in content_table:
        combined = " ".join([str(row.get("title", "")), str(row.get("desc", ""))]).strip()
        if combined:
            return combined[:36]
    return "日常使用场景"


def build_copywriter_context(ad_type: str, payload: dict[str, Any]) -> dict[str, Any]:
    """从现有结构化数据中整理文案生成所需上下文。"""
    feature_table = payload.get("feature_table", [])
    content_table = payload.get("content_table", [])
    primary = _pick_primary_feature(feature_table)
    pain_points = _collect_top_labels(feature_table, "pain_points")
    intents = _collect_top_labels(feature_table, "intent_labels")
    risks = _collect_top_labels(feature_table, "risk_flags")
    audience = str(primary.get("audience_profile") or "泛人群")
    topic = str(primary.get("topic_cluster") or "general")
    scene_hint = _collect_scene_hint(content_table)
    return {
        "ad_type": ad_type.strip(),
        "audience": audience,
        "topic_cluster": topic,
        "pain_points": pain_points or ["需求待挖掘"],
        "intent_labels": intents or ["场景"],
        "risk_flags": risks,
        "scene_hint": scene_hint,
    }


def build_generation_prompts(context: dict[str, Any]) -> dict[str, str]:
    """构造供真实 LLM 使用的 system/user prompt。"""
    style_block = "\n".join(
        f"- {item['style']}：{item['tone']}；要求：{item['instruction']}" for item in STYLE_GUIDES
    )
    example_block = "\n".join(
        [
            (
                f"<example>\n"
                f"<input>{example['input']}</input>\n"
                f"<output>{example['output']}</output>\n"
                f"</example>"
            )
            for example in FEW_SHOT_EXAMPLES
        ]
    )
    system_prompt = f"""
你是一个资深的小红书评论区软植入文案助手。

你的目标不是写“广告”，而是写“像真实用户会发的评论”。
你必须优先满足以下要求：
1. 先回应用户语境，再自然带出产品方向。
2. 文风要像评论区真人，不要像电商 banner 或促销短信。
3. 避免绝对化、医疗化、虚假承诺、夸张效果。
4. 输出必须是结构化 JSON 数组，每个元素包含 style、ad_text、reason、risk_flags。
5. 每条 ad_text 长度控制在 40-90 字，尽量一句到两句。
6. 优先使用“个人体验”“更适合”“可以先看”这类低压迫表达，不要使用“必须买”“闭眼入”“根治”等强推表达。

可选风格：
{style_block}

下面是风格参考示例：
{example_block}

如果输入信息不足，不要编造细节，用保守表达生成。
""".strip()

    user_prompt = f"""
请根据以下上下文，生成 {len(STYLE_GUIDES)} 条不同风格的小红书评论区候选文案。

### 上下文
- 产品类型: {context['ad_type']}
- 受众画像: {context['audience']}
- 场景线索: {context['scene_hint']}
- 主题簇: {context['topic_cluster']}
- 主要痛点: {", ".join(context['pain_points'])}
- 主要意图: {", ".join(context['intent_labels'])}
- 风险提示: {", ".join(context['risk_flags']) if context['risk_flags'] else "无显著风险"}

### 输出要求
- 每条风格不同，避免改几个词重复表达
- 优先写“真实体验细节、选择逻辑、低压迫建议”
- 不要出现购买链接、私信引导、联系方式
- 不要写得像官方客服
""".strip()
    return {
        "prompt_version": "agent5-v3",
        "style_guides": STYLE_GUIDES,
        "few_shot_examples": FEW_SHOT_EXAMPLES,
        "expected_output_schema": {
            "type": "json_array",
            "fields": ["style", "ad_text", "reason", "risk_flags"],
        },
        "system_prompt": system_prompt,
        "user_prompt": user_prompt,
    }


def call_llm_with_reserved_interface(
    prompt_bundle: dict[str, Any],
    llm_gateway: LLMGateway | None = None,
) -> dict[str, Any]:
    """通过预留接口调用模型；未配置时返回占位结果。"""
    gateway = llm_gateway or NullLLMGateway()
    result = gateway.generate(prompt_bundle)
    # 统一保底字段，便于前端后续直接消费。
    return {
        "status": str(result.get("status", "unknown")),
        "provider": str(result.get("provider", "")),
        "model": str(result.get("model", "")),
        "copy_candidates": result.get("copy_candidates", []),
        "raw_response": str(result.get("raw_response", "")),
        "message": str(result.get("message", "")),
        "prompt_version": str(
            result.get("prompt_version", prompt_bundle.get("prompt_version", ""))
        ),
    }


def build_agent5_output(
    ad_type: str,
    payload: dict[str, Any],
    llm_gateway: LLMGateway | None = None,
) -> dict[str, Any]:
    """生成 Agent 5 输出：当前以 Prompt 为主，并预留 LLM 输出通道。"""
    context = build_copywriter_context(ad_type, payload)
    prompt_bundle = build_generation_prompts(context)
    llm_result = call_llm_with_reserved_interface(prompt_bundle, llm_gateway=llm_gateway)
    copy_candidates = llm_result.get("copy_candidates", [])
    return {
        "copywriter_context": context,
        "prompt_bundle": prompt_bundle,
        "llm_result": llm_result,
        "copy_candidates": copy_candidates if isinstance(copy_candidates, list) else [],
    }

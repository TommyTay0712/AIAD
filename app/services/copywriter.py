from __future__ import annotations

import json
import re
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
            "scene": "海边/沙滩",
            "product_info": "蕉下防晒霜，特点：水润不假白，适合敏感肌",
        },
        "output": {"style": "测评风", "content": "海边这种场景我会更看重防晒的肤感和稳定性，这类水润不假白、敏感肌也能安心用的方向会更值得先看。"},
    },
    {
        "input": {
            "style": "随口安利风",
            "pain_point": "怕晒黑",
            "scene": "通勤/日常",
            "product_info": "蕉下防晒霜，特点：水润不假白，适合敏感肌",
        },
        "output": {"style": "随口安利风", "content": "如果你也是日常通勤怕晒黑那种，这种水润一点、不容易假白的防晒会更顺手，补涂的时候也没那么有负担。"},
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
            "final_ads": [],
            "raw_response": "",
            "message": "LLM 接口已预留，当前未配置真实模型。",
            "prompt_version": prompt_bundle.get("prompt_version", ""),
            "review_score": 0,
        }


def build_copywriter_context(state: dict[str, Any]) -> dict[str, Any]:
    """从规范约定的 Global State 中整理文案生成所需上下文。"""
    request_info = state.get("request_info", {})
    vision_analysis = state.get("vision_analysis", {})
    nlp_analysis = state.get("nlp_analysis", {})
    rag_references = state.get("rag_references", [])
    raw_data = state.get("raw_data", {})
    return {
        "product_info": str(request_info.get("product_info", "")).strip(),
        "target_style": str(request_info.get("target_style", "测评风")).strip() or "测评风",
        "scene": str(vision_analysis.get("scene", "待补充场景")),
        "vibe": str(vision_analysis.get("vibe", "生活化")),
        "detected_items": vision_analysis.get("detected_items", []),
        "main_emotion": str(nlp_analysis.get("main_emotion", "待补充情绪")),
        "pain_points": nlp_analysis.get("pain_points", []) or ["需求待挖掘"],
        "language_style": str(nlp_analysis.get("language_style", "生活化表达")),
        "rag_references": rag_references if isinstance(rag_references, list) else [],
        "post_content": str(raw_data.get("post_content", "")).strip(),
    }


def build_generation_prompts(context: dict[str, Any]) -> dict[str, Any]:
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
4. 输出必须是结构化 JSON 数组，每个元素包含 style、content。
5. 每条 content 长度控制在 40-90 字，尽量一句到两句。
6. 优先使用“个人体验”“更适合”“可以先看”这类低压迫表达，不要使用“必须买”“闭眼入”“根治”等强推表达。

可选风格：
{style_block}

下面是风格参考示例：
{example_block}

如果输入信息不足，不要编造细节，用保守表达生成。
""".strip()

    user_prompt = f"""
请根据以下上下文，生成 3 条以上不同风格的小红书评论区候选文案，并优先覆盖目标风格。

### 上下文
- 产品信息: {context['product_info']}
- 目标风格: {context['target_style']}
- 场景: {context['scene']}
- 氛围: {context['vibe']}
- 帖子正文: {context['post_content']}
- 主要痛点: {", ".join(context['pain_points'])}
- 情绪: {context['main_emotion']}
- 语言风格: {context['language_style']}
- 参考文案: {" | ".join(context['rag_references']) if context['rag_references'] else "无"}

### 输出要求
- 每条风格不同，避免改几个词重复表达
- 优先写“真实体验细节、选择逻辑、低压迫建议”
- 不要出现购买链接、私信引导、联系方式
- 不要写得像官方客服
- 输出字段必须是 style 和 content
""".strip()
    return {
        "prompt_version": "agent5-v4",
        "style_guides": STYLE_GUIDES,
        "few_shot_examples": FEW_SHOT_EXAMPLES,
        "expected_output_schema": {
            "type": "json_array",
            "fields": ["style", "content"],
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
        "final_ads": result.get("final_ads", []),
        "raw_response": str(result.get("raw_response", "")),
        "message": str(result.get("message", "")),
        "review_score": int(result.get("review_score", 0) or 0),
        "prompt_version": str(
            result.get("prompt_version", prompt_bundle.get("prompt_version", ""))
        ),
    }


def build_per_comment_prompt(
    comments: list[dict[str, Any]],
    product_info: str,
    pain_points: list[str],
    target_style: str,
) -> dict[str, Any]:
    """构造批量逐评论植入文案的 system/user prompt，一次 LLM 调用覆盖所有评论。"""
    entries = []
    for i, c in enumerate(comments[:8]):
        cid = str(c.get("comment_id") or f"{c.get('note_id', '')}-{i}").strip() or f"c{i}"
        text = str(c.get("comment_text", "")).strip()[:120]
        if text:
            entries.append({"id": cid, "text": text})

    comments_json = json.dumps(entries, ensure_ascii=False, indent=2)
    pain_str = "、".join(pain_points[:3]) if pain_points else "真实体验"

    system_prompt = """你是小红书评论区软植入专家。
针对每条用户评论，生成一条以普通用户口吻发出的植入回复（不是对话回复，是你主动发的评论）。

硬性要求：
1. 先呼应该评论的痛点或场景，再自然带出产品方向，过渡要丝滑
2. 语气像真实用户而非客服，禁止出现"官方""客服""品牌"等词
3. 每条 30-60 字，不堆砌形容词
4. 不使用绝对化表达（"必须""根治""100%"），用"可以先看""更适合""我用下来"等低压迫表达
5. ad_text 中不要提品牌名，只写功能/场景/感受
6. 输出严格 JSON 数组，格式：[{"comment_id": "...", "ad_text": "..."}, ...]
7. 覆盖输入中的每一个 id，不得遗漏"""

    user_prompt = f"""产品背景：{product_info or "待补充"}
用户关注点：{pain_str}
参考风格：{target_style}

评论列表：
{comments_json}

请为每条评论生成一条植入回复，输出 JSON 数组。"""

    return {
        "prompt_version": "per-comment-v1",
        "system_prompt": system_prompt,
        "user_prompt": user_prompt,
    }


def parse_per_comment_result(raw_response: str) -> dict[str, str]:
    """从 LLM 原始 HTTP 响应中解析出 {comment_id: ad_text} 字典。"""
    content = ""
    try:
        resp = json.loads(raw_response)
        content = resp["choices"][0]["message"]["content"]
    except Exception:
        content = raw_response

    content = content.strip()
    # 去掉 markdown 代码块
    content = re.sub(r"^```(?:json)?\s*", "", content)
    content = re.sub(r"\s*```$", "", content).strip()

    items: list[Any] = []
    try:
        items = json.loads(content)
    except json.JSONDecodeError:
        m = re.search(r"\[[\s\S]*\]", content)
        if m:
            try:
                items = json.loads(m.group(0))
            except json.JSONDecodeError:
                pass

    result: dict[str, str] = {}
    if isinstance(items, list):
        for item in items:
            if isinstance(item, dict):
                cid = str(item.get("comment_id", "")).strip()
                ad = str(item.get("ad_text", "")).strip()
                if cid and ad:
                    result[cid] = ad
    return result


def run_copywriter_agent(
    state: dict[str, Any],
    llm_gateway: LLMGateway | None = None,
) -> dict[str, Any]:
    """运行 Agent 5，并把 final_ads 写回 Global State。"""
    context = build_copywriter_context(state)
    prompt_bundle = build_generation_prompts(context)
    llm_result = call_llm_with_reserved_interface(prompt_bundle, llm_gateway=llm_gateway)
    final_ads = llm_result.get("final_ads", [])
    next_state = dict(state)
    next_state["prompt_bundle"] = prompt_bundle
    next_state["llm_result"] = llm_result
    next_state["final_ads"] = final_ads if isinstance(final_ads, list) else []
    next_state["review_score"] = int(llm_result.get("review_score", 0) or 0)
    return next_state

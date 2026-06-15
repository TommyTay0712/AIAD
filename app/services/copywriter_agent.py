from __future__ import annotations

import logging
from typing import Any

from app.models.schemas import AdDraft, NLPAnalysis, RequestInfo, VisionAnalysis
from app.services.llm_gateway import OpenAICompatibleGateway, _extract_json_payload

logger = logging.getLogger(__name__)

DEFAULT_STYLES = ["测评风", "随口安利风", "科普风"]


class CopywriterAgent:
    """核心文案生成智能体。优先 LLM 生成，降级为模板文案。"""

    def __init__(self, gateway: OpenAICompatibleGateway | None = None) -> None:
        self._gateway = gateway

    def generate(
        self,
        request_info: RequestInfo,
        vision_analysis: VisionAnalysis,
        nlp_analysis: NLPAnalysis,
        rag_references: list[str],
        styles: list[str] | None = None,
    ) -> list[AdDraft]:
        if self._gateway is not None:
            try:
                return self._llm_generate(
                    request_info, vision_analysis, nlp_analysis, rag_references, styles
                )
            except Exception as exc:
                logger.warning("LLM 文案生成失败，降级模板 error=%s", exc)
        return self._template_generate(
            request_info, vision_analysis, nlp_analysis, rag_references, styles
        )

    def _llm_generate(
        self,
        request_info: RequestInfo,
        vision_analysis: VisionAnalysis,
        nlp_analysis: NLPAnalysis,
        rag_references: list[str],
        styles: list[str] | None,
    ) -> list[AdDraft]:
        assert self._gateway is not None
        resolved_styles = styles or DEFAULT_STYLES
        ref_text = (
            "\n".join(f"- {r}" for r in rag_references[:5])
            if rag_references
            else "暂无参考案例"
        )
        system_prompt = (
            "你是一个小红书软植入文案专家。请根据提供的背景信息，"
            "生成 JSON 格式的软广告文案，格式为数组：\n"
            '[{"style": "文案风格", "content": "文案内容"}, ...]\n'
            "要求：\n"
            "1. 每种风格生成一条文案，像真实用户评论，不带硬广感\n"
            "2. 自然融入产品，不要直接推销\n"
            "3. 仅输出 JSON 数组，不要其他说明文字"
        )
        user_prompt = (
            f"产品信息：{request_info.product_info or '未指定'}\n"
            f"画面场景：{vision_analysis.scene or '日常分享'}\n"
            f"画面氛围：{vision_analysis.vibe or '自然真实'}\n"
            f"评论情绪：{nlp_analysis.main_emotion or '中性'}\n"
            f"用户痛点：{'、'.join(nlp_analysis.pain_points[:3]) or '暂无'}\n"
            f"推荐切入角度：{'、'.join(nlp_analysis.ad_angles[:2]) or '自然体验'}\n"
            f"参考案例：\n{ref_text}\n\n"
            f"请生成以下风格的文案：{', '.join(resolved_styles)}"
        )
        result = self._gateway.generate({
            "system_prompt": system_prompt,
            "user_prompt": user_prompt,
            "prompt_version": "v1.0-llm",
        })
        final_ads = result.get("final_ads", [])
        if not final_ads:
            raise ValueError(
                f"LLM 文案为空 status={result.get('status')} msg={result.get('message')}"
            )
        return [
            AdDraft(style=ad.get("style", ""), content=ad.get("content", ""))
            for ad in final_ads
        ]

    def _template_generate(
        self,
        request_info: RequestInfo,
        vision_analysis: VisionAnalysis,
        nlp_analysis: NLPAnalysis,
        rag_references: list[str],
        styles: list[str] | None,
    ) -> list[AdDraft]:
        product = request_info.product_info or "这款产品"
        scene = vision_analysis.scene or "这个场景"
        vibe = vision_analysis.vibe or "自然氛围"
        angle = (nlp_analysis.ad_angles or ["真实体验切入"])[0]
        reference = rag_references[0] if rag_references else "像普通用户分享一样自然提一句"
        resolved_styles = styles or DEFAULT_STYLES

        drafts = []
        for style in resolved_styles:
            if style == "测评风":
                content = (
                    f"{scene}这个画面一出来就很有代入感，我最近刚好在用{product}，"
                    f"最直观的感受就是{angle}，整体体验和这种{vibe}场景挺搭，"
                    "不是那种一上脸就很突兀的感觉。"
                )
            elif style == "科普风":
                content = (
                    f"这类{scene}场景其实最容易放大使用感，所以挑{product}的时候我会更看重"
                    f"{angle}。如果评论区有人也在意效果和适配度，可以先从成分/场景匹配去看。"
                )
            else:
                content = (
                    f"{scene}的氛围真的很好，顺手说一句，{product}我最近用下来还蛮惊喜，"
                    f"尤其是{angle}这点，很适合这种{vibe}内容里自然带一下。"
                )
            drafts.append(AdDraft(style=style, content=f"{content} {reference}"))
        return drafts

    BATCH_SIZE = 15   # 每批评论数，减少单次 LLM 输出量加快响应
    MAX_COMMENTS = 60  # 最多处理前 N 条，控制总耗时

    def batch_reply_slice(
        self,
        batch: list[dict[str, Any]],
        offset: int,
        nlp_analysis: NLPAnalysis,
        request_info: RequestInfo,
    ) -> dict[str, str]:
        assert self._gateway is not None
        comment_lines = "\n".join(
            f"{offset + i}: {c.get('content', '').strip()}"
            for i, c in enumerate(batch)
            if c.get("content", "").strip()
        )
        if not comment_lines:
            return {}
        system_prompt = (
            "你是一个小红书评论区软植入文案专家。"
            "针对以下每条评论，生成一条自然融入产品的回复，像真实用户发言，不带硬广感。\n"
            "输出严格 JSON 数组，格式：\n"
            '[{"index": 评论序号, "reply": "回复内容"}, ...]\n'
            "要求：口语化，50-120字，仅输出 JSON 数组，不要其他文字。"
        )
        user_prompt = (
            f"产品：{request_info.product_info or '护肤品'}\n"
            f"评论情绪：{nlp_analysis.main_emotion or '中性'}\n"
            f"推荐角度：{'、'.join(nlp_analysis.ad_angles[:2]) or '真实体验'}\n\n"
            f"评论列表：\n{comment_lines}"
        )
        raw = self._gateway.chat(system_prompt, user_prompt)
        if not raw:
            raise ValueError("LLM 返回空内容")
        data = _extract_json_payload(raw)
        result: dict[str, str] = {}
        if isinstance(data, list):
            for item in data:
                if isinstance(item, dict):
                    idx = str(item.get("index", ""))
                    reply = str(item.get("reply", ""))
                    if idx != "" and reply:
                        result[idx] = reply
        return result

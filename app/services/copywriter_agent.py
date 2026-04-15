from __future__ import annotations

from app.models.schemas import AdDraft, NLPAnalysis, RequestInfo, VisionAnalysis

DEFAULT_STYLES = ["测评风", "随口安利风", "科普风"]


class CopywriterAgent:
    """核心文案生成智能体的最小可联调实现。"""

    def generate(
        self,
        request_info: RequestInfo,
        vision_analysis: VisionAnalysis,
        nlp_analysis: NLPAnalysis,
        rag_references: list[str],
        styles: list[str] | None = None,
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

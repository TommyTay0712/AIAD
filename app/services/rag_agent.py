from __future__ import annotations

from app.models.schemas import NLPAnalysis, VisionAnalysis


class RagAgent:
    """记忆与检索智能体的最小可联调实现。"""

    def retrieve(
        self,
        vision_analysis: VisionAnalysis,
        nlp_analysis: NLPAnalysis,
        top_k: int = 5,
    ) -> list[str]:
        scene = vision_analysis.scene or "日常分享场景"
        vibe = vision_analysis.vibe or "自然真实"
        emotion = nlp_analysis.main_emotion or "中性讨论"
        angles = nlp_analysis.ad_angles or ["自然体验式表达"]
        items = vision_analysis.detected_items[:2] or ["真实使用细节"]

        candidates = [
            f"这个{scene}的氛围真的很适合做自然种草，顺着{vibe}的感觉补一句体验就很顺。",
            f"评论区现在是“{emotion}”的语境，建议不要硬推，先回应顾虑再带产品。",
            f"如果围绕{angles[0]}来写，广告感会比直接报产品卖点弱很多。",
            f"可以借画面里的{items[0]}切入，把产品放进真实使用场景里。",
            "高转化文案通常先像普通用户分享，再自然补一句为什么会回购。",
            "这类帖子更适合‘先共情，再安利’的结构，不适合上来就品牌自述。",
        ]
        return candidates[: max(1, top_k)]

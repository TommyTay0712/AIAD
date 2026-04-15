from __future__ import annotations

from collections import Counter

from app.models.schemas import NLPAnalysis, RawComment


class ContextAgent:
    """评论区语境与情感智能体的启发式实现。"""

    def analyze(self, comments: list[RawComment], product_info: str = "") -> NLPAnalysis:
        texts = [comment.content.strip() for comment in comments if comment.content.strip()]
        joined_text = " ".join(texts)
        emotion = self._detect_emotion(joined_text)
        pain_points = self._detect_pain_points(joined_text, product_info)
        language_style = self._detect_language_style(texts)
        keyword_summary = self._extract_keywords(texts)
        ad_angles = self._build_ad_angles(pain_points, emotion, product_info)
        return NLPAnalysis(
            main_emotion=emotion,
            pain_points=pain_points,
            language_style=language_style,
            ad_angles=ad_angles,
            keyword_summary=keyword_summary,
        )

    def _detect_emotion(self, text: str) -> str:
        if any(token in text for token in ["求链接", "哪里买", "怎么买", "链接"]):
            return "高兴趣，带明显购买/求购意图"
        if any(token in text for token in ["喜欢", "种草", "好看", "想要"]):
            return "积极，容易接受种草信息"
        if any(token in text for token in ["避雷", "失望", "踩雷", "不好用"]):
            return "谨慎，对效果与真实性更敏感"
        return "中性，偏围观讨论"

    def _detect_pain_points(self, text: str, product_info: str) -> list[str]:
        pain_points: list[str] = []
        keyword_map = {
            "求链接": "用户希望快速获取购买入口",
            "防晒": "用户关注防晒效果与场景适配",
            "敏感肌": "用户关注成分温和与低刺激",
            "贵": "用户对价格敏感",
            "不好用": "用户担心使用体验和真实效果",
            "适合": "用户关心人群适配与使用条件",
        }
        for keyword, desc in keyword_map.items():
            if keyword in text and desc not in pain_points:
                pain_points.append(desc)
        if (
            product_info
            and "防晒" in product_info
            and "用户关注防晒效果与场景适配" not in pain_points
        ):
            pain_points.append("用户关注防晒效果与场景适配")
        return pain_points or ["用户更关注真实体验、使用效果和购买决策成本"]

    def _detect_language_style(self, texts: list[str]) -> str:
        has_emoji = any(any(char in text for char in "😀🤣🥹😭😍🔥✨👍") for text in texts)
        has_question = any("?" in text or "？" in text for text in texts)
        has_short_text = sum(len(text) <= 12 for text in texts) >= max(1, len(texts) // 3)
        styles = []
        if has_emoji:
            styles.append("带表情和情绪化表达")
        if has_question:
            styles.append("提问型互动明显")
        if has_short_text:
            styles.append("短句高频，适合口语化回复")
        return "；".join(styles) if styles else "自然口语化，偏真实交流"

    def _extract_keywords(self, texts: list[str], limit: int = 6) -> list[str]:
        counter: Counter[str] = Counter()
        for text in texts:
            for keyword in ["求链接", "防晒", "敏感肌", "好用", "喜欢", "在哪里买", "效果"]:
                if keyword in text:
                    counter[keyword] += 1
        return [word for word, _ in counter.most_common(limit)]

    def _build_ad_angles(
        self,
        pain_points: list[str],
        emotion: str,
        product_info: str,
    ) -> list[str]:
        angles = []
        if "购买入口" in "".join(pain_points):
            angles.append("从真实使用体验切入，再顺带给出购买建议")
        if "防晒" in "".join(pain_points):
            angles.append("突出具体场景下的效果表现，如通勤、海边、暴晒")
        if "价格敏感" in "".join(pain_points):
            angles.append("强调性价比、用量和复购理由")
        if "谨慎" in emotion:
            angles.append("弱化广告感，优先回答顾虑和避雷点")
        if product_info and not angles:
            angles.append(f"围绕“{product_info}”的真实体验和适用人群展开")
        return angles or ["优先采用像普通用户回帖的自然安利角度"]

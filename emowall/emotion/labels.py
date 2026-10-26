"""情绪标签与不可变展示元数据（Stage 4）。

本模块只放纯数据与展示映射：不发网络请求、不读写文件、不依赖 Qt。
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class Emotion(str, Enum):
    """五种基础表情；值同时是 Storage / 组合根使用的字符串。"""

    HAPPY = "happy"
    CALM = "calm"
    SAD = "sad"
    ANGRY = "angry"
    SURPRISED = "surprised"


@dataclass(frozen=True)
class EmotionPresentation:
    """一种表情的展示数据（不含 Qt 类型）。"""

    label: str
    emoji: str
    color: str


_PRESENTATIONS: dict[Emotion, EmotionPresentation] = {
    Emotion.HAPPY: EmotionPresentation("开心", "😊", "#FFB74D"),
    Emotion.CALM: EmotionPresentation("平静", "😌", "#81C784"),
    Emotion.SAD: EmotionPresentation("难过", "😢", "#64B5F6"),
    Emotion.ANGRY: EmotionPresentation("生气", "😠", "#E57373"),
    Emotion.SURPRISED: EmotionPresentation("惊讶", "😲", "#BA68C8"),
}


def presentation(emotion: Emotion) -> EmotionPresentation:
    """返回一种表情的展示数据（模块级 frozen 实例，不可变）。"""
    if not isinstance(emotion, Emotion):
        raise TypeError(
            f"presentation() 需要 Emotion 实例，收到 {type(emotion).__name__}"
        )
    return _PRESENTATIONS[emotion]

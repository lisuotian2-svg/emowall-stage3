"""中英文情绪词典（Stage 4，纯数据、无逻辑）。

词条为 ``(词形, 情绪, 权重)``；声明顺序即"同起点、同长度"候选的确定性顺序。
英文统一小写，中文与 emoji 原样。否定短语单独维护：detector 以 ``sad`` / ``1.0``
并入匹配，但不得同时出现在 ``EMOTION_LEXICON`` 中，避免重复计分。
"""

from __future__ import annotations

from .labels import Emotion

WEIGHT_STRONG = 1.0
WEIGHT_WEAK = 0.5
WEIGHT_EMOJI = 1.5

LexiconEntry = tuple[str, Emotion, float]

# 105 条基础词条（happy 22 / sad 23 / angry 19 / surprised 22 / calm 19）。
EMOTION_LEXICON: tuple[LexiconEntry, ...] = (
    # ---- happy（22）----
    ("开心", Emotion.HAPPY, WEIGHT_STRONG),
    ("高兴", Emotion.HAPPY, WEIGHT_STRONG),
    ("快乐", Emotion.HAPPY, WEIGHT_STRONG),
    ("幸福", Emotion.HAPPY, WEIGHT_STRONG),
    ("兴奋", Emotion.HAPPY, WEIGHT_STRONG),
    ("愉快", Emotion.HAPPY, WEIGHT_STRONG),
    ("满意", Emotion.HAPPY, WEIGHT_WEAK),
    ("太好了", Emotion.HAPPY, WEIGHT_STRONG),
    ("太棒了", Emotion.HAPPY, WEIGHT_STRONG),
    ("哈哈", Emotion.HAPPY, WEIGHT_STRONG),
    ("嘻嘻", Emotion.HAPPY, WEIGHT_WEAK),
    ("笑", Emotion.HAPPY, WEIGHT_WEAK),
    ("happy", Emotion.HAPPY, WEIGHT_STRONG),
    ("glad", Emotion.HAPPY, WEIGHT_STRONG),
    ("joyful", Emotion.HAPPY, WEIGHT_STRONG),
    ("wonderful", Emotion.HAPPY, WEIGHT_STRONG),
    ("great", Emotion.HAPPY, WEIGHT_WEAK),
    ("awesome", Emotion.HAPPY, WEIGHT_STRONG),
    ("love", Emotion.HAPPY, WEIGHT_STRONG),
    ("yay", Emotion.HAPPY, WEIGHT_STRONG),
    ("😊", Emotion.HAPPY, WEIGHT_EMOJI),
    ("😄", Emotion.HAPPY, WEIGHT_EMOJI),
    # ---- sad（23）----
    ("难过", Emotion.SAD, WEIGHT_STRONG),
    ("伤心", Emotion.SAD, WEIGHT_STRONG),
    ("悲伤", Emotion.SAD, WEIGHT_STRONG),
    ("失落", Emotion.SAD, WEIGHT_WEAK),
    ("沮丧", Emotion.SAD, WEIGHT_STRONG),
    ("郁闷", Emotion.SAD, WEIGHT_WEAK),
    ("委屈", Emotion.SAD, WEIGHT_WEAK),
    ("哭", Emotion.SAD, WEIGHT_WEAK),
    ("想哭", Emotion.SAD, WEIGHT_STRONG),
    ("遗憾", Emotion.SAD, WEIGHT_WEAK),
    ("绝望", Emotion.SAD, WEIGHT_STRONG),
    ("心痛", Emotion.SAD, WEIGHT_STRONG),
    ("唉", Emotion.SAD, WEIGHT_WEAK),
    ("sad", Emotion.SAD, WEIGHT_STRONG),
    ("unhappy", Emotion.SAD, WEIGHT_STRONG),
    ("depressed", Emotion.SAD, WEIGHT_STRONG),
    ("cry", Emotion.SAD, WEIGHT_WEAK),
    ("lonely", Emotion.SAD, WEIGHT_STRONG),
    ("miserable", Emotion.SAD, WEIGHT_STRONG),
    ("heartbroken", Emotion.SAD, WEIGHT_STRONG),
    ("😢", Emotion.SAD, WEIGHT_EMOJI),
    ("😭", Emotion.SAD, WEIGHT_EMOJI),
    ("💔", Emotion.SAD, WEIGHT_EMOJI),
    # ---- angry（19）----
    ("生气", Emotion.ANGRY, WEIGHT_STRONG),
    ("愤怒", Emotion.ANGRY, WEIGHT_STRONG),
    ("恼火", Emotion.ANGRY, WEIGHT_STRONG),
    ("讨厌", Emotion.ANGRY, WEIGHT_WEAK),
    ("烦躁", Emotion.ANGRY, WEIGHT_WEAK),
    ("火大", Emotion.ANGRY, WEIGHT_STRONG),
    ("气死", Emotion.ANGRY, WEIGHT_STRONG),
    ("可恶", Emotion.ANGRY, WEIGHT_STRONG),
    ("受不了", Emotion.ANGRY, WEIGHT_WEAK),
    ("恨", Emotion.ANGRY, WEIGHT_STRONG),
    ("气人", Emotion.ANGRY, WEIGHT_STRONG),
    ("angry", Emotion.ANGRY, WEIGHT_STRONG),
    ("mad", Emotion.ANGRY, WEIGHT_WEAK),
    ("furious", Emotion.ANGRY, WEIGHT_STRONG),
    ("annoyed", Emotion.ANGRY, WEIGHT_WEAK),
    ("hate", Emotion.ANGRY, WEIGHT_STRONG),
    ("😠", Emotion.ANGRY, WEIGHT_EMOJI),
    ("😡", Emotion.ANGRY, WEIGHT_EMOJI),
    ("🤬", Emotion.ANGRY, WEIGHT_EMOJI),
    # ---- surprised（22）----
    ("惊讶", Emotion.SURPRISED, WEIGHT_STRONG),
    ("吃惊", Emotion.SURPRISED, WEIGHT_STRONG),
    ("震惊", Emotion.SURPRISED, WEIGHT_STRONG),
    ("意外", Emotion.SURPRISED, WEIGHT_WEAK),
    ("没想到", Emotion.SURPRISED, WEIGHT_STRONG),
    ("竟然", Emotion.SURPRISED, WEIGHT_WEAK),
    ("居然", Emotion.SURPRISED, WEIGHT_WEAK),
    ("哇", Emotion.SURPRISED, WEIGHT_STRONG),
    ("天哪", Emotion.SURPRISED, WEIGHT_STRONG),
    ("不敢相信", Emotion.SURPRISED, WEIGHT_STRONG),
    ("惊喜", Emotion.SURPRISED, WEIGHT_WEAK),
    ("surprised", Emotion.SURPRISED, WEIGHT_STRONG),
    ("shocked", Emotion.SURPRISED, WEIGHT_STRONG),
    ("wow", Emotion.SURPRISED, WEIGHT_STRONG),
    ("amazing", Emotion.SURPRISED, WEIGHT_WEAK),
    ("unexpected", Emotion.SURPRISED, WEIGHT_WEAK),
    ("whoa", Emotion.SURPRISED, WEIGHT_WEAK),
    ("omg", Emotion.SURPRISED, WEIGHT_STRONG),
    ("😲", Emotion.SURPRISED, WEIGHT_EMOJI),
    ("😮", Emotion.SURPRISED, WEIGHT_EMOJI),
    ("😱", Emotion.SURPRISED, WEIGHT_EMOJI),
    ("🤯", Emotion.SURPRISED, WEIGHT_EMOJI),
    # ---- calm（19）----
    ("平静", Emotion.CALM, WEIGHT_STRONG),
    ("冷静", Emotion.CALM, WEIGHT_STRONG),
    ("放松", Emotion.CALM, WEIGHT_STRONG),
    ("安心", Emotion.CALM, WEIGHT_STRONG),
    ("安稳", Emotion.CALM, WEIGHT_WEAK),
    ("淡定", Emotion.CALM, WEIGHT_STRONG),
    ("舒适", Emotion.CALM, WEIGHT_WEAK),
    ("舒服", Emotion.CALM, WEIGHT_WEAK),
    ("宁静", Emotion.CALM, WEIGHT_STRONG),
    ("平和", Emotion.CALM, WEIGHT_STRONG),
    ("还好", Emotion.CALM, WEIGHT_WEAK),
    ("没事", Emotion.CALM, WEIGHT_WEAK),
    ("calm", Emotion.CALM, WEIGHT_STRONG),
    ("relaxed", Emotion.CALM, WEIGHT_STRONG),
    ("peaceful", Emotion.CALM, WEIGHT_STRONG),
    ("chill", Emotion.CALM, WEIGHT_WEAK),
    ("tranquil", Emotion.CALM, WEIGHT_WEAK),
    ("serene", Emotion.CALM, WEIGHT_STRONG),
    ("😌", Emotion.CALM, WEIGHT_EMOJI),
)

# 否定的正向表达：命中即按 sad / 1.0 计分，并遮蔽内部正向词（非重叠匹配）。
NEGATION_PHRASES: tuple[str, ...] = (
    "不开心",
    "不高兴",
    "没意思",
    "not happy",
    "don't like",
    "不快乐",
    "不满意",
    "不愉快",
)

# D08 批准的有限排除短语：只遮蔽自己的区间、贡献 0 分，不进入 matched_keywords。
EXCLUSION_PHRASES: tuple[str, ...] = (
    "生气勃勃",
    "别生气",
    "笑话",
    "开心果",
    "not great",
)

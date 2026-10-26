"""规则法情绪检测（Stage 4）。

纯函数：仅标准库，无 I/O、无随机、无时间依赖；同一输入必同输出。
算法与语义见 ``docs/contracts/stage4-emotion-v1.md`` §4。
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

from .labels import Emotion
from .lexicon import EMOTION_LEXICON, EXCLUSION_PHRASES, NEGATION_PHRASES

_INTENSITY_SCALE = 3.0
_APOSTROPHE_TRANSLATION = str.maketrans({"\u2019": "'", "\u2018": "'", "`": "'"})
_WHITESPACE = re.compile(r"\s+")

# 情感词 + 否定短语（sad/1.0）。排除短语单独维护，kind=0，仅遮蔽不计分。
_SENTIMENT_ENTRIES: tuple[tuple[str, Emotion, float], ...] = EMOTION_LEXICON + tuple(
    (phrase, Emotion.SAD, 1.0) for phrase in NEGATION_PHRASES
)
_EXCLUSION_ENTRIES: tuple[tuple[str, float], ...] = tuple(
    (phrase, 0.0) for phrase in EXCLUSION_PHRASES
)


@dataclass(frozen=True)
class EmotionResult:
    """一次情绪检测的不可变结果。"""

    emotion: Emotion
    intensity: float
    matched_keywords: tuple[str, ...]
    source: str = "rule"


def detect_emotion(text: str) -> EmotionResult:
    """把一段文本映射为五种基础表情之一（纯函数、确定性）。

    Args:
        text: 待分析文本；非 ``str`` 抛 ``TypeError``。

    Returns:
        ``EmotionResult``：emotion、[0, 1] 内两位小数的 intensity、
        按首次出现排序并去重的规范命中词、``source="rule"``。
    """
    if not isinstance(text, str):
        raise TypeError(f"detect_emotion() 需要 text: str，收到 {type(text).__name__}")

    normalized = _normalize(text)
    hits = _accepted_hits(normalized)
    scored_hits = [hit for hit in hits if hit[2] is not None]
    matched = _matched_keywords(scored_hits)

    if not scored_hits:
        return EmotionResult(Emotion.CALM, 0.0, matched)

    scores: dict[Emotion, float] = dict.fromkeys(Emotion, 0.0)
    for _start, _token, emotion, weight in scored_hits:
        scores[emotion] += weight

    best = max(scores.values())
    winners = [emotion for emotion in Emotion if scores[emotion] == best]

    if len(winners) > 1:
        # 并列 → 默认平静；保留命中词便于调试（D04）。
        return EmotionResult(Emotion.CALM, 0.0, matched)

    return EmotionResult(winners[0], _intensity(best), matched)


def _normalize(text: str) -> str:
    """NFKC → 弯引号归一 → casefold → 空白折叠/去首尾（D16）。"""
    normalized = unicodedata.normalize("NFKC", text)
    normalized = normalized.translate(_APOSTROPHE_TRANSLATION)
    normalized = normalized.casefold()
    return _WHITESPACE.sub(" ", normalized).strip()


def _intensity(score: float) -> float:
    """强度 = min(1.0, score / 3.0)，保留两位小数（D14）。"""
    return round(min(1.0, score / _INTENSITY_SCALE), 2)


def _is_ascii_alnum(char: str) -> bool:
    return char.isascii() and char.isalnum()


def _boundary_ok(text: str, start: int, token: str) -> bool:
    """英文/ASCII 词元要求两侧不是 ASCII 字母数字；中文与 emoji 不要求边界。"""
    if _is_ascii_alnum(token[0]) and start > 0 and _is_ascii_alnum(text[start - 1]):
        return False
    end = start + len(token) - 1
    if _is_ascii_alnum(token[-1]) and end + 1 < len(text) and _is_ascii_alnum(text[end + 1]):
        return False
    return True


def _collect_candidates(
    text: str,
    token: str,
    kind: int,
    order: int,
    emotion: Emotion | None,
    weight: float,
    candidates: list[tuple[int, int, int, int, str, Emotion | None, float]],
) -> None:
    search_from = 0
    while True:
        start = text.find(token, search_from)
        if start < 0:
            break
        if _boundary_ok(text, start, token):
            candidates.append((start, -len(token), kind, order, token, emotion, weight))
        search_from = start + 1


def _accepted_hits(text: str) -> list[tuple[int, str, Emotion | None, float]]:
    """最左最长、非重叠地接受命中（D17）；排除短语 kind=0，仅遮蔽不计分。

    排序键为 ``(起点, -长度, kind, 声明顺序)``：同起点长者优先；同起点同长度时
    kind=0（排除短语）优先，其余按固定声明顺序。
    """
    candidates: list[tuple[int, int, int, int, str, Emotion | None, float]] = []
    for order, (token, emotion, weight) in enumerate(_SENTIMENT_ENTRIES):
        _collect_candidates(text, token, 1, order, emotion, weight, candidates)
    for order, (token, weight) in enumerate(_EXCLUSION_ENTRIES):
        _collect_candidates(text, token, 0, order, None, weight, candidates)

    candidates.sort(key=lambda candidate: (candidate[0], candidate[1], candidate[2], candidate[3]))

    accepted: list[tuple[int, str, Emotion | None, float]] = []
    last_end = -1
    for start, _negative_length, _kind, _order, token, emotion, weight in candidates:
        if start >= last_end:
            accepted.append((start, token, emotion, weight))
            last_end = start + len(token)
    return accepted


def _matched_keywords(hits: list[tuple[int, str, Emotion | None, float]]) -> tuple[str, ...]:
    """按首次出现位置去重，返回规范词形（D07）；排除短语不进入。"""
    seen: set[str] = set()
    keywords: list[str] = []
    for _start, token, emotion, _weight in hits:
        if emotion is None:
            continue
        if token not in seen:
            seen.add(token)
            keywords.append(token)
    return tuple(keywords)

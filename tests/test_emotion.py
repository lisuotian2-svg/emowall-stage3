"""Stage 4 情绪核心黄金测试（契约 ``stage4-emotion-v1`` §7）。

本文件先于实现编写（RED），实现后转绿（GREEN）。表驱动覆盖：
五类正例、计分/强度/舍入、英文边界、否定遮蔽、非重叠、混合类别、
20 条中性文本、空白/长文本/无效输入、重复词、确定性、展示元数据、
词典全表与导出精确断言。
"""

from __future__ import annotations

import re
from dataclasses import FrozenInstanceError

import pytest

import emowall.emotion as emotion_pkg
from emowall.emotion import (
    Emotion,
    EmotionPresentation,
    EmotionResult,
    detect_emotion,
    presentation,
)
from emowall.emotion.lexicon import EMOTION_LEXICON, NEGATION_PHRASES

# ---------------------------------------------------------------------------
# 黄金样本（G01–G101；无效输入 G68–G70 用单独用例表达）
# 元组：(ID, 输入, 期望 emotion, 期望 intensity, 期望 matched_keywords)
# ---------------------------------------------------------------------------

GOLDEN_CASES: tuple[tuple[str, str, Emotion, float, tuple[str, ...]], ...] = (
    # 7.1 五类基础正例
    ("G01", "开心", Emotion.HAPPY, 0.33, ("开心",)),
    ("G02", "难过", Emotion.SAD, 0.33, ("难过",)),
    ("G03", "生气", Emotion.ANGRY, 0.33, ("生气",)),
    ("G04", "惊讶", Emotion.SURPRISED, 0.33, ("惊讶",)),
    ("G05", "平静", Emotion.CALM, 0.33, ("平静",)),
    ("G06", "😊", Emotion.HAPPY, 0.50, ("😊",)),
    ("G07", "💔", Emotion.SAD, 0.50, ("💔",)),
    ("G08", "😠", Emotion.ANGRY, 0.50, ("😠",)),
    ("G09", "😲", Emotion.SURPRISED, 0.50, ("😲",)),
    ("G10", "😌", Emotion.CALM, 0.50, ("😌",)),
    # 7.2 计分、强度与舍入
    ("G11", "满意", Emotion.HAPPY, 0.17, ("满意",)),
    ("G12", "开心高兴", Emotion.HAPPY, 0.67, ("开心", "高兴")),
    ("G13", "开心高兴快乐", Emotion.HAPPY, 1.00, ("开心", "高兴", "快乐")),
    ("G14", "开心满意", Emotion.HAPPY, 0.50, ("开心", "满意")),
    ("G15", "开心😊", Emotion.HAPPY, 0.83, ("开心", "😊")),
    ("G16", "开心高兴快乐幸福", Emotion.HAPPY, 1.00, ("开心", "高兴", "快乐", "幸福")),
    ("G17", "😊😄", Emotion.HAPPY, 1.00, ("😊", "😄")),
    ("G18", "happy", Emotion.HAPPY, 0.33, ("happy",)),
    ("G19", "HAPPY", Emotion.HAPPY, 0.33, ("happy",)),
    ("G20", "开心happy", Emotion.HAPPY, 0.67, ("开心", "happy")),
    ("G21", "开心，开心，开心，开心", Emotion.HAPPY, 1.00, ("开心",)),
    # 7.3 英文词边界
    ("G22", "sadistic", Emotion.CALM, 0.00, ()),
    ("G23", "gladiator", Emotion.CALM, 0.00, ()),
    ("G24", "happiness", Emotion.CALM, 0.00, ()),
    ("G25", "I am happy!", Emotion.HAPPY, 0.33, ("happy",)),
    ("G26", "unhappy", Emotion.SAD, 0.33, ("unhappy",)),
    ("G27", "We are not happy.", Emotion.SAD, 0.33, ("not happy",)),
    # 7.4 否定与遮蔽
    ("G28", "我不开心", Emotion.SAD, 0.33, ("不开心",)),
    ("G29", "我不高兴", Emotion.SAD, 0.33, ("不高兴",)),
    ("G30", "没意思", Emotion.SAD, 0.33, ("没意思",)),
    ("G31", "I don't like it.", Emotion.SAD, 0.33, ("don't like",)),
    ("G32", "不快乐", Emotion.SAD, 0.33, ("不快乐",)),
    ("G33", "not happy but wonderful", Emotion.CALM, 0.00, ("not happy", "wonderful")),
    # 7.5 非重叠匹配
    ("G34", "想哭", Emotion.SAD, 0.33, ("想哭",)),
    ("G35", "有点想哭", Emotion.SAD, 0.33, ("想哭",)),
    ("G36", "不高兴，但也不难过", Emotion.SAD, 0.67, ("不高兴", "难过")),
    # 7.6 混合类别、胜出与排序
    ("G37", "开心，生气，愤怒", Emotion.ANGRY, 0.67, ("开心", "生气", "愤怒")),
    ("G38", "开心，难过，伤心", Emotion.SAD, 0.67, ("开心", "难过", "伤心")),
    ("G39", "开心，生气", Emotion.CALM, 0.00, ("开心", "生气")),
    ("G40", "开心😊 平静", Emotion.HAPPY, 0.83, ("开心", "😊", "平静")),
    ("G41", "开心 难过 开心", Emotion.HAPPY, 0.67, ("开心", "难过")),
    # 7.7 20 条独立中性文本
    ("G42", "这是一段普通的说明文字。", Emotion.CALM, 0.00, ()),
    ("G43", "会议室在三楼东侧。", Emotion.CALM, 0.00, ()),
    ("G44", "请把文件放到桌面上。", Emotion.CALM, 0.00, ()),
    ("G45", "今天的天气是阴天。", Emotion.CALM, 0.00, ()),
    ("G46", "我需要核对一下表格数据。", Emotion.CALM, 0.00, ()),
    ("G47", "列车将在十分钟后到达。", Emotion.CALM, 0.00, ()),
    ("G48", "这个函数返回布尔值。", Emotion.CALM, 0.00, ()),
    ("G49", "密码需要至少八位字符。", Emotion.CALM, 0.00, ()),
    ("G50", "请在周五之前提交申请。", Emotion.CALM, 0.00, ()),
    ("G51", "打印机缺纸了。", Emotion.CALM, 0.00, ()),
    ("G52", "我下午三点有个会议。", Emotion.CALM, 0.00, ()),
    ("G53", "这段代码使用标准库。", Emotion.CALM, 0.00, ()),
    ("G54", "快递预计明天送达。", Emotion.CALM, 0.00, ()),
    ("G55", "请关闭所有电源。", Emotion.CALM, 0.00, ()),
    ("G56", "这本书共有十二个章节。", Emotion.CALM, 0.00, ()),
    ("G57", "The report is due on Friday.", Emotion.CALM, 0.00, ()),
    ("G58", "Please update the spreadsheet.", Emotion.CALM, 0.00, ()),
    ("G59", "The meeting room is on the third floor.", Emotion.CALM, 0.00, ()),
    ("G60", "Insert the cable into the port.", Emotion.CALM, 0.00, ()),
    ("G61", "The package arrives tomorrow.", Emotion.CALM, 0.00, ()),
    # 7.8 空白、长文本
    ("G62", "", Emotion.CALM, 0.00, ()),
    ("G63", " \t\n\r\f\v", Emotion.CALM, 0.00, ()),
    ("G64", "  开心  ", Emotion.HAPPY, 0.33, ("开心",)),
    ("G65", "开 心", Emotion.CALM, 0.00, ()),
    ("G66", "这是一段很长的文本。" * 1000, Emotion.CALM, 0.00, ()),
    ("G67", "这是一段很长的文本。" * 1000 + "开心", Emotion.HAPPY, 0.33, ("开心",)),
    # 7.9 重复词
    ("G71", "开心开心", Emotion.HAPPY, 0.67, ("开心",)),
    ("G72", "开心开心开心", Emotion.HAPPY, 1.00, ("开心",)),
    # 7.14 规范化与边界
    ("G86", "made", Emotion.CALM, 0.00, ()),
    ("G87", "sadness", Emotion.CALM, 0.00, ()),
    ("G88", "ＨＡＰＰＹ", Emotion.HAPPY, 0.33, ("happy",)),
    ("G89", "NOT HAPPY", Emotion.SAD, 0.33, ("not happy",)),
    ("G90", "don\u2019t like it", Emotion.SAD, 0.33, ("don't like",)),
    ("G91", "NOT   HAPPY", Emotion.SAD, 0.33, ("not happy",)),
    ("G99", "\u3000开心\u3000", Emotion.HAPPY, 0.33, ("开心",)),
    # 7.15 D08 排除规则（已批准）
    ("G92", "生气勃勃", Emotion.CALM, 0.00, ()),
    ("G93", "别生气", Emotion.CALM, 0.00, ()),
    ("G94", "这是一个笑话", Emotion.CALM, 0.00, ()),
    ("G96", "not great", Emotion.CALM, 0.00, ()),
    ("G102", "开心果", Emotion.CALM, 0.00, ()),
    # G103 为已批准规则下的已知限制（不代表正确语境判断）
    ("G103", "不开心果", Emotion.SAD, 0.33, ("不开心",)),
    # 7.17 D08 组合句（已批准）
    ("G104", "别生气，我很开心", Emotion.HAPPY, 0.33, ("开心",)),
    ("G105", "开心果让我很开心", Emotion.HAPPY, 0.33, ("开心",)),
    ("G106", "别生气了", Emotion.CALM, 0.00, ()),
    ("G107", "开心果酱", Emotion.CALM, 0.00, ()),
    ("G108", "别太生气", Emotion.ANGRY, 0.33, ("生气",)),
    ("G109", "not-so-great", Emotion.HAPPY, 0.17, ("great",)),
    ("G110", "笑笑话", Emotion.HAPPY, 0.17, ("笑",)),
    ("G111", "not  great", Emotion.CALM, 0.00, ()),
    ("G112", "Not Great", Emotion.CALM, 0.00, ()),
    # 7.16 D02 补充
    ("G95", "不满意", Emotion.SAD, 0.33, ("不满意",)),
    ("G101", "不愉快", Emotion.SAD, 0.33, ("不愉快",)),
)

NEUTRALS: tuple[str, ...] = tuple(
    case[1] for case in GOLDEN_CASES if case[0] in {f"G{i:02d}" for i in range(42, 62)}
)


@pytest.mark.parametrize(
    ("case_id", "text", "expected_emotion", "expected_intensity", "expected_matched"),
    GOLDEN_CASES,
    ids=[case[0] for case in GOLDEN_CASES],
)
def test_golden_case(
    case_id: str,
    text: str,
    expected_emotion: Emotion,
    expected_intensity: float,
    expected_matched: tuple[str, ...],
) -> None:
    result = detect_emotion(text)

    assert result.emotion is expected_emotion, case_id
    assert result.intensity == expected_intensity, case_id
    assert isinstance(result.intensity, float), case_id
    assert result.matched_keywords == expected_matched, case_id
    assert result.source == "rule", case_id


# ---------------------------------------------------------------------------
# G68–G70：无效输入
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "bad_input",
    [None, 123, b"happy", ["开心"], 1.5, True],
    ids=["none", "int", "bytes", "list", "float", "bool"],
)
def test_non_str_input_raises_type_error(bad_input: object) -> None:
    with pytest.raises(TypeError, match="text"):
        detect_emotion(bad_input)  # type: ignore[arg-type]


class _StrSubclass(str):
    """契约 §6：str 子类应按普通 str 接受。"""


def test_str_subclass_is_accepted() -> None:
    result = detect_emotion(_StrSubclass("开心"))

    assert result == EmotionResult(Emotion.HAPPY, 0.33, ("开心",))


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("\x00开心\x00", (Emotion.HAPPY, 0.33, ("开心",))),
        ("\x01难过\x02", (Emotion.SAD, 0.33, ("难过",))),
        ("\x07", (Emotion.CALM, 0.0, ())),
        ("\x1b生气\x1f", (Emotion.ANGRY, 0.33, ("生气",))),
        ("\x00sad\x7f", (Emotion.SAD, 0.33, ("sad",))),
    ],
    ids=["nul", "stx-etx", "bel", "esc-us", "nul-del"],
)
def test_nul_and_control_characters_are_accepted(
    text: str,
    expected: tuple[Emotion, float, tuple[str, ...]],
) -> None:
    result = detect_emotion(text)

    assert result.emotion is expected[0]
    assert result.intensity == expected[1]
    assert result.matched_keywords == expected[2]


# ---------------------------------------------------------------------------
# G73：确定性（同一输入 100 次）
# ---------------------------------------------------------------------------

DETERMINISM_INPUTS: tuple[str, ...] = (
    "开心",
    "not happy but wonderful",
    "😊😄",
    "会议室在三楼东侧。",
    "这是一段很长的文本。" * 1000,
)


@pytest.mark.parametrize("text", DETERMINISM_INPUTS, ids=range(len(DETERMINISM_INPUTS)))
def test_determinism_across_100_runs(text: str) -> None:
    first = detect_emotion(text)
    for _ in range(100):
        assert detect_emotion(text) == first


# ---------------------------------------------------------------------------
# G74–G78：展示元数据与不可变性
# ---------------------------------------------------------------------------

EXPECTED_PRESENTATION: dict[Emotion, tuple[str, str, str]] = {
    Emotion.HAPPY: ("开心", "😊", "#FFB74D"),
    Emotion.CALM: ("平静", "😌", "#81C784"),
    Emotion.SAD: ("难过", "😢", "#64B5F6"),
    Emotion.ANGRY: ("生气", "😠", "#E57373"),
    Emotion.SURPRISED: ("惊讶", "😲", "#BA68C8"),
}


@pytest.mark.parametrize("emotion", list(Emotion), ids=lambda value: value.value)
def test_presentation_exact(emotion: Emotion) -> None:
    got = presentation(emotion)
    assert isinstance(got, EmotionPresentation)
    assert (got.label, got.emoji, got.color) == EXPECTED_PRESENTATION[emotion]


@pytest.mark.parametrize("emotion", list(Emotion), ids=lambda value: value.value)
def test_presentation_shape(emotion: Emotion) -> None:
    got = presentation(emotion)
    assert got.label.strip()
    assert len(got.emoji) == 1
    assert re.fullmatch(r"#[0-9A-F]{6}", got.color)


def test_presentation_is_immutable() -> None:
    got = presentation(Emotion.HAPPY)
    with pytest.raises(FrozenInstanceError):
        got.label = "悲伤"  # type: ignore[misc]


@pytest.mark.parametrize("bad_input", ["happy", None, 1], ids=["str", "none", "int"])
def test_presentation_rejects_non_emotion(bad_input: object) -> None:
    with pytest.raises(TypeError, match="Emotion"):
        presentation(bad_input)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# G79–G80：结果不变量与不可变性
# ---------------------------------------------------------------------------

INVARIANT_INPUTS: tuple[str, ...] = (
    "开心",
    "难过",
    "生气",
    "惊讶",
    "平静",
    "😊",
    "not happy but wonderful",
    "开心😊 平静",
    "",
    " \t\n",
    "这是一段很长的文本。" * 1000,
    *NEUTRALS,
)


@pytest.mark.parametrize("text", INVARIANT_INPUTS, ids=range(len(INVARIANT_INPUTS)))
def test_result_invariants(text: str) -> None:
    result = detect_emotion(text)
    assert isinstance(result, EmotionResult)
    assert isinstance(result.emotion, Emotion)
    assert 0.0 <= result.intensity <= 1.0
    assert round(result.intensity, 2) == result.intensity
    assert isinstance(result.matched_keywords, tuple)
    assert len(set(result.matched_keywords)) == len(result.matched_keywords)
    assert result.source == "rule"


def test_result_is_frozen() -> None:
    result = detect_emotion("开心")
    with pytest.raises(FrozenInstanceError):
        result.emotion = Emotion.SAD  # type: ignore[misc]


# ---------------------------------------------------------------------------
# G81–G85、G97–G100：词典、导出与枚举精确断言
# ---------------------------------------------------------------------------

EXPECTED_LEXICON: tuple[tuple[str, Emotion, float], ...] = (
    # happy（22）
    ("开心", Emotion.HAPPY, 1.0),
    ("高兴", Emotion.HAPPY, 1.0),
    ("快乐", Emotion.HAPPY, 1.0),
    ("幸福", Emotion.HAPPY, 1.0),
    ("兴奋", Emotion.HAPPY, 1.0),
    ("愉快", Emotion.HAPPY, 1.0),
    ("满意", Emotion.HAPPY, 0.5),
    ("太好了", Emotion.HAPPY, 1.0),
    ("太棒了", Emotion.HAPPY, 1.0),
    ("哈哈", Emotion.HAPPY, 1.0),
    ("嘻嘻", Emotion.HAPPY, 0.5),
    ("笑", Emotion.HAPPY, 0.5),
    ("happy", Emotion.HAPPY, 1.0),
    ("glad", Emotion.HAPPY, 1.0),
    ("joyful", Emotion.HAPPY, 1.0),
    ("wonderful", Emotion.HAPPY, 1.0),
    ("great", Emotion.HAPPY, 0.5),
    ("awesome", Emotion.HAPPY, 1.0),
    ("love", Emotion.HAPPY, 1.0),
    ("yay", Emotion.HAPPY, 1.0),
    ("😊", Emotion.HAPPY, 1.5),
    ("😄", Emotion.HAPPY, 1.5),
    # sad（23）
    ("难过", Emotion.SAD, 1.0),
    ("伤心", Emotion.SAD, 1.0),
    ("悲伤", Emotion.SAD, 1.0),
    ("失落", Emotion.SAD, 0.5),
    ("沮丧", Emotion.SAD, 1.0),
    ("郁闷", Emotion.SAD, 0.5),
    ("委屈", Emotion.SAD, 0.5),
    ("哭", Emotion.SAD, 0.5),
    ("想哭", Emotion.SAD, 1.0),
    ("遗憾", Emotion.SAD, 0.5),
    ("绝望", Emotion.SAD, 1.0),
    ("心痛", Emotion.SAD, 1.0),
    ("唉", Emotion.SAD, 0.5),
    ("sad", Emotion.SAD, 1.0),
    ("unhappy", Emotion.SAD, 1.0),
    ("depressed", Emotion.SAD, 1.0),
    ("cry", Emotion.SAD, 0.5),
    ("lonely", Emotion.SAD, 1.0),
    ("miserable", Emotion.SAD, 1.0),
    ("heartbroken", Emotion.SAD, 1.0),
    ("😢", Emotion.SAD, 1.5),
    ("😭", Emotion.SAD, 1.5),
    ("💔", Emotion.SAD, 1.5),
    # angry（19）
    ("生气", Emotion.ANGRY, 1.0),
    ("愤怒", Emotion.ANGRY, 1.0),
    ("恼火", Emotion.ANGRY, 1.0),
    ("讨厌", Emotion.ANGRY, 0.5),
    ("烦躁", Emotion.ANGRY, 0.5),
    ("火大", Emotion.ANGRY, 1.0),
    ("气死", Emotion.ANGRY, 1.0),
    ("可恶", Emotion.ANGRY, 1.0),
    ("受不了", Emotion.ANGRY, 0.5),
    ("恨", Emotion.ANGRY, 1.0),
    ("气人", Emotion.ANGRY, 1.0),
    ("angry", Emotion.ANGRY, 1.0),
    ("mad", Emotion.ANGRY, 0.5),
    ("furious", Emotion.ANGRY, 1.0),
    ("annoyed", Emotion.ANGRY, 0.5),
    ("hate", Emotion.ANGRY, 1.0),
    ("😠", Emotion.ANGRY, 1.5),
    ("😡", Emotion.ANGRY, 1.5),
    ("🤬", Emotion.ANGRY, 1.5),
    # surprised（22）
    ("惊讶", Emotion.SURPRISED, 1.0),
    ("吃惊", Emotion.SURPRISED, 1.0),
    ("震惊", Emotion.SURPRISED, 1.0),
    ("意外", Emotion.SURPRISED, 0.5),
    ("没想到", Emotion.SURPRISED, 1.0),
    ("竟然", Emotion.SURPRISED, 0.5),
    ("居然", Emotion.SURPRISED, 0.5),
    ("哇", Emotion.SURPRISED, 1.0),
    ("天哪", Emotion.SURPRISED, 1.0),
    ("不敢相信", Emotion.SURPRISED, 1.0),
    ("惊喜", Emotion.SURPRISED, 0.5),
    ("surprised", Emotion.SURPRISED, 1.0),
    ("shocked", Emotion.SURPRISED, 1.0),
    ("wow", Emotion.SURPRISED, 1.0),
    ("amazing", Emotion.SURPRISED, 0.5),
    ("unexpected", Emotion.SURPRISED, 0.5),
    ("whoa", Emotion.SURPRISED, 0.5),
    ("omg", Emotion.SURPRISED, 1.0),
    ("😲", Emotion.SURPRISED, 1.5),
    ("😮", Emotion.SURPRISED, 1.5),
    ("😱", Emotion.SURPRISED, 1.5),
    ("🤯", Emotion.SURPRISED, 1.5),
    # calm（19）
    ("平静", Emotion.CALM, 1.0),
    ("冷静", Emotion.CALM, 1.0),
    ("放松", Emotion.CALM, 1.0),
    ("安心", Emotion.CALM, 1.0),
    ("安稳", Emotion.CALM, 0.5),
    ("淡定", Emotion.CALM, 1.0),
    ("舒适", Emotion.CALM, 0.5),
    ("舒服", Emotion.CALM, 0.5),
    ("宁静", Emotion.CALM, 1.0),
    ("平和", Emotion.CALM, 1.0),
    ("还好", Emotion.CALM, 0.5),
    ("没事", Emotion.CALM, 0.5),
    ("calm", Emotion.CALM, 1.0),
    ("relaxed", Emotion.CALM, 1.0),
    ("peaceful", Emotion.CALM, 1.0),
    ("chill", Emotion.CALM, 0.5),
    ("tranquil", Emotion.CALM, 0.5),
    ("serene", Emotion.CALM, 1.0),
    ("😌", Emotion.CALM, 1.5),
)

EXPECTED_NEGATION_PHRASES: tuple[str, ...] = (
    "不开心",
    "不高兴",
    "没意思",
    "not happy",
    "don't like",
    "不快乐",
    "不满意",
    "不愉快",
)


def test_lexicon_exact_table() -> None:
    assert EMOTION_LEXICON == EXPECTED_LEXICON
    assert len(EMOTION_LEXICON) == 105
    assert NEGATION_PHRASES == EXPECTED_NEGATION_PHRASES
    assert len(NEGATION_PHRASES) == 8


def test_each_emotion_has_enough_entries() -> None:
    for emotion in Emotion:
        entries = [entry for entry in EMOTION_LEXICON if entry[1] is emotion]
        assert len(entries) >= 12, emotion
        text_only = [
            entry for entry in entries if not any(ord(char) > 0x1F000 for char in entry[0])
        ]
        assert len(text_only) >= 12, emotion


def test_lexicon_entry_invariants() -> None:
    assert len({entry[0] for entry in EMOTION_LEXICON}) == len(EMOTION_LEXICON), "词形重复"
    for token, _emotion, weight in EMOTION_LEXICON:
        assert token
        assert weight in {0.5, 1.0, 1.5}
    for phrase in NEGATION_PHRASES:
        assert phrase
        assert phrase not in {entry[0] for entry in EMOTION_LEXICON}, "否定短语不得重复计分"


def test_exclusion_phrases_exact() -> None:
    from emowall.emotion.lexicon import EXCLUSION_PHRASES

    assert EXCLUSION_PHRASES == ("生气勃勃", "别生气", "笑话", "开心果", "not great")
    lexicon_tokens = {entry[0] for entry in EMOTION_LEXICON}
    for phrase in EXCLUSION_PHRASES:
        assert phrase
        assert phrase not in lexicon_tokens, "排除短语不得与情感词重复"
        assert phrase not in NEGATION_PHRASES, "排除短语不得与否定短语重复"


def test_neutral_corpus_is_disjoint_from_lexicon() -> None:
    from emowall.emotion.detector import _normalize

    entries = EMOTION_LEXICON + tuple((phrase, Emotion.SAD, 1.0) for phrase in NEGATION_PHRASES)
    for text in NEUTRALS:
        normalized = _normalize(text)
        for token, _emotion, _weight in entries:
            assert token not in normalized, f"中性语料意外命中 {token!r}：{text!r}"


def test_package_exports_exact() -> None:
    assert emotion_pkg.__all__ == [
        "Emotion",
        "EmotionResult",
        "EmotionPresentation",
        "detect_emotion",
        "presentation",
    ]
    for name in emotion_pkg.__all__:
        assert getattr(emotion_pkg, name)


def test_emotion_enum_identities() -> None:
    assert Emotion.HAPPY == "happy"
    assert Emotion.HAPPY.value == "happy"
    assert Emotion("happy") is Emotion.HAPPY
    assert [emotion.value for emotion in Emotion] == [
        "happy",
        "calm",
        "sad",
        "angry",
        "surprised",
    ]

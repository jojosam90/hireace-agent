import pytest

from transcript_guard import UNCLEAR, clean_agent_text, clean_user_transcript, has_foreign_script


@pytest.mark.parametrize(
    "text",
    [
        "Open wikipedia.org please.",
        "What's 2 + 2? It's $5, 10% off — ok!",
        "Café crème, naïve résumé",  # accented Latin is still Latin script
        "",
    ],
)
def test_english_text_passes_through(text: str) -> None:
    assert clean_user_transcript(text, "en") == text


@pytest.mark.parametrize(
    ("raw", "shown"),
    [
        ("um so can you uh find the the acme proposal", "So can you find the acme proposal"),
        ("Hmm, open, open Excel please", "Open Excel please"),
        ("umbrella and hummus", "Umbrella and hummus"),  # real words stay
        ("uh um", "(Sorry, I didn't catch that clearly)"),
    ],
)
def test_mumbling_is_tidied(raw: str, shown: str) -> None:
    assert clean_user_transcript(raw, "en") == shown


def test_chinese_fillers_are_dropped() -> None:
    assert clean_user_transcript("嗯 帮 我 呃 打 开 表 格", "zh") == "帮我打开表格"


@pytest.mark.parametrize(
    "text",
    [
        "계 오픈 샌드박스 폼",  # Korean script for "open sandbox"
        "Open 샌드박스 please",  # mixed: still not trustworthy
        "привет как дела",  # Cyrillic
        "こんにちは",  # Japanese kana
        "可以打开沙盒",  # Chinese in English mode
    ],
)
def test_other_scripts_in_english_mode_become_a_clear_notice(text: str) -> None:
    assert clean_user_transcript(text, "en") == UNCLEAR["en"]


@pytest.mark.parametrize(
    "text",
    ["可以帮我打开沙盒吗？", "打开 YouTube 搜索音乐", "去 trip.com 找机票"],
)
def test_chinese_mode_allows_chinese_and_english(text: str) -> None:
    assert clean_user_transcript(text, "zh") == text


@pytest.mark.parametrize("text", ["계 오픈 샌드박스", "привет"])
def test_other_scripts_in_chinese_mode_become_a_clear_notice(text: str) -> None:
    assert clean_user_transcript(text, "zh") == UNCLEAR["zh"]


def test_agent_text_drops_stray_foreign_fragments_but_keeps_the_sentence() -> None:
    assert clean_agent_text("Of course, Sir 샌드박스. Opening it now.", "en") == (
        "Of course, Sir. Opening it now."
    )
    assert clean_agent_text("好的，先生。", "zh") == "好的，先生。"


def test_detection() -> None:
    assert has_foreign_script("abc 한", "en")
    assert not has_foreign_script("abc", "en")
    assert not has_foreign_script("中文 abc", "zh")


# --- Readable Chinese for both apps -------------------------------------------


@pytest.mark.parametrize(
    ("raw", "shown"),
    [
        ("可 以 打 开 沙 盒 。", "可以打开沙盒。"),
        ("您好, 先生。 随时 准备 为您 效劳?", "您好，先生。随时准备为您效劳？"),
        ("我是由 Google 训练 的大型 语言 模型。", "我是由 Google 训练的大型语言模型。"),
    ],
)
def test_chinese_transcripts_are_tidied(raw: str, shown: str) -> None:
    assert clean_user_transcript(raw, "zh") == shown


def test_streamed_chinese_chunks_are_joined_without_stray_spaces() -> None:
    from transcript_guard import ChunkCleaner

    cleaner = ChunkCleaner("zh")
    chunks = ["您好， 先生。", " 随时", " 准备", " 为您 效劳，", " 请问 用 Google 吗?"]
    assert "".join(cleaner.clean(c) for c in chunks) == "您好，先生。随时准备为您效劳，请问用 Google 吗？"


def test_english_chunks_are_untouched() -> None:
    from transcript_guard import ChunkCleaner

    cleaner = ChunkCleaner("en")
    chunks = ["Good day,", " Sir.", " Opening", " it now."]
    assert "".join(cleaner.clean(c) for c in chunks) == "Good day, Sir. Opening it now."

"""001 FR-026, ADR-077: greeting detection, once-per-viewer rule and template replies."""

from pathlib import Path

import pytest

from ai_live.comments.greetings import GreetingReplier, GreetingRules, is_greeting_comment
from ai_live.core.models import Comment, Priority
from ai_live.products.docx_loader import load_catalog
from fixtures.content_builder import valid_docx

RULES = Path(__file__).resolve().parents[2] / "data" / "rules" / "greetings.json"


class Clock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


def make(text: str, author: str = "Lan") -> Comment:
    return Comment(id=text, source="mock", author=author, text=text, received_at=0.0)


@pytest.fixture
def rules() -> GreetingRules:
    return GreetingRules.from_file(RULES)


@pytest.mark.parametrize(
    "text", ["hi", "Hello shop", "hii shop ơi", "Chào shop", "chao shop", "xin chào mọi người", "alo alo", "hey!!"]
)
def test_short_greetings_are_detected(rules, text):
    assert rules.is_greeting(text, Priority.LOW)


@pytest.mark.parametrize(
    "text",
    [
        "cháo ngon",  # porridge, not a greeting: matching keeps diacritics
        "hì hì",  # a laugh
        "hihi",
        "shop đẹp quá",
        "hi shop ơi hôm nay em muốn hỏi chút về cái thùng này nha",  # long: the LLM answers it
    ],
)
def test_non_greetings_are_not_detected(rules, text):
    assert not rules.is_greeting(text, Priority.LOW)


def test_greeting_with_a_question_goes_to_the_llm(rules):
    assert not rules.is_greeting("chào shop giá bao nhiêu", Priority.HIGH)
    assert not rules.is_greeting("hi shop còn hàng không", Priority.MEDIUM)


def test_check_tags_once_then_reports_repeat_until_window_passes():
    clock = Clock()
    rules = GreetingRules(["hi", "hello"], max_words=8, repeat_s=600, clock=clock)
    first = rules.check(make("hi"), Priority.LOW)
    assert first.is_greeting and not first.repeat
    assert is_greeting_comment(first.comment)
    clock.now += 100
    assert rules.check(make("hello shop"), Priority.LOW).repeat
    assert not rules.check(make("hello", author="Mai"), Priority.LOW).repeat
    clock.now += 600
    assert not rules.check(make("hi lại nè"), Priority.LOW).repeat


def test_non_greeting_comment_is_returned_untouched(rules):
    comment = make("shop đẹp quá")
    result = rules.check(comment, Priority.LOW)
    assert result.comment is comment and not result.is_greeting


def test_replier_names_viewer_and_main_product_and_rotates():
    catalog = load_catalog(valid_docx(), "valid.docx", 5_000_000)
    replier = GreetingReplier.from_file(RULES)
    first = replier.sentences(make("hi"), catalog)
    second = replier.sentences(make("hi"), catalog)
    assert len(first) == 2
    assert "bạn Lan" in first[0]
    assert catalog.primary.name in first[1]
    assert first[0] != second[0]
    assert all(s[0].isupper() for s in first + second)


def test_replier_uses_plain_ban_for_unsafe_name():
    catalog = load_catalog(valid_docx(), "valid.docx", 5_000_000)
    sentences = GreetingReplier(["Chào {who} nha."]).sentences(make("hi", author="http://spam.vn"), catalog)
    assert sentences == ["Chào bạn nha."]


def test_replier_needs_a_reply():
    with pytest.raises(ValueError):
        GreetingReplier([])

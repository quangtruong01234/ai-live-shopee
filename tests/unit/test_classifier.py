"""T059: rule-based priority classifier (FR-003, research R9; table in docs/ARCHITECTURE.md §5)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ai_live.comments.classifier import PriorityClassifier
from ai_live.core.models import Priority

RULES = Path(__file__).resolve().parents[2] / "data" / "rules" / "priority_keywords.json"


@pytest.fixture(scope="module")
def classifier() -> PriorityClassifier:
    return PriorityClassifier.from_file(RULES)


@pytest.mark.parametrize(
    "text",
    [
        "giá bao nhiêu vậy shop?",
        "gia bao nhieu",
        "bn vậy shop",
        "có khuyến mãi không",
        "co km ko shop",
        "mua ở đâu vậy",
        "chốt đơn cho em 2 hộp",
        "size L còn không",
        "con hang khong shop",
        "có màu hồng không",
        "ship mấy ngày?",
        "chào shop, giá bao nhiêu?",
    ],
)
def test_high_priority(classifier, text):
    assert classifier.classify(text) is Priority.HIGH


@pytest.mark.parametrize(
    "text",
    [
        "chất liệu gì vậy?",
        "chat lieu gi vay",
        "dùng cho da dầu được không",
        "thành phần có gì",
        "công dụng là gì",
        "so với loại kia khác gì",
        "hạn sử dụng bao lâu",
    ],
)
def test_medium_priority(classifier, text):
    assert classifier.classify(text) is Priority.MEDIUM


@pytest.mark.parametrize("text", ["chào shop", "chao shop", "hello shop", "shop xinh quá", "đẹp quá", "hi mọi người"])
def test_low_priority(classifier, text):
    assert classifier.classify(text) is Priority.LOW


@pytest.mark.parametrize("text", ["cái này sao vậy?", "?", "dùng được ko", "loại nào tốt k", "là gì thế"])
def test_question_without_keyword_is_medium(classifier, text):
    assert classifier.classify(text) is Priority.MEDIUM


def test_keywords_match_whole_words_only(tmp_path):
    rules = tmp_path / "rules.json"
    rules.write_text(json.dumps({"high": ["gia"], "medium": [], "question_words": []}), encoding="utf-8")
    c = PriorityClassifier.from_file(rules)
    assert c.classify("giá nhiêu") is Priority.HIGH
    assert c.classify("giay đẹp") is Priority.LOW


def test_high_is_checked_before_medium(tmp_path):
    rules = tmp_path / "rules.json"
    rules.write_text(json.dumps({"high": ["gia"], "medium": ["chat lieu"], "question_words": []}), encoding="utf-8")
    c = PriorityClassifier.from_file(rules)
    assert c.classify("chất liệu gì, giá sao") is Priority.HIGH


def test_from_settings_reads_rules_path(settings, tmp_path):
    rules = tmp_path / "rules.json"
    rules.write_text(json.dumps({"high": ["xyz"], "medium": [], "question_words": []}), encoding="utf-8")
    c = PriorityClassifier.from_settings(settings.model_copy(update={"priority_rules_path": rules}))
    assert c.classify("xyz") is Priority.HIGH

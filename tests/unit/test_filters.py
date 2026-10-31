"""T058: comment filter (FR-002, research R9; data-model.md §1 for the author rule)."""

from __future__ import annotations

import pytest

from ai_live.comments.filters import CommentFilter, load_word_list
from ai_live.core.models import Comment, DropReason

BANNED = ["du ma", "vcl"]


def make_filter(clock, **kwargs) -> CommentFilter:
    return CommentFilter(banned_words=BANNED, clock=clock, **kwargs)


def make_comment(clock, text: str, author: str = "Lan", cid: str = "c1") -> Comment:
    return Comment(id=cid, source="mock", author=author, text=text, received_at=clock())


def test_normalizes_nfc_and_collapses_whitespace(clock):
    decomposed = "giá   bao\t\tnhiêu\n vậy"
    result = make_filter(clock).check(make_comment(clock, decomposed))
    assert result.drop_reason is None
    assert result.comment.text == "giá bao nhiêu vậy"


def test_long_comment_is_truncated_and_flagged(clock):
    result = make_filter(clock, max_chars=300).check(make_comment(clock, "a" * 500))
    assert result.drop_reason is None
    assert len(result.comment.text) == 300
    assert result.comment.meta["truncated"] is True


def test_short_comment_is_not_flagged_truncated(clock):
    result = make_filter(clock).check(make_comment(clock, "giá bao nhiêu?"))
    assert result.comment.meta["truncated"] is False


@pytest.mark.parametrize("text", ["", "   ", "😍😍😍", "👍 ❤️ !!!", "?", "a 🔥"])
def test_empty_or_emoji_only_is_dropped_empty(clock, text):
    assert make_filter(clock).check(make_comment(clock, text)).drop_reason is DropReason.EMPTY


@pytest.mark.parametrize(
    "text",
    [
        "xem ở đây http://spam.vn nha",
        "https://a.b/c",
        "vào www.abc.xyz mua",
        "shopabc.com giá rẻ hơn",
        "ghé tiemxinh.vn",
    ],
)
def test_link_is_dropped_link(clock, text):
    assert make_filter(clock).check(make_comment(clock, text)).drop_reason is DropReason.LINK


@pytest.mark.parametrize("text", ["đụ má shop", "du ma shop", "ĐỤ MÁ", "vcl giá cao thế", "giá cao vcl"])
def test_profanity_with_or_without_diacritics_is_dropped(clock, text):
    assert make_filter(clock).check(make_comment(clock, text)).drop_reason is DropReason.PROFANITY


def test_profanity_matches_whole_words_only(clock):
    # "vcl" inside a longer token is not the banned word.
    assert make_filter(clock).check(make_comment(clock, "mã avclx còn không")).drop_reason is None


def test_same_author_same_text_within_window_is_duplicate(clock):
    f = make_filter(clock, dedup_window_s=60)
    assert f.check(make_comment(clock, "giá bao nhiêu?", cid="1")).drop_reason is None
    clock.advance(30)
    # Diacritics, case and punctuation do not make it a different comment.
    assert f.check(make_comment(clock, "Gia bao nhieu", cid="2")).drop_reason is DropReason.DUPLICATE


def test_other_author_is_not_duplicate(clock):
    f = make_filter(clock)
    f.check(make_comment(clock, "giá bao nhiêu?", author="Lan", cid="1"))
    assert f.check(make_comment(clock, "giá bao nhiêu?", author="Huy", cid="2")).drop_reason is None


def test_same_text_after_window_is_not_duplicate(clock):
    f = make_filter(clock, dedup_window_s=60)
    f.check(make_comment(clock, "giá bao nhiêu?", cid="1"))
    clock.advance(61)
    assert f.check(make_comment(clock, "giá bao nhiêu?", cid="2")).drop_reason is None


def test_dropped_comment_does_not_count_for_duplicate(clock):
    f = make_filter(clock)
    assert f.check(make_comment(clock, "vcl http://a.vn", cid="1")).drop_reason is DropReason.LINK
    assert f.check(make_comment(clock, "vcl http://a.vn", cid="2")).drop_reason is DropReason.LINK


def test_link_beats_profanity(clock):
    # Every link has at least 2 letters, so "empty" can never compete with the later rules.
    assert make_filter(clock).check(make_comment(clock, "vcl http://a.vn")).drop_reason is DropReason.LINK


def test_profanity_beats_duplicate(clock):
    f = make_filter(clock)
    f.check(make_comment(clock, "giá vcl", cid="1"))
    assert f.check(make_comment(clock, "giá vcl", cid="2")).drop_reason is DropReason.PROFANITY


@pytest.mark.parametrize("author", ["", "   ", "http://spam.vn", "shop www.abc.com", "Lan vcl", "đụ má"])
def test_unsafe_author_is_replaced_but_comment_kept(clock, author):
    result = make_filter(clock).check(make_comment(clock, "giá bao nhiêu?", author=author))
    assert result.drop_reason is None
    assert result.comment.author == "bạn"


def test_safe_author_is_kept(clock):
    result = make_filter(clock).check(make_comment(clock, "giá bao nhiêu?", author="Lan Anh"))
    assert result.comment.author == "Lan Anh"


def test_comment_id_and_received_at_are_preserved(clock):
    comment = make_comment(clock, "giá  bao nhiêu?", cid="abc")
    result = make_filter(clock).check(comment)
    assert result.comment.id == "abc"
    assert result.comment.received_at == comment.received_at


def test_load_word_list_skips_comments_and_blank_lines(tmp_path):
    path = tmp_path / "words.txt"
    path.write_text("# header\n\ndu ma\n  VCL  \n", encoding="utf-8")
    assert load_word_list(path) == ["du ma", "vcl"]


def test_from_settings_reads_profanity_file(settings, tmp_path, clock):
    path = tmp_path / "words.txt"
    path.write_text("chuoi cam\n", encoding="utf-8")
    s = settings.model_copy(update={"profanity_list_path": path})
    f = CommentFilter.from_settings(s, clock=clock)
    assert f.check(make_comment(clock, "chuỗi cấm đây")).drop_reason is DropReason.PROFANITY


def test_repo_profanity_list_loads_and_spares_common_words(settings, clock):
    # Words that collide with everyday words once diacritics are stripped must not be in the list.
    f = CommentFilter.from_settings(settings, clock=clock)
    for i, text in enumerate(["đeo kính được không", "size lớn có không", "các màu nào", "buổi live sau"]):
        assert f.check(make_comment(clock, text, cid=str(i))).drop_reason is None, text

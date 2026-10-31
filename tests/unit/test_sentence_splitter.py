"""T031: tách câu khi streaming (research R7, FR-013)."""

from __future__ import annotations

from ai_live.brain.sentence_splitter import SentenceSplitter


def _split_stream(deltas: list[str], **kwargs) -> list[str]:
    splitter = SentenceSplitter(**kwargs)
    out: list[str] = []
    for d in deltas:
        out += splitter.feed(d)
    return out + splitter.flush()


def test_splits_on_terminator_followed_by_space():
    s = SentenceSplitter()
    assert s.feed("Dạ chào bạn Lan. Kem") == ["Dạ chào bạn Lan."]
    assert s.feed(" giá 250.000đ nha! Bạn ") == ["Kem giá 250.000đ nha!"]
    assert s.feed("chọn loại nào ạ? ") == ["Bạn chọn loại nào ạ?"]
    assert s.flush() == []


def test_waits_for_whitespace_before_cutting():
    s = SentenceSplitter()
    # Dấu chấm ở cuối delta chưa chắc là hết câu (có thể là "250." của "250.000").
    assert s.feed("Kem giá 250.") == []
    assert s.feed("000đ nha.") == []
    assert s.flush() == ["Kem giá 250.000đ nha."]


def test_ellipsis_and_newline():
    assert _split_stream(["Dạ để em xem… Kem này dùng tốt ạ"]) == ["Dạ để em xem…", "Kem này dùng tốt ạ"]
    assert _split_stream(["Câu thứ nhất\nCâu thứ hai"]) == ["Câu thứ nhất", "Câu thứ hai"]


def test_does_not_split_inside_amount():
    out = _split_stream(["Toner Z giá 1.250.000đ nha bạn. ", "Cảm ơn bạn ạ."])
    assert out == ["Toner Z giá 1.250.000đ nha bạn.", "Cảm ơn bạn ạ."]


def test_does_not_split_after_vv():
    out = _split_stream(["Kem hợp da dầu, da khô v.v. và cả da hỗn hợp nha. Bạn thử nha."])
    assert out == ["Kem hợp da dầu, da khô v.v. và cả da hỗn hợp nha.", "Bạn thử nha."]


def test_short_sentence_merges_with_next():
    assert _split_stream(["Dạ. Kem giá 250.000đ ạ. "]) == ["Dạ. Kem giá 250.000đ ạ."]


def test_long_sentence_cut_at_last_comma():
    first = "Kem chống nắng dạng sữa " + "rất mỏng nhẹ " * 12 + ","
    rest = " thấm nhanh " * 10
    s = SentenceSplitter(max_chars=200)
    out = s.feed(first + rest)
    assert len(out) == 1
    assert out[0] == first.strip()
    assert len(out[0]) <= 200
    assert s.flush() == [rest.strip()]


def test_long_sentence_without_comma_cut_at_space():
    s = SentenceSplitter(max_chars=50)
    out = s.feed("một " * 30)
    assert out and all(len(x) <= 50 for x in out)
    assert " ".join(out + s.flush()).split() == ["một"] * 30


def test_flush_returns_remainder_and_resets():
    s = SentenceSplitter()
    s.feed("Dạ bạn Lan ơi")
    assert s.flush() == ["Dạ bạn Lan ơi"]
    assert s.flush() == []


def test_empty_and_whitespace_only():
    assert _split_stream(["", "   ", "\n"]) == []


def test_multiple_terminators():
    assert _split_stream(["Thật hả?! Dạ đúng rồi ạ."]) == ["Thật hả?!", "Dạ đúng rồi ạ."]

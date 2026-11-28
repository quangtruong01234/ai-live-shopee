"""001 FR-027, ADR-077: per-viewer rate limit."""

from ai_live.comments.author_limits import AuthorLimiter
from ai_live.core.models import Comment


class Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


def make(author: str, text: str = "x", key: str | None = None) -> Comment:
    meta = {"author_key": key} if key is not None else {}
    return Comment(id=text, source="mock", author=author, text=text, received_at=0.0, meta=meta)


def test_fourth_comment_in_window_is_refused_and_mutes():
    clock = Clock()
    limiter = AuthorLimiter(max_comments=3, window_s=30, mute_s=120, clock=clock)
    assert [limiter.allow(make("Tú")) for _ in range(3)] == [True, True, True]
    assert limiter.allow(make("Tú")) is False
    assert limiter.muted() == ["tu"]
    # Others are not affected.
    assert limiter.allow(make("Lan")) is True


def test_mute_holds_then_lifts_without_extending():
    clock = Clock()
    limiter = AuthorLimiter(max_comments=3, window_s=30, mute_s=120, clock=clock)
    for _ in range(4):
        limiter.allow(make("Tú"))
    clock.now += 60
    assert limiter.allow(make("Tú")) is False  # still muted; this one does not push the end back
    clock.now += 61
    assert limiter.allow(make("Tú")) is True
    assert limiter.muted() == []


def test_slow_viewer_is_never_limited():
    clock = Clock()
    limiter = AuthorLimiter(max_comments=3, window_s=30, mute_s=120, clock=clock)
    for _ in range(20):
        assert limiter.allow(make("Lan")) is True
        clock.now += 11


def test_author_key_from_source_beats_the_name():
    clock = Clock()
    limiter = AuthorLimiter(max_comments=1, window_s=30, mute_s=120, clock=clock)
    assert limiter.allow(make("Lan", key="u1")) is True
    # Same display name, different account: counted apart.
    assert limiter.allow(make("Lan", key="u2")) is True
    assert limiter.allow(make("Lan", key="u1")) is False


def test_name_match_form_groups_spellings():
    clock = Clock()
    limiter = AuthorLimiter(max_comments=1, window_s=30, mute_s=120, clock=clock)
    assert limiter.allow(make("Tú")) is True
    assert limiter.allow(make("tu")) is False


# ---------- 001 FR-029, ADR-078: operator block ----------


def test_manual_block_holds_for_its_minutes_and_lists_the_viewer():
    clock = Clock()
    limiter = AuthorLimiter(max_comments=3, window_s=30, mute_s=120, clock=clock)
    limiter.block("tu", 5, author="Tú")
    assert limiter.blocked(make("Tú")) is True
    assert limiter.blocked(make("Lan")) is False
    [entry] = limiter.viewers()
    assert (entry.author_key, entry.author, entry.kind, entry.remaining_s) == ("tu", "Tú", "manual", 300)
    clock.now += 301
    assert limiter.blocked(make("Tú")) is False
    assert limiter.viewers() == []


def test_session_block_has_no_end():
    clock = Clock()
    limiter = AuthorLimiter(clock=clock)
    limiter.block("tu", None)
    clock.now += 10_000_000
    assert limiter.blocked(make("Tú")) is True
    assert limiter.viewers()[0].to_json()["remaining_s"] is None


def test_unblock_lifts_block_and_auto_mute_and_resets_the_count():
    clock = Clock()
    limiter = AuthorLimiter(max_comments=3, window_s=30, mute_s=120, clock=clock)
    for _ in range(4):
        limiter.allow(make("Tú"))
    assert [v.kind for v in limiter.viewers()] == ["auto"]
    assert limiter.viewers()[0].author == "Tú"
    limiter.block("tu", 30)
    # Blocked and muted at once: listed once, as manual.
    assert [v.kind for v in limiter.viewers()] == ["manual"]
    assert limiter.unblock("tu") is True
    assert limiter.viewers() == [] and limiter.muted() == []
    assert limiter.allow(make("Tú")) is True
    assert limiter.unblock("tu") is False


def test_version_moves_on_auto_mute_block_and_unblock_only():
    clock = Clock()
    limiter = AuthorLimiter(max_comments=1, window_s=30, mute_s=120, clock=clock)
    v0 = limiter.version
    limiter.allow(make("Tú"))
    assert limiter.version == v0
    limiter.allow(make("Tú"))
    assert limiter.version == v0 + 1
    limiter.block("lan", 5)
    limiter.unblock("lan")
    limiter.unblock("nobody")
    assert limiter.version == v0 + 3

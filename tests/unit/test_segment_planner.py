"""T019 SegmentPlanner rotation and T061 operator choice (004 US1, US5; FR-004, FR-005, FR-018, research R5, R6,
contracts/adapters.md §5).

Catalogs are built from `Product` objects directly: the planner only reads the catalog, so no `.docx` is needed.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

import pytest

from ai_live.core.models import ROTATION_TOPICS, SegmentOrigin, Topic
from ai_live.director.segment_planner import PlannedSlot, SegmentPlanner, TopicUnavailable
from ai_live.products.models import Product, ProductCatalog, Variant

T = Topic
ALL_TOPICS = tuple(ROTATION_TOPICS)


def _product(pid: str, *, primary: bool = False, **overrides) -> Product:
    """A product with data for every rotation topic; pass `field=empty` to remove one."""
    fields = {
        "id": pid,
        "name": f"Sản phẩm {pid}",
        "is_primary": primary,
        "description": "Mô tả ngắn.",
        "intro": "Bài giới thiệu.",
        "price": 150_000,
        "specs": (("Dung tích", "50 ml"),),
        "faq": (("Dùng cho da dầu được không?", "Dạ được."),),
        "promotions": ("Mua 2 tặng 1",),
    }
    fields.update(overrides)
    return Product(**fields)


def _catalog(*products, version: str = "v1") -> ProductCatalog:
    return ProductCatalog(
        version=version,
        source_name="test.docx",
        loaded_at=datetime(2026, 11, 1, tzinfo=UTC),
        products=tuple(products),
    )


def _three_products(version: str = "v1") -> ProductCatalog:
    return _catalog(_product("p1", primary=True), _product("p2"), _product("p3"), version=version)


@dataclass(frozen=True)
class _BareProduct:
    """Stands in for a product the current template cannot express: no price and no text (R5 `TODO`).

    `Product` requires a price or variants, so only a stub reaches the "single combination" case.
    """

    id: str
    name: str = "Sản phẩm trống"
    is_primary: bool = True
    description: str = ""
    intro: str = ""
    price: int | None = None
    variants: tuple = ()
    specs: tuple = ()
    faq: tuple = ()
    promotions: tuple = ()


# --- available_topics (R5) ---


def test_full_product_has_every_rotation_topic_in_r5_order():
    planner = SegmentPlanner(_three_products(), primary_share=0.5)

    assert planner.available_topics("p1") == ALL_TOPICS
    assert ALL_TOPICS == (T.INTRO, T.HIGHLIGHTS, T.SPECS, T.PRICE, T.PROMOTION, T.FAQ, T.CALL_TO_ACTION)


def test_opening_and_closing_are_never_rotation_topics():
    planner = SegmentPlanner(_three_products(), primary_share=0.5)

    for topics in planner.availability().values():
        assert T.OPENING not in topics
        assert T.CLOSING not in topics


def test_no_promotion_means_no_promotion_topic():
    planner = SegmentPlanner(_catalog(_product("p1", primary=True, promotions=())), primary_share=0.5)

    assert T.PROMOTION not in planner.available_topics("p1")


def test_no_specs_and_no_faq_remove_those_topics():
    planner = SegmentPlanner(_catalog(_product("p1", primary=True, specs=(), faq=())), primary_share=0.5)

    topics = planner.available_topics("p1")
    assert T.SPECS not in topics
    assert T.FAQ not in topics
    assert T.PRICE in topics


def test_no_description_removes_highlights_but_intro_text_keeps_intro():
    planner = SegmentPlanner(_catalog(_product("p1", primary=True, description="")), primary_share=0.5)

    topics = planner.available_topics("p1")
    assert T.HIGHLIGHTS not in topics
    assert T.INTRO in topics


def test_intro_available_from_description_alone():
    planner = SegmentPlanner(_catalog(_product("p1", primary=True, intro="")), primary_share=0.5)

    assert T.INTRO in planner.available_topics("p1")


def test_variants_count_as_price():
    product = _product("p1", primary=True, price=None, variants=(Variant("50 ml", 250_000),))
    planner = SegmentPlanner(_catalog(product), primary_share=0.5)

    assert T.PRICE in planner.available_topics("p1")


def test_no_price_means_no_price_topic_but_call_to_action_stays():
    """US1 #4. A valid file always has a price, so this guards against a future template change (R5)."""
    planner = SegmentPlanner(_catalog(_BareProduct("p1")), primary_share=0.5)

    assert planner.available_topics("p1") == (T.CALL_TO_ACTION,)


def test_unknown_product_has_no_topics():
    planner = SegmentPlanner(_three_products(), primary_share=0.5)

    assert planner.available_topics("missing") == ()


def test_availability_lists_every_product():
    planner = SegmentPlanner(
        _catalog(_product("p1", primary=True), _product("p2", specs=(), faq=(), promotions=())), primary_share=0.5
    )

    assert planner.availability() == {
        "p1": ALL_TOPICS,
        "p2": (T.INTRO, T.HIGHLIGHTS, T.PRICE, T.CALL_TO_ACTION),
    }


# --- next_slot rotation (R6) ---


def _run(planner: SegmentPlanner, n: int) -> list[PlannedSlot]:
    return [planner.next_slot() for _ in range(n)]


@pytest.mark.parametrize("share", [0.5, 0.6, 0.7, 0.9])
def test_1000_slots_never_repeat_product_and_topic_back_to_back(share):
    slots = _run(SegmentPlanner(_three_products(), primary_share=share), 1000)

    for before, after in zip(slots, slots[1:], strict=False):
        assert (before.product_id, before.topic) != (after.product_id, after.topic)


def test_slots_are_rotation_slots_with_available_topics():
    planner = SegmentPlanner(
        _catalog(_product("p1", primary=True), _product("p2", promotions=(), specs=())), primary_share=0.5
    )

    for slot in _run(planner, 200):
        assert slot.origin is SegmentOrigin.ROTATION
        assert slot.product_id is not None
        assert slot.topic in planner.available_topics(slot.product_id)


@pytest.mark.parametrize("share", [0.5, 0.6, 0.75, 0.9])
def test_primary_share_is_at_least_the_setting(share):
    planner = SegmentPlanner(_three_products(), primary_share=share)
    n = planner.cycle_length * 50  # whole cycles, so the ratio is exact
    slots = _run(planner, n)

    primary = sum(slot.product_id == "p1" for slot in slots)
    assert primary / n >= share - 1e-9


def test_default_interleave_alternates_primary_and_secondaries():
    planner = SegmentPlanner(_three_products(), primary_share=0.5)

    assert [slot.product_id for slot in _run(planner, 8)] == ["p1", "p2", "p1", "p3", "p1", "p2", "p1", "p3"]


@pytest.mark.parametrize("share", [0.5, 0.7, 0.9])
def test_every_secondary_appears_in_every_cycle(share):
    catalog = _catalog(_product("p1", primary=True), _product("p2"), _product("p3"), _product("p4"))
    planner = SegmentPlanner(catalog, primary_share=share)
    length = planner.cycle_length
    slots = _run(planner, length * 30)

    # Any run of `cycle_length` consecutive slots is one full cycle, wherever it starts.
    for start in range(len(slots) - length + 1):
        window = {slot.product_id for slot in slots[start : start + length]}
        assert {"p2", "p3", "p4"} <= window


def test_each_product_rotates_through_its_topics_in_order():
    planner = SegmentPlanner(
        _catalog(_product("p1", primary=True), _product("p2", specs=(), faq=())), primary_share=0.5
    )
    slots = _run(planner, 40)

    p1_topics = [slot.topic for slot in slots if slot.product_id == "p1"]
    p2_topics = [slot.topic for slot in slots if slot.product_id == "p2"]
    assert p1_topics[: len(ALL_TOPICS) * 2] == list(ALL_TOPICS) * 2
    p2_available = planner.available_topics("p2")
    assert p2_topics[: len(p2_available) * 2] == list(p2_available) * 2


def test_primary_only_rotates_its_own_topics():
    planner = SegmentPlanner(_catalog(_product("p1", primary=True)), primary_share=0.5)
    slots = _run(planner, 21)

    assert {slot.product_id for slot in slots} == {"p1"}
    assert [slot.topic for slot in slots] == list(ALL_TOPICS) * 3
    for before, after in zip(slots, slots[1:], strict=False):
        assert before.topic != after.topic


def test_single_combination_catalog_allows_the_repeat():
    planner = SegmentPlanner(_catalog(_BareProduct("p1")), primary_share=0.5)
    slots = _run(planner, 5)

    assert planner.single_combination
    assert all((slot.product_id, slot.topic) == ("p1", T.CALL_TO_ACTION) for slot in slots)


def test_full_catalog_is_not_single_combination():
    assert not SegmentPlanner(_three_products(), primary_share=0.5).single_combination


# --- peek_slot ---


def test_peek_slot_does_not_consume():
    planner = SegmentPlanner(_three_products(), primary_share=0.6)

    for _ in range(30):
        peeked = planner.peek_slot()
        assert planner.peek_slot() == peeked
        assert planner.next_slot() == peeked


# --- replace_catalog ---


def test_replace_catalog_keeps_cursor_of_surviving_products():
    planner = SegmentPlanner(_three_products(), primary_share=0.5)
    slots = _run(planner, 6)  # p1, p2, p1, p3, p1, p2
    last_p1 = [slot.topic for slot in slots if slot.product_id == "p1"][-1]
    assert last_p1 == T.SPECS

    planner.replace_catalog(_catalog(_product("p1", primary=True), _product("p2"), version="v2"))
    after = _run(planner, 10)

    next_p1 = next(slot.topic for slot in after if slot.product_id == "p1")
    assert next_p1 == T.PRICE  # the topic after specs, not intro again


def test_replace_catalog_drops_removed_products():
    planner = SegmentPlanner(_three_products(), primary_share=0.5)
    _run(planner, 5)

    planner.replace_catalog(_catalog(_product("p1", primary=True), _product("p2"), version="v2"))

    assert "p3" not in planner.availability()
    assert planner.available_topics("p3") == ()
    slots = _run(planner, 200)
    assert "p3" not in {slot.product_id for slot in slots}
    for before, after in zip(slots, slots[1:], strict=False):
        assert (before.product_id, before.topic) != (after.product_id, after.topic)


def test_replace_catalog_cursor_survives_a_topic_that_lost_its_data():
    planner = SegmentPlanner(_catalog(_product("p1", primary=True)), primary_share=0.5)
    assert [slot.topic for slot in _run(planner, 5)][-1] == T.PROMOTION

    planner.replace_catalog(_catalog(_product("p1", primary=True, promotions=(), faq=()), version="v2"))

    assert planner.next_slot().topic == T.CALL_TO_ACTION  # first available topic after promotion


def test_replace_catalog_adds_new_secondary_to_the_cycle():
    planner = SegmentPlanner(_catalog(_product("p1", primary=True)), primary_share=0.5)
    _run(planner, 3)

    planner.replace_catalog(_catalog(_product("p1", primary=True), _product("p9"), version="v2"))
    slots = _run(planner, planner.cycle_length)

    assert "p9" in {slot.product_id for slot in slots}
    assert planner.availability()["p9"] == ALL_TOPICS


# --- T061: operator choice for the next segment (US5; FR-018, research R6) ---


def test_choose_product_only_takes_the_next_topic_of_that_products_cursor():
    planner = SegmentPlanner(_three_products(), primary_share=0.5)
    assert [(s.product_id, s.topic) for s in _run(planner, 2)] == [("p1", T.INTRO), ("p2", T.INTRO)]

    assert planner.choose("p2", None) == PlannedSlot("p2", T.HIGHLIGHTS, SegmentOrigin.OPERATOR)
    # A product the rotation has not reached yet starts at its first topic.
    assert planner.choose("p3", None) == PlannedSlot("p3", T.INTRO, SegmentOrigin.OPERATOR)


def test_choose_topic_only_takes_the_first_product_with_that_topic_primary_first():
    # The primary is listed last on purpose: "primary first" must not depend on the file order.
    planner = SegmentPlanner(_catalog(_product("p2"), _product("p3"), _product("p1", primary=True)), primary_share=0.5)
    assert planner.choose(None, T.FAQ) == PlannedSlot("p1", T.FAQ, SegmentOrigin.OPERATOR)

    no_promo_primary = SegmentPlanner(
        _catalog(_product("p1", primary=True, promotions=()), _product("p2", promotions=()), _product("p3")),
        primary_share=0.5,
    )
    assert no_promo_primary.choose(None, T.PROMOTION) == PlannedSlot("p3", T.PROMOTION, SegmentOrigin.OPERATOR)


def test_choose_product_and_topic_takes_exactly_that_combination():
    planner = SegmentPlanner(_three_products(), primary_share=0.5)

    assert planner.choose("p3", T.PROMOTION) == PlannedSlot("p3", T.PROMOTION, SegmentOrigin.OPERATOR)


@pytest.mark.parametrize(
    ("product_id", "topic"),
    [
        ("p2", T.PROMOTION),  # US5 #2: the product has no promotion
        ("p2", T.SPECS),
        ("missing", None),  # unknown product
        ("missing", T.INTRO),
        (None, T.FAQ),  # no product has a FAQ
        (None, T.OPENING),  # opening and closing belong to the show, never to a choice
        ("p1", T.CLOSING),
    ],
)
def test_choose_a_combination_without_data_raises_topic_unavailable(product_id, topic):
    planner = SegmentPlanner(
        _catalog(_product("p1", primary=True, faq=()), _product("p2", promotions=(), specs=(), faq=())),
        primary_share=0.5,
    )

    with pytest.raises(TopicUnavailable):
        planner.choose(product_id, topic)
    assert planner.take_override() is None  # a refused choice leaves nothing behind


def test_choose_needs_a_product_or_a_topic():
    planner = SegmentPlanner(_three_products(), primary_share=0.5)

    with pytest.raises(ValueError):
        planner.choose(None, None)


def test_take_override_returns_the_chosen_slot_once():
    planner = SegmentPlanner(_three_products(), primary_share=0.5)
    assert planner.take_override() is None

    chosen = planner.choose("p3", T.FAQ)
    assert planner.override == chosen  # visible to the snapshot without consuming it
    assert planner.take_override() == chosen
    assert planner.take_override() is None
    assert planner.override is None


def test_a_second_choice_replaces_the_first():
    planner = SegmentPlanner(_three_products(), primary_share=0.5)
    planner.choose("p2", T.PRICE)

    second = planner.choose("p3", T.FAQ)

    assert planner.take_override() == second
    assert planner.take_override() is None


def test_choose_does_not_change_the_planned_rotation_slot():
    planner = SegmentPlanner(_three_products(), primary_share=0.5)
    _run(planner, 3)
    before = planner.peek_slot()

    planner.choose("p3", T.FAQ)

    assert planner.peek_slot() == before


def test_a_manual_segment_does_not_consume_a_rotation_slot():
    plain = SegmentPlanner(_three_products(), primary_share=0.5)
    expected = [(s.product_id, s.topic) for s in _run(plain, 12)]

    planner = SegmentPlanner(_three_products(), primary_share=0.5)
    got = [(s.product_id, s.topic) for s in _run(planner, 3)]
    planner.choose("p3", T.FAQ)
    manual = planner.take_override()
    got += [(s.product_id, s.topic) for s in _run(planner, 9)]

    assert manual is not None and manual.origin is SegmentOrigin.OPERATOR
    # The rotation goes on from where it was: same products, same topic cursors.
    assert got == expected

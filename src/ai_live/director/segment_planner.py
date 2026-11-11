"""Rotation of products and topics for the scripted show (004 US1, US5; FR-004, FR-005, FR-018, research R5, R6).

Pure: no asyncio and no I/O, so the rotation invariants are unit-tested over thousands of slots.
`opening` and `closing` are never planned here; the runner creates those two slots itself.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from ai_live.core.models import ROTATION_TOPICS, SegmentOrigin, Topic
from ai_live.products.models import ProductCatalog

_EPS = 1e-9
_ORDER = {topic: i for i, topic in enumerate(ROTATION_TOPICS)}


class NoSlotAvailable(LookupError):
    """The catalog has no product, so there is nothing to talk about."""


class TopicUnavailable(LookupError):
    """The operator's choice has no data: unknown product, or no product with that topic (FR-018, US5 #2)."""


@dataclass(frozen=True)
class PlannedSlot:
    product_id: str | None
    topic: Topic
    origin: SegmentOrigin


def topics_for(product: Any) -> tuple[Topic, ...]:
    """Topics a product has data for, in R5 order. `call_to_action` needs no data, so it is always there."""
    description = (getattr(product, "description", "") or "").strip()
    intro = (getattr(product, "intro", "") or "").strip()
    has = {
        Topic.INTRO: bool(intro or description),
        Topic.HIGHLIGHTS: bool(description),
        Topic.SPECS: bool(getattr(product, "specs", ())),
        Topic.PRICE: getattr(product, "price", None) is not None or bool(getattr(product, "variants", ())),
        Topic.PROMOTION: bool(getattr(product, "promotions", ())),
        Topic.FAQ: bool(getattr(product, "faq", ())),
        Topic.CALL_TO_ACTION: True,
    }
    return tuple(t for t in ROTATION_TOPICS if has[t])


def _extra_primary_slots(secondaries: int, share: float) -> int:
    """Smallest x with (k + x) / (2k + x) >= share, where the base interleave P,S1,P,S2,... gives exactly 0.5."""
    k = secondaries
    x = max(0, math.ceil((share * 2 * k - k) / (1 - share) - _EPS))
    while (k + x) / (2 * k + x) < share - _EPS:
        x += 1
    return x


def _build_cycle(primary: str | None, secondaries: list[str], share: float) -> tuple[str, ...]:
    if primary is None:
        return tuple(secondaries)
    if not secondaries:
        return (primary,)
    extra = _extra_primary_slots(len(secondaries), share)
    cycle: list[str] = []
    for i, secondary in enumerate(secondaries):
        # Extra primary slots are spread over the groups, so the primary never disappears for long.
        count = 1 + extra // len(secondaries) + (1 if i < extra % len(secondaries) else 0)
        cycle += [primary] * count
        cycle.append(secondary)
    return tuple(cycle)


class SegmentPlanner:
    """Plans the next `(product, topic)` slot.

    The cycle interleaves the primary product with each secondary in turn (P, S1, P, S2, ...), with extra primary
    slots when `primary_share` is above 0.5, so every secondary appears once per cycle (R6). Each product has its
    own topic cursor that walks its available topics in R5 order and wraps.
    """

    def __init__(self, catalog: ProductCatalog, primary_share: float) -> None:
        if not 0 <= primary_share < 1:
            raise ValueError(f"primary_share must be in [0, 1), got {primary_share}")
        self._share = primary_share
        self._position = 0
        self._cursors: dict[str, Topic] = {}
        self._previous: PlannedSlot | None = None
        # The operator's slot for the next segment (FR-018); it never moves `_position`.
        self._override: PlannedSlot | None = None
        self._install(catalog)

    # ---------- catalog ----------

    def _install(self, catalog: ProductCatalog) -> None:
        self._catalog = catalog
        self._topics: dict[str, tuple[Topic, ...]] = {p.id: topics_for(p) for p in catalog.products}
        primary = next((p.id for p in catalog.products if p.is_primary), None)
        secondaries = [p.id for p in catalog.products if p.id != primary]
        self._cycle = _build_cycle(primary, secondaries, self._share)

    @property
    def catalog(self) -> ProductCatalog:
        return self._catalog

    def replace_catalog(self, catalog: ProductCatalog) -> None:
        """Keep the topic cursor of products that survive; drop the rest. The cycle position wraps to the new length."""
        self._install(catalog)
        self._cursors = {pid: topic for pid, topic in self._cursors.items() if pid in self._topics}
        if self._previous is not None and self._previous.product_id not in self._topics:
            self._previous = None
        override = self._override
        if override is not None and override.topic not in self._topics.get(override.product_id or "", ()):
            self._override = None  # the chosen data is gone from the new file
        self._position = self._position % len(self._cycle) if self._cycle else 0

    # ---------- queries ----------

    def available_topics(self, product_id: str) -> tuple[Topic, ...]:
        return self._topics.get(product_id, ())

    def availability(self) -> dict[str, tuple[Topic, ...]]:
        return dict(self._topics)

    @property
    def cycle_length(self) -> int:
        return len(self._cycle)

    @property
    def single_combination(self) -> bool:
        """Only one `(product, topic)` exists, so a back-to-back repeat cannot be avoided."""
        return sum(len(topics) for topics in self._topics.values()) == 1

    # ---------- rotation ----------

    def _next_topic(self, product_id: str) -> Topic | None:
        topics = self._topics.get(product_id, ())
        if not topics:
            return None
        last = self._cursors.get(product_id)
        if last is None:
            return topics[0]
        return next((t for t in topics if _ORDER[t] > _ORDER[last]), topics[0])

    def _compute(self) -> tuple[int, PlannedSlot]:
        if not self._cycle:
            raise NoSlotAvailable("Catalog has no product to plan")
        length = len(self._cycle)
        fallback: tuple[int, PlannedSlot] | None = None
        for offset in range(length):
            index = (self._position + offset) % length
            product_id = self._cycle[index]
            topic = self._next_topic(product_id)
            if topic is None:
                continue
            slot = PlannedSlot(product_id, topic, SegmentOrigin.ROTATION)
            if fallback is None:
                fallback = (index, slot)
            prev = self._previous
            repeat = prev is not None and (prev.product_id, prev.topic) == (slot.product_id, slot.topic)
            if not repeat or self.single_combination:
                return index, slot
        if fallback is None:
            raise NoSlotAvailable("No product has a topic to talk about")
        return fallback

    def peek_slot(self) -> PlannedSlot:
        return self._compute()[1]

    def next_slot(self) -> PlannedSlot:
        index, slot = self._compute()
        self._position = (index + 1) % len(self._cycle)
        if slot.product_id is not None:
            self._cursors[slot.product_id] = slot.topic
        self._previous = slot
        return slot

    # ---------- operator choice (US5) ----------

    def choose(self, product_id: str | None, topic: Topic | None) -> PlannedSlot:
        """Hold the operator's slot for the next segment (FR-018, research R6); a later choice replaces it.

        Product only: that product's next topic by its cursor. Topic only: the first product with that topic, the
        primary first. A combination without data raises `TopicUnavailable` and keeps the slot held before.
        """
        if product_id is None and topic is None:
            raise ValueError("choose() needs a product or a topic")
        if topic is not None and not topic.has_product:
            raise TopicUnavailable(f"{topic.value} is not a choosable topic")
        if product_id is not None:
            if product_id not in self._topics:
                raise TopicUnavailable(f"unknown product {product_id}")
            chosen = topic if topic is not None else self._next_topic(product_id)
            if chosen is None or chosen not in self._topics[product_id]:
                raise TopicUnavailable(f"product {product_id} has no data for {topic}")
        else:
            assert topic is not None
            primary_first = sorted(self._catalog.products, key=lambda p: not p.is_primary)
            owner = next((p.id for p in primary_first if topic in self._topics.get(p.id, ())), None)
            if owner is None:
                raise TopicUnavailable(f"no product has data for {topic.value}")
            product_id, chosen = owner, topic
        self._override = PlannedSlot(product_id, chosen, SegmentOrigin.OPERATOR)
        return self._override

    @property
    def override(self) -> PlannedSlot | None:
        """The chosen slot not yet taken, for the snapshot; reading it does not consume it."""
        return self._override

    def take_override(self) -> PlannedSlot | None:
        """The chosen slot, once. The rotation position and cursors stay where they were (a manual segment does
        not consume a rotation slot); it only counts as the previous slot, so the next one does not repeat it.
        """
        slot, self._override = self._override, None
        if slot is not None:
            self._previous = slot
        return slot

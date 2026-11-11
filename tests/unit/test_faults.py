"""T028 (008): `FaultInjector` per-entry faults (contracts/adapters.md §5, FR-016); 004 step faults stay the same."""

from __future__ import annotations

import logging

import pytest

from ai_live.director.faults import ENTRY_FAULT_MODES, FAULT_MODES, FAULT_STEPS, FaultInjector


def test_entry_fault_modes_are_the_contract_list():
    assert ENTRY_FAULT_MODES == ("rate_limited", "overloaded", "timeout", "empty", "wrong_platform", "interrupted")
    # The 004 names are unchanged.
    assert FAULT_STEPS == ("llm", "tts", "render")
    assert FAULT_MODES == ("error", "timeout")


@pytest.mark.parametrize("mode", ENTRY_FAULT_MODES)
def test_inject_with_entry_queues_that_mode_for_the_label(mode):
    faults = FaultInjector()
    faults.inject("llm", mode, 2, entry="sealion")

    assert faults.pending_entry("sealion") == 2
    assert faults.take_entry("sealion") == mode
    assert faults.pending_entry("sealion") == 1
    assert faults.take_entry("sealion") == mode
    assert faults.pending_entry("sealion") == 0
    assert faults.take_entry("sealion") is None


def test_entry_queues_are_per_label_and_keep_their_order():
    faults = FaultInjector()
    faults.inject("llm", "rate_limited", 1, entry="sealion")
    faults.inject("llm", "interrupted", 1, entry="sealion")
    faults.inject("llm", "overloaded", 3, entry="qwen")

    assert (faults.pending_entry("sealion"), faults.pending_entry("qwen")) == (2, 3)
    assert faults.take_entry("sealion") == "rate_limited"
    assert faults.take_entry("sealion") == "interrupted"
    assert faults.take_entry("sealion") is None
    # Taking from one label never touches another.
    assert faults.pending_entry("qwen") == 3
    assert [faults.take_entry("qwen") for _ in range(4)] == ["overloaded", "overloaded", "overloaded", None]


def test_unknown_label_has_nothing_pending():
    faults = FaultInjector()
    assert faults.pending_entry("gptoss") == 0
    assert faults.take_entry("gptoss") is None


def test_take_entry_works_as_the_engine_fault_hook():
    # The engine only gets a `Callable[[str], str | None]` (brain/ never imports director/).
    faults = FaultInjector()
    hook = faults.take_entry
    faults.inject("llm", "empty", entry="sealion")
    assert hook("sealion") == "empty"
    assert hook("sealion") is None


@pytest.mark.parametrize("step", ["tts", "render"])
def test_entry_with_a_step_other_than_llm_is_rejected(step):
    faults = FaultInjector()
    with pytest.raises(ValueError):
        faults.inject(step, "timeout", 1, entry="sealion")
    assert faults.pending_entry("sealion") == 0
    assert faults.pending(step) == 0


@pytest.mark.parametrize("mode", ["error", "crash", ""])
def test_entry_with_a_mode_outside_entry_fault_modes_is_rejected(mode):
    faults = FaultInjector()
    with pytest.raises(ValueError):
        faults.inject("llm", mode, 1, entry="sealion")
    assert faults.pending_entry("sealion") == 0
    assert faults.pending("llm") == 0


@pytest.mark.parametrize("count", [0, -1])
def test_entry_with_a_count_below_one_is_rejected(count):
    faults = FaultInjector()
    with pytest.raises(ValueError):
        faults.inject("llm", "rate_limited", count, entry="sealion")
    assert faults.pending_entry("sealion") == 0


@pytest.mark.parametrize("mode", ["rate_limited", "overloaded", "empty", "wrong_platform", "interrupted"])
def test_entry_only_modes_need_an_entry(mode):
    faults = FaultInjector()
    with pytest.raises(ValueError):
        faults.inject("llm", mode, 1)
    assert faults.pending("llm") == 0


def test_step_faults_of_004_are_unchanged_and_separate_from_entry_faults():
    faults = FaultInjector()
    faults.inject("llm", "error", 2)
    faults.inject("tts", "timeout")
    faults.inject("llm", "timeout", 1, entry="sealion")

    # A per-entry fault is not a step fault: it never makes `reply()` / `narrate()` fail before the engine runs.
    assert faults.pending("llm") == 2
    assert faults.pending_entry("sealion") == 1
    assert faults.take("llm") == "error"
    assert faults.take("llm") == "error"
    assert faults.take("llm") is None
    assert faults.take("tts") == "timeout"
    assert faults.take_entry("sealion") == "timeout"
    # The old three-argument form still works, and its bad values are still rejected.
    with pytest.raises(ValueError):
        faults.inject("brain", "error")
    with pytest.raises(ValueError):
        faults.inject("llm", "crash")
    with pytest.raises(ValueError):
        faults.inject("llm", "error", 0)


def test_inject_with_entry_logs_the_label():
    records: list[logging.LogRecord] = []

    class Collect(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            records.append(record)

    # A handler on the module's own logger: app startup in other tests may stop `ai_live` from propagating.
    target = logging.getLogger("ai_live.director")
    handler, saved = Collect(), target.level
    target.addHandler(handler)
    target.setLevel(logging.INFO)
    try:
        FaultInjector().inject("llm", "rate_limited", 3, entry="sealion")
    finally:
        target.removeHandler(handler)
        target.setLevel(saved)

    fields = [r.fields for r in records if r.getMessage() == "fault_injected"]
    assert fields == [{"step": "llm", "mode": "rate_limited", "count": 3, "entry": "sealion"}]

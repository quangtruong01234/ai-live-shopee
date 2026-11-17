"""T009 power and disk checks for the readiness list (research R5): stdlib only, no new dependency."""

from __future__ import annotations

from collections import namedtuple

import pytest

from ai_live.ops import system


@pytest.mark.parametrize(("ac_line", "expected"), [(1, "ac"), (0, "battery"), (255, None)])
def test_power_status_maps_ac_line_status(monkeypatch, ac_line, expected):
    monkeypatch.setattr(system, "_read_ac_line_status", lambda: ac_line)
    assert system.power_status() == expected


def test_power_status_none_when_unreadable(monkeypatch):
    monkeypatch.setattr(system, "_read_ac_line_status", lambda: None)
    assert system.power_status() is None


def test_power_status_none_outside_windows(monkeypatch):
    monkeypatch.setattr(system.sys, "platform", "linux")
    assert system._read_ac_line_status() is None
    assert system.power_status() is None


def test_power_status_reads_real_api_on_this_machine():
    # Smoke: whatever the machine is, the call never raises and returns one of the three values.
    assert system.power_status() in ("ac", "battery", None)


def test_free_disk_gb_uses_disk_usage(monkeypatch, tmp_path):
    usage = namedtuple("usage", "total used free")
    seen = []

    def fake_usage(path):
        seen.append(path)
        return usage(100 * 1024**3, 90 * 1024**3, 10 * 1024**3)

    monkeypatch.setattr(system.shutil, "disk_usage", fake_usage)
    assert system.free_disk_gb(tmp_path) == pytest.approx(10.0)
    assert seen == [tmp_path]


def test_free_disk_gb_walks_up_to_existing_parent(tmp_path):
    # SESSION_DATA_DIR may not exist yet before the first session; its drive is what matters.
    assert system.free_disk_gb(tmp_path / "not" / "yet") > 0

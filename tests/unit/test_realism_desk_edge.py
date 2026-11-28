"""`realism_report._desk_edge` finds the desk top, not the shirt-to-arms step in the middle of the frame.

The skill script is not a package, so it is loaded with importlib.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / ".claude" / "skills" / "live-scene-realism" / "scripts" / "realism_report.py"
W, H = 480, 832


@pytest.fixture(scope="module")
def rr():
    spec = importlib.util.spec_from_file_location("realism_report_desk_test", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_desk_edge_ignores_a_strong_step_on_the_host(rr) -> None:
    # Room wall everywhere, a wooden desk across the full width from y 649, and a dark shirt over light
    # arms in the middle (x 140-340) whose step at y 611 is far stronger than the desk step.
    frame = np.full((H, W, 3), (200, 196, 190), np.uint8)
    frame[649:] = (150, 110, 70)
    frame[300:611, 140:340] = (20, 20, 25)
    frame[611:700, 140:340] = (235, 200, 175)
    assert abs(rr._desk_edge(frame) - 649) <= 2


def test_desk_edge_on_a_plain_full_width_step(rr) -> None:
    frame = np.full((H, W, 3), (180, 180, 180), np.uint8)
    frame[700:] = (90, 60, 40)
    assert abs(rr._desk_edge(frame) - 700) <= 2


def test_desk_edge_ignores_busy_shelves_at_the_frame_sides(rr) -> None:
    # A stocked shelf behind the host reaches the frame sides: strong, textured board edges above the desk.
    rng = np.random.default_rng(0)
    frame = np.full((H, W, 3), (200, 196, 190), np.uint8)
    frame[440:649] = rng.integers(60, 250, (649 - 440, W, 3), dtype=np.uint8)
    frame[500:506] = (250, 250, 250)  # a white shelf board
    frame[649:] = (215, 180, 140)
    assert abs(rr._desk_edge(frame) - 649) <= 2

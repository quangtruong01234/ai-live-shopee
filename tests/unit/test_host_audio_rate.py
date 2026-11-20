"""Guard for the static host's Web Audio path (006 T029 finding, 2026-11-19).

Chrome resamples every AudioBuffer on its own when its rate differs from the context rate, and treats the samples
outside the buffer as silence. Streaming 16 kHz chunks into a 48 kHz context therefore clicks at each chunk seam
(OfflineAudioContext check: max error 0.5 on a 0.5 sine with 1777-sample chunks, 0 at a 16 kHz context). The real
check needs a browser; this test only keeps the page on the fix, which is to run the context at the PCM rate.
"""

import re
from pathlib import Path

from ai_live.core.config import Settings

HOST_JS = Path(__file__).resolve().parents[2] / "src" / "ai_live" / "app" / "static" / "host.js"


def test_audio_context_runs_at_the_pcm_rate() -> None:
    js = HOST_JS.read_text(encoding="utf-8")
    rate = re.search(r"const PCM_RATE = (\d+);", js)
    assert rate, "host.js must name the PCM rate it plays"
    assert int(rate.group(1)) == Settings.model_fields["tts_sample_rate"].default
    assert "new AudioContext({ sampleRate: PCM_RATE })" in js


def test_playback_rebuffers_after_running_dry() -> None:
    # A lead of a few tens of ms let a slow first chunk of VieNeu on CPU leave holes of ~14 ms at show start.
    js = HOST_JS.read_text(encoding="utf-8")
    lead = re.search(r"const LEAD_S = ([\d.]+);", js)
    assert lead and float(lead.group(1)) >= 0.15

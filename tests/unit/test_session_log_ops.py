"""T007 session files added by 007: session.json, gaps/alerts/readiness.jsonl (contracts/files.md §1-§4)."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from ai_live.director.session_log import (
    ALERTS_FILE,
    GAPS_FILE,
    READINESS_FILE,
    SESSION_INFO_FILE,
    SessionLog,
)


def _lines(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


@pytest.mark.anyio
async def test_jsonl_lines_are_on_disk_before_close(tmp_path):
    log = await SessionLog.open(tmp_path, "s1")
    gap = {
        "show_id": "sh1",
        "kind": "script",
        "counted": True,
        "seconds": 0.84,
        "from_id": "a",
        "to_id": "b",
        "at": "t",
    }
    log.write_gap(gap)
    log.write_alert({"event": "open", "at": "t", "alert": {"alert_id": "x", "kind": "silence"}})
    log.write_readiness({"checked_at": "t", "source": "app", "ready": False, "items": []})
    await log.flush()
    # Read while the log is still open: a crash after this point must not lose these lines.
    assert _lines(log.directory / GAPS_FILE) == [gap]
    assert _lines(log.directory / ALERTS_FILE)[0]["alert"]["kind"] == "silence"
    assert _lines(log.directory / READINESS_FILE)[0]["ready"] is False
    await log.close()


@pytest.mark.anyio
async def test_lines_keep_submit_order(tmp_path):
    log = await SessionLog.open(tmp_path, "s1")
    for i in range(20):
        log.write_gap({"seconds": i})
    await log.close()
    assert [r["seconds"] for r in _lines(log.directory / GAPS_FILE)] == list(range(20))


@pytest.mark.anyio
async def test_session_info_written_once_and_redacted(tmp_path):
    log = await SessionLog.open(tmp_path, "s1")
    log.write_session_info(
        {"session_id": "s1", "reply_engine": "fake", "gemini_api_key": "AIzaSyD-very-secret-value-123456789012"}
    )
    await log.flush()
    data = json.loads((log.directory / SESSION_INFO_FILE).read_text(encoding="utf-8"))
    assert data["session_id"] == "s1"
    assert data["gemini_api_key"] == "***"
    await log.close()


@pytest.mark.anyio
async def test_alert_text_with_key_is_redacted(tmp_path):
    log = await SessionLog.open(tmp_path, "s1")
    log.write_alert({"event": "open", "at": "t", "alert": {"message": "lỗi GEMINI_API_KEY=abcdef123456"}})
    await log.close()
    assert "abcdef123456" not in (log.directory / ALERTS_FILE).read_text(encoding="utf-8")


@pytest.mark.anyio
async def test_writes_after_close_are_ignored(tmp_path):
    log = await SessionLog.open(tmp_path, "s1")
    await log.close()
    log.write_gap({"seconds": 1})
    log.write_session_info({"session_id": "s1"})
    assert not (log.directory / GAPS_FILE).exists()


def test_session_dir_is_outside_git():
    ignored = subprocess.run(
        ["git", "check-ignore", "-q", "data/sessions/s1/gaps.jsonl"], capture_output=True, check=False
    )
    assert ignored.returncode == 0

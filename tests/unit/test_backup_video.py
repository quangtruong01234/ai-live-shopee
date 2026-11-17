"""007 US4 T045: the backup-video maker (FR-018, FR-019, research R7, contracts/cli.md `backup-video`).

The app and the fork are fake HTTP servers, the analyzer is a function returning a `report.json` dict and the clock only
moves when the maker sleeps, so the R7 order and every refusal run in milliseconds without a GPU.
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import httpx
import pytest

from ai_live.ops import backup_video as bv

NOW = datetime(2026, 11, 13, 14, 5, 30).astimezone()
NAME = "backup_20261113-1405_demo_customer_01"
MP4_BYTES = b"\x00\x00\x00\x18ftypmp42" + bytes(range(256)) * 4


def good_report(seconds: float = 150.0) -> dict[str, Any]:
    return {
        "checks": {
            "stream": {"seconds": seconds, "ok": True},
            "audio": {"peak": 12000, "speaking_frames": 2900, "ok": True},
            "label": {"frames_missing": 0, "ok": True},
            "mouth": {"ok": True},
        },
        "ok": True,
    }


class World:
    """The running app and fork as the maker sees them over HTTP; every request lands in `calls`."""

    def __init__(self, tmp_path: Path) -> None:
        self.calls: list[tuple] = []
        self.health: dict[str, Any] = {
            "status": "ok",
            "host_connected": True,
            "catalog_version": "2a1a52d5ae99",
            "customer_id": "demo_customer_01",
            "avatar_id": "demo_host_01",
            "show_active": False,
            "avatar": {"configured": "livetalking", "active": "livetalking", "lipsync_connected": True},
        }
        self.fork_health: dict[str, Any] = {"ok": True, "sessions": ["123456"], "record_enabled": True}
        self.record_dir = tmp_path / "records"
        self.record_max_s = 600.0
        self.show: dict[str, Any] | None = None
        self.polls_until_ended = 2
        self.start_status = 200
        self.end_early_after_polls: int | None = None
        self.app_down = False
        self.recording: Path | None = None

    # --- the app ---

    def app_handler(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        body = json.loads(request.content) if request.content else None
        self.calls.append(("app", request.method, path, body))
        if self.app_down:
            raise httpx.ConnectError("refused", request=request)
        if path == "/health":
            return httpx.Response(200, json=self.health)
        if path == "/api/show/start":
            if self.start_status != 200:
                return httpx.Response(
                    self.start_status, json={"error": "host_unavailable", "message": "Host chưa sẵn sàng"}
                )
            self.show = {"show_id": "show-b1", "state": "running", "content_source": body["content"], "polls": 0}
            return httpx.Response(
                200,
                json={"show_id": "show-b1", "state": "running", "already_running": False, "content": body["content"]},
            )
        if path == "/api/show/end":
            if self.show is None:
                return httpx.Response(200, json={"show_id": None, "state": None})
            if self.show["state"] != "ended":
                self.show["state"] = "closing"
            return httpx.Response(200, json={"show_id": self.show["show_id"], "state": self.show["state"]})
        if path == "/api/show":
            if self.show is None:
                return httpx.Response(200, json=None)
            self.show["polls"] += 1
            if self.show["state"] == "closing":
                self.polls_until_ended -= 1
                if self.polls_until_ended <= 0:
                    self.show["state"] = "ended"
            elif self.end_early_after_polls is not None and self.show["polls"] >= self.end_early_after_polls:
                self.show["state"] = "ended"
            return httpx.Response(200, json={k: v for k, v in self.show.items() if k != "polls"})
        return httpx.Response(404)

    # --- the fork ---

    def fork_handler(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        params = dict(request.url.params)
        self.calls.append(("fork", request.method, path, params))
        if path == "/ailive/health":
            return httpx.Response(200, json=self.fork_health)
        if path == "/ailive/record/start":
            prefix = self.record_dir / params["name"]
            self.recording = prefix
            return httpx.Response(
                200, json={"recording": True, "prefix": str(prefix), "max_seconds": self.record_max_s}
            )
        if path == "/ailive/record/stop":
            prefix, self.recording = self.recording, None
            if prefix is None:
                return httpx.Response(409, json={"error": "not recording"})
            prefix.parent.mkdir(parents=True, exist_ok=True)
            Path(f"{prefix}.mp4").write_bytes(MP4_BYTES)
            return httpx.Response(
                200,
                json={
                    "prefix": str(prefix),
                    "frames": 3750,
                    "dropped": 0,
                    "seconds": 150.0,
                    "stopped_by": "request",
                    "error": None,
                    "files": [f"{prefix}.mp4", f"{prefix}.wav", f"{prefix}.jsonl"],
                },
            )
        return httpx.Response(404)


class Clock:
    def __init__(self, calls: list[tuple]) -> None:
        self.calls = calls
        self.t = NOW

    def now(self) -> datetime:
        return self.t

    async def sleep(self, seconds: float) -> None:
        self.calls.append(("sleep", seconds))
        self.t += timedelta(seconds=seconds)


@pytest.fixture
def world(tmp_path: Path) -> World:
    return World(tmp_path)


def make(world: World, tmp_path: Path, report: dict[str, Any] | None = None, *, messages: list[str] | None = None):
    clock = Clock(world.calls)
    analyzed: list[Path] = []

    async def analyze(prefix: Path) -> dict[str, Any] | None:
        world.calls.append(("analyze", str(prefix)))
        analyzed.append(prefix)
        return good_report() if report is None else report

    app = httpx.AsyncClient(base_url="http://app", transport=httpx.MockTransport(world.app_handler))
    fork = httpx.AsyncClient(base_url="http://fork", transport=httpx.MockTransport(world.fork_handler))
    maker = bv.BackupVideoMaker(
        app,
        fork,
        backup_dir=tmp_path / "backup",
        analyze=analyze,
        sleep=clock.sleep,
        now=clock.now,
        progress=(messages.append if messages is not None else lambda _: None),
    )
    return maker, clock


def run(
    world: World, tmp_path: Path, seconds: float = 150.0, content: str = "verbatim", **kwargs
) -> bv.BackupVideoSheet:
    maker, _ = make(world, tmp_path, **kwargs)
    return asyncio.run(maker.make(seconds, content))


def steps(world: World) -> list[str]:
    """The calls without the progress polls and the short waits, in the order they happened."""
    out = []
    for call in world.calls:
        if call[0] == "sleep":
            continue
        if call[0] == "analyze":
            out.append("analyze")
        elif call[2] != "/api/show":
            out.append(f"{call[0]} {call[1]} {call[2]}")
    return out


# --- the R7 order ---


def test_the_r7_order(world, tmp_path):
    sheet = run(world, tmp_path)
    assert steps(world) == [
        "app GET /health",
        "fork GET /ailive/health",
        "fork POST /ailive/record/start",
        "app POST /api/show/start",
        "app POST /api/show/end",
        "fork POST /ailive/record/stop",
        "analyze",
    ]
    assert sheet.ok
    start = next(c for c in world.calls if c[2] == "/ailive/record/start")
    assert start[3] == {"sessionid": "123456", "name": NAME}
    show_start = next(c for c in world.calls if c[2] == "/api/show/start")
    assert show_start[3] == {"content": "verbatim"}


def test_the_show_runs_seconds_minus_8_then_closes_and_waits_1_second_before_stopping(world, tmp_path):
    run(world, tmp_path, seconds=150.0)
    i_start = next(i for i, c in enumerate(world.calls) if c[2:3] == ("/api/show/start",))
    i_end = next(i for i, c in enumerate(world.calls) if c[2:3] == ("/api/show/end",))
    i_stop = next(i for i, c in enumerate(world.calls) if c[2:3] == ("/ailive/record/stop",))
    waited = sum(c[1] for c in world.calls[i_start:i_end] if c[0] == "sleep")
    assert waited == pytest.approx(142.0)
    # No progress step is longer than 10 s, so the operator sees the show move.
    assert all(c[1] <= 10.0 for c in world.calls[i_start:i_end] if c[0] == "sleep")
    # After the end: the show is seen `ended`, then a 1 s tail, then the recording stops.
    between = world.calls[i_end:i_stop]
    polls = [c for c in between if c[0] == "app" and c[2] == "/api/show"]
    assert polls
    assert between[-1] == ("sleep", 1.0)


def test_progress_is_printed_every_10_seconds(world, tmp_path):
    messages: list[str] = []
    run(world, tmp_path, messages=messages)
    ticks = [m for m in messages if "giây" in m and "/" in m]
    assert len(ticks) >= 14


def test_script_content_is_passed_through(world, tmp_path):
    sheet = run(world, tmp_path, content="script")
    show_start = next(c for c in world.calls if c[2] == "/api/show/start")
    assert show_start[3] == {"content": "script"}
    assert sheet.content_source == "script"


# --- the sheet ---


def test_a_good_recording_gives_an_ok_sheet_the_video_and_both_sheet_files(world, tmp_path):
    sheet = run(world, tmp_path)
    backup = tmp_path / "backup"
    assert sheet.name == NAME
    assert sheet.ok and sheet.problems == ()
    assert sheet.seconds == pytest.approx(150.0)
    assert sheet.has_audio and sheet.label_ok and sheet.label_frames_missing == 0
    assert (sheet.customer_id, sheet.avatar_id, sheet.catalog_version) == (
        "demo_customer_01",
        "demo_host_01",
        "2a1a52d5ae99",
    )
    assert sheet.show_id == "show-b1"
    assert sheet.content_source == "verbatim"
    assert sheet.made_at.startswith("2026-11-13T14:05")
    # The recorder's mp4, byte for byte: nothing cut or joined (constitution I).
    video = Path(sheet.video)
    assert video == (backup / f"{NAME}.mp4").resolve()
    assert video.read_bytes() == MP4_BYTES
    data = json.loads((backup / f"{NAME}.sheet.json").read_text(encoding="utf-8"))
    assert data["ok"] is True and data["name"] == NAME and data["video"] == str(video)
    assert data["note"] == bv.NOTE == "Chỉ dùng cho demo Meet/YouTube, không phát trên Shopee Live"
    md = (backup / f"{NAME}.sheet.md").read_text(encoding="utf-8")
    assert bv.NOTE in md and "demo_host_01" in md and "2a1a52d5ae99" in md and "verbatim" in md


@pytest.mark.parametrize(
    ("report", "problem"),
    [
        (good_report(100.0), "độ dài"),
        (good_report(185.0), "độ dài"),
        ({**good_report(), "checks": {**good_report()["checks"], "audio": {"peak": 0, "speaking_frames": 0}}}, "tiếng"),
        (
            {**good_report(), "checks": {**good_report()["checks"], "audio": {"peak": 900, "speaking_frames": 0}}},
            "tiếng",
        ),
        ({**good_report(), "checks": {**good_report()["checks"], "label": {"frames_missing": 3, "ok": False}}}, "nhãn"),
    ],
)
def test_a_failed_check_is_not_ok_and_says_why_in_vietnamese(world, tmp_path, report, problem):
    sheet = run(world, tmp_path, report=report)
    assert not sheet.ok
    assert len(sheet.problems) == 1
    assert problem in sheet.problems[0].lower()
    # The sheet is still written so the operator sees what failed (readiness reads it as not usable).
    assert json.loads((tmp_path / "backup" / f"{NAME}.sheet.json").read_text(encoding="utf-8"))["ok"] is False


def test_a_missing_label_counts_the_frames(world, tmp_path):
    report = {**good_report(), "checks": {**good_report()["checks"], "label": {"frames_missing": 7, "ok": False}}}
    sheet = run(world, tmp_path, report=report)
    assert sheet.label_frames_missing == 7
    assert "7" in sheet.problems[0]


def test_other_analyzer_checks_do_not_decide_the_sheet(world, tmp_path):
    report = good_report()
    report["checks"]["mouth"] = {"ok": False}
    report["ok"] = False
    assert run(world, tmp_path, report=report).ok


def test_no_analyzer_report_is_not_ok(world, tmp_path):
    maker, _ = make(world, tmp_path)

    async def no_report(prefix: Path) -> None:
        return None

    maker.analyze = no_report
    sheet = asyncio.run(maker.make(150.0, "verbatim"))
    assert not sheet.ok
    assert any("chấm" in p for p in sheet.problems)


def test_a_recording_cut_by_the_fork_limit_is_a_problem(world, tmp_path):
    original = world.fork_handler

    def cut(request: httpx.Request) -> httpx.Response:
        response = original(request)
        if request.url.path == "/ailive/record/stop":
            return httpx.Response(200, json={**response.json(), "stopped_by": "max_seconds"})
        return response

    world.fork_handler = cut
    sheet = run(world, tmp_path)
    assert not sheet.ok
    assert any("AILIVE_RECORD_MAX_S" in p for p in sheet.problems)


# --- refusals (exit 2, nothing recorded, no show) ---


@pytest.mark.parametrize(
    ("change", "word"),
    [
        (lambda w: w.health["avatar"].update(active="static"), "ảnh tĩnh"),
        (lambda w: w.health.update(show_active=True), "show"),
        (lambda w: w.health.update(host_connected=False), "host"),
        (lambda w: w.health.update(customer_id=""), "CUSTOMER_ID"),
        (lambda w: w.health.update(avatar_id=""), "AVATAR_ID"),
        (lambda w: w.fork_health.update(record_enabled=False), "AILIVE_RECORD_DIR"),
        (lambda w: w.fork_health.update(sessions=[]), "phiên"),
    ],
)
def test_refused_before_anything_starts(world, tmp_path, change, word):
    change(world)
    with pytest.raises(bv.BackupRefused) as err:
        run(world, tmp_path)
    assert word in str(err.value)
    assert err.value.action
    assert not [c for c in world.calls if c[2] in ("/ailive/record/start", "/api/show/start")]
    assert not (tmp_path / "backup").exists()


def test_app_down_is_refused(world, tmp_path):
    world.app_down = True
    with pytest.raises(bv.BackupRefused) as err:
        run(world, tmp_path)
    assert "app" in str(err.value).lower()


def test_a_fork_that_does_not_answer_is_refused(world, tmp_path):
    def down(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    world.fork_handler = down
    with pytest.raises(bv.BackupRefused) as err:
        run(world, tmp_path)
    assert "fork" in str(err.value).lower()


@pytest.mark.parametrize("seconds", [119.0, 181.0, 0.0])
def test_seconds_outside_120_to_180_are_refused(world, tmp_path, seconds):
    with pytest.raises(bv.BackupRefused) as err:
        run(world, tmp_path, seconds=seconds)
    assert "120" in str(err.value) and "180" in str(err.value)
    assert world.calls == []


def test_an_unknown_content_is_refused(world, tmp_path):
    with pytest.raises(bv.BackupRefused):
        run(world, tmp_path, content="video")
    assert world.calls == []


def test_a_fork_record_limit_shorter_than_the_video_is_refused_and_the_recording_stopped(world, tmp_path):
    world.record_max_s = 120.0
    with pytest.raises(bv.BackupRefused) as err:
        run(world, tmp_path, seconds=150.0)
    assert "AILIVE_RECORD_MAX_S" in str(err.value)
    assert "fork POST /ailive/record/stop" in steps(world)
    assert "app POST /api/show/start" not in steps(world)


# --- errors midway: always end the show and stop the recording, no sheet ---


def test_show_start_refused_stops_the_recording(world, tmp_path):
    world.start_status = 409
    with pytest.raises(bv.BackupFailed) as err:
        run(world, tmp_path)
    assert "Host chưa sẵn sàng" in str(err.value)
    assert steps(world)[-1] == "fork POST /ailive/record/stop"
    assert "analyze" not in steps(world)
    assert not (tmp_path / "backup").exists()


def test_a_show_that_ends_early_fails_and_still_stops_the_recording(world, tmp_path):
    world.end_early_after_polls = 3
    with pytest.raises(bv.BackupFailed) as err:
        run(world, tmp_path)
    assert "kết thúc sớm" in str(err.value)
    assert "fork POST /ailive/record/stop" in steps(world)
    assert "analyze" not in steps(world)


def test_a_show_that_never_ends_still_stops_the_recording(world, tmp_path):
    world.polls_until_ended = 10_000
    with pytest.raises(bv.BackupFailed) as err:
        run(world, tmp_path)
    assert "30" in str(err.value)
    assert steps(world)[-1] == "fork POST /ailive/record/stop"


def test_ctrl_c_ends_the_show_stops_the_recording_and_writes_no_sheet(world, tmp_path):
    maker, clock = make(world, tmp_path)
    slept = 0

    async def interrupted_sleep(seconds: float) -> None:
        nonlocal slept
        slept += 1
        if slept == 3:
            raise KeyboardInterrupt
        await clock.sleep(seconds)

    maker.sleep = interrupted_sleep
    with pytest.raises(KeyboardInterrupt):
        asyncio.run(maker.make(150.0, "verbatim"))
    assert steps(world)[-2:] == ["app POST /api/show/end", "fork POST /ailive/record/stop"]
    assert not (tmp_path / "backup").exists()


# --- the CLI ---


def test_cli_exit_codes(world, tmp_path, monkeypatch, capsys):
    def cli(**kwargs) -> int:
        clock = Clock(world.calls)

        async def analyze(prefix: Path) -> dict[str, Any]:
            return kwargs.pop("report", None) or good_report()

        return bv.cli_backup_video(
            "http://app",
            seconds=kwargs.get("seconds", 150.0),
            content="verbatim",
            fork_url="http://fork",
            backup_dir=tmp_path / "backup",
            analyze=analyze,
            transport=httpx.MockTransport(world.app_handler),
            fork_transport=httpx.MockTransport(world.fork_handler),
            sleep=clock.sleep,
            now=clock.now,
        )

    assert cli() == 0
    out = capsys.readouterr().out
    assert NAME in out and "Đạt" in out
    world.show = None
    world.health["show_active"] = False
    assert cli(report=good_report(90.0)) == 1
    assert cli(seconds=200.0) == 2
    assert "120" in capsys.readouterr().out
    world.health["host_connected"] = False
    assert cli() == 2

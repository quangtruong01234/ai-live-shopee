"""Backup video for the Meet/YouTube demo (007 US4, data-model §5, research R7, contracts/cli.md `backup-video`).

A real show, recorded by the fork's recorder (the frames that go out, with the "AI" label, scene and watermark, and the
sound the fork plays), checked by the fork's analyzer and copied as is: nothing is cut, joined or rendered afterwards
(constitution I). The video is only for demos outside Shopee: the app has no way to play it (FR-021).
"""

from __future__ import annotations

import asyncio
import json
import shutil
import subprocess
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

import httpx

from ai_live.avatar.character import DEFAULT_FORK_DIR

if TYPE_CHECKING:
    from ai_live.core.config import Settings

NOTE = "Chỉ dùng cho demo Meet/YouTube, không phát trên Shopee Live"
MIN_SECONDS = 120.0
MAX_SECONDS = 180.0
CONTENTS = ("verbatim", "script")
# The closing takes a few sentences; ending early keeps the whole video, closing included, near `seconds` (R7).
CLOSING_ALLOWANCE_S = 8.0
END_WAIT_S = 30.0
END_POLL_S = 0.5
TAIL_S = 1.0  # the last picture and sound after the closing sentence, so the video does not stop mid-word
PROGRESS_EVERY_S = 10.0
# The fork stops recording by itself after AILIVE_RECORD_MAX_S: leave room for the closing and the tail.
RECORD_MARGIN_S = END_WAIT_S
HTTP_TIMEOUT_S = 10.0
RECORD_STOP_TIMEOUT_S = 120.0  # the recorder finishes encoding before it answers

Analyze = Callable[[Path], Awaitable[dict[str, Any] | None]]


class BackupRefused(Exception):
    """Nothing was recorded and no show started: a condition before the run is not met (exit 2)."""

    def __init__(self, message: str, action: str) -> None:
        super().__init__(message)
        self.action = action


class BackupFailed(Exception):
    """The run broke midway; the show was ended and the recording stopped, no sheet was written (exit 1)."""


@dataclass(frozen=True)
class BackupVideoSheet:
    name: str  # backup_<YYYYmmdd-HHMM>_<customer>
    video: str  # the mp4 inside BACKUP_VIDEO_DIR
    made_at: str
    customer_id: str
    avatar_id: str
    catalog_version: str
    content_source: Literal["verbatim", "script"]
    show_id: str
    seconds: float
    has_audio: bool
    label_ok: bool
    label_frames_missing: int
    ok: bool  # 120 ≤ seconds ≤ 180 and has_audio and label_ok
    problems: tuple[str, ...] = ()  # Vietnamese, for the operator
    note: str = field(default=NOTE)

    def to_json(self) -> dict[str, Any]:
        data = asdict(self)
        data["problems"] = list(self.problems)
        return data


# ---------- pure parts ----------


def check_request(seconds: float, content: str) -> None:
    if not MIN_SECONDS <= seconds <= MAX_SECONDS:
        raise BackupRefused(
            f"--seconds phải trong {MIN_SECONDS:g}–{MAX_SECONDS:g} giây (đang là {seconds:g})",
            f"Chạy lại với --seconds từ {MIN_SECONDS:g} đến {MAX_SECONDS:g}, ví dụ --seconds 150",
        )
    if content not in CONTENTS:
        raise BackupRefused(f'--content "{content}" không hợp lệ', "Dùng --content verbatim hoặc --content script")


def check_app(health: Mapping[str, Any]) -> None:
    """`BackupRefused` naming what to do first when the app cannot make a backup video (contracts/cli.md)."""
    avatar = health.get("avatar") or {}
    if avatar.get("active") != "livetalking":
        if avatar.get("configured") == "livetalking":
            message = "Nhép miệng chưa chạy: app đang hiện ảnh tĩnh, không có bộ ghi của fork"
        else:
            message = "App đang chạy chế độ ảnh tĩnh (AVATAR_MODE=static), không có bộ ghi của fork"
        raise BackupRefused(
            message, "Bật fork (scripts/livetalking/run.ps1), chạy app với AVATAR_MODE=livetalking, chờ host nhép miệng"
        )
    if not health.get("customer_id"):
        raise BackupRefused(
            "Thiếu CUSTOMER_ID: video phải gắn với đúng một khách", "Đặt CUSTOMER_ID trong .env rồi bật lại app"
        )
    if not health.get("avatar_id"):
        raise BackupRefused(
            "Thiếu AVATAR_ID: video phải gắn với đúng một nhân vật", "Đặt AVATAR_ID trong .env rồi bật lại app"
        )
    if health.get("show_active"):
        raise BackupRefused("Đang có show chạy", "Kết thúc show trên trang điều khiển rồi chạy lại lệnh")
    if not health.get("host_connected"):
        raise BackupRefused("Trang host chưa sẵn sàng", "Mở /host và bấm 'Bắt đầu', chờ hình host hiện rồi chạy lại")


def check_fork(fork_health: Mapping[str, Any]) -> str:
    """The fork session to record, or `BackupRefused` when the fork cannot record it."""
    if not fork_health.get("record_enabled"):
        raise BackupRefused(
            "Fork chưa bật ghi (AILIVE_RECORD_DIR trống)",
            "Đặt AILIVE_RECORD_DIR trong .env rồi chạy lại scripts/livetalking/run.ps1",
        )
    sessions = fork_health.get("sessions") or []
    if not sessions:
        raise BackupRefused("Fork chưa có phiên nào đang phát", "Mở /host và bấm 'Bắt đầu' để host nối với fork")
    return str(sessions[0])


def sheet_name(made_at: datetime, customer_id: str) -> str:
    return f"backup_{made_at:%Y%m%d-%H%M}_{customer_id}"


def check_recording(
    report: Mapping[str, Any] | None, stopped_by: str | None
) -> tuple[float, bool, bool, int, list[str]]:
    """(seconds, has_audio, label_ok, label_frames_missing, problems) from the analyzer's `report.json` (R7)."""
    checks = (report or {}).get("checks") or {}
    stream = checks.get("stream") or {}
    if report is None or "seconds" not in stream:
        return 0.0, False, False, 0, ["Không chấm được bản ghi: thiếu report.json của ailive_ext.analyze"]
    seconds = float(stream["seconds"])
    audio = checks.get("audio") or {}
    has_audio = (audio.get("peak") or 0) > 0 and (audio.get("speaking_frames") or 0) > 0
    label = checks.get("label") or {}
    label_ok = label.get("ok") is True
    missing = int(label.get("frames_missing") or 0)
    problems = []
    if not MIN_SECONDS <= seconds <= MAX_SECONDS:
        problems.append(f"Độ dài {seconds:.1f} giây, cần {MIN_SECONDS:g}–{MAX_SECONDS:g} giây")
    if not has_audio:
        problems.append("Không có tiếng: bản ghi im lặng hoặc host không nói câu nào")
    if not label_ok:
        problems.append(f'Thiếu nhãn "AI" ở {missing} khung hình')
    if stopped_by == "max_seconds":
        problems.append("Fork tự dừng ghi (AILIVE_RECORD_MAX_S) trước khi show kết thúc")
    return seconds, has_audio, label_ok, missing, problems


def render_markdown(sheet: BackupVideoSheet) -> str:
    result = "Đạt" if sheet.ok else "Không đạt"
    lines = [
        f"# Video dự phòng {sheet.name}",
        "",
        f"> **{sheet.note}.**",
        "",
        f"- Video: `{sheet.video}`",
        f"- Làm lúc: {sheet.made_at}",
        f"- Khách: {sheet.customer_id}",
        f"- Nhân vật: {sheet.avatar_id}",
        f"- Bản nội dung sản phẩm: {sheet.catalog_version}",
        f"- Nguồn nội dung: {sheet.content_source}"
        + (" (đọc nguyên văn phần giới thiệu và mô tả)" if sheet.content_source == "verbatim" else " (kịch bản LLM)"),
        f"- Show: {sheet.show_id}",
        "",
        f"## Kết quả kiểm: {result}",
        "",
        f"- Độ dài: {sheet.seconds:.1f} giây (cần {MIN_SECONDS:g}–{MAX_SECONDS:g})",
        f"- Có tiếng: {'có' if sheet.has_audio else 'không'}",
        f'- Nhãn "AI" ở mọi khung: {"có" if sheet.label_ok else f"không, thiếu {sheet.label_frames_missing} khung"}',
    ]
    if sheet.problems:
        lines += ["", "## Vấn đề", ""] + [f"- {p}" for p in sheet.problems]
    lines += ["", "Video chép nguyên từ bộ ghi của fork, không cắt ghép. Làm lại khi đổi nhân vật, sản phẩm hoặc cảnh."]
    return "\n".join(lines) + "\n"


def fork_analyzer(python: Path, fork_dir: Path = DEFAULT_FORK_DIR) -> Analyze:
    """Runs `ailive_ext.analyze` with the fork's python (its own venv has OpenCV) and reads `<prefix>.report.json`."""
    if not python.is_absolute():
        python = fork_dir.parents[1] / python  # LIVETALKING_PYTHON is relative to the repo root

    def run(prefix: Path) -> dict[str, Any] | None:
        # The exit code only says whether every analyzer check passed; the sheet judges length, sound and label itself.
        subprocess.run([str(python), "-m", "ailive_ext.analyze", str(prefix)], cwd=fork_dir, check=False)
        report = Path(f"{prefix}.report.json")
        if not report.exists():
            return None
        return json.loads(report.read_text(encoding="utf-8"))

    async def analyze(prefix: Path) -> dict[str, Any] | None:
        return await asyncio.to_thread(run, prefix)

    return analyze


# ---------- the run ----------


def _message(response: httpx.Response) -> str:
    try:
        body = response.json()
    except ValueError:
        return f"HTTP {response.status_code}"
    if isinstance(body, dict):
        return str(body.get("message") or body.get("error") or f"HTTP {response.status_code}")
    return f"HTTP {response.status_code}"


class BackupVideoMaker:
    """Runs the R7 steps against a running app and fork; `make` returns the sheet it wrote."""

    def __init__(
        self,
        app: httpx.AsyncClient,
        fork: httpx.AsyncClient,
        *,
        backup_dir: Path,
        analyze: Analyze,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        now: Callable[[], datetime] = lambda: datetime.now().astimezone(),
        progress: Callable[[str], None] = print,
    ) -> None:
        self.app = app
        self.fork = fork
        self.backup_dir = backup_dir
        self.analyze = analyze
        self.sleep = sleep
        self.now = now
        self.progress = progress

    async def make(self, seconds: float, content: str) -> BackupVideoSheet:
        check_request(seconds, content)
        health = await self._get(self.app, "/health", "App chưa bật", "Bật app (uv run uvicorn ...) rồi chạy lại")
        check_app(health)
        fork_health = await self._get(
            self.fork, "/ailive/health", "Fork LiveTalking không trả lời", "Bật fork: scripts/livetalking/run.ps1"
        )
        session = check_fork(fork_health)
        made_at = self.now()
        name = sheet_name(made_at, str(health["customer_id"]))

        started = await self.fork.post("/ailive/record/start", params={"sessionid": session, "name": name})
        if started.status_code != 200:
            raise BackupRefused(
                f"Fork không bật ghi được: {_message(started)}",
                "Nếu fork đang ghi dở: POST /ailive/record/stop rồi chạy lại",
            )
        prefix = Path(started.json()["prefix"])
        max_s = started.json().get("max_seconds")
        self.progress(f"Đang ghi {prefix}")

        show_may_run = False
        try:
            if max_s is not None and float(max_s) < seconds + RECORD_MARGIN_S:
                raise BackupRefused(
                    f"Fork chỉ ghi tối đa {float(max_s):g} giây (AILIVE_RECORD_MAX_S), cần ít nhất "
                    f"{seconds + RECORD_MARGIN_S:g}",
                    "Tăng AILIVE_RECORD_MAX_S trong .env (hoặc bỏ trống) rồi chạy lại scripts/livetalking/run.ps1",
                )
            show_may_run = True  # set before the call: a timeout after the app started the show must still end it
            show_id = await self._start_show(content)
            await self._run_for(seconds - CLOSING_ALLOWANCE_S, seconds)
            await self._end_show()
            show_may_run = False
            await self.sleep(TAIL_S)
            summary = await self._stop_recording(session)
        except BaseException:
            # Ctrl+C included: the live output must not keep a show nobody watches, and the fork must not keep writing.
            await self._abort(session, show_may_run)
            raise

        mp4 = Path(f"{prefix}.mp4")
        if not await asyncio.to_thread(mp4.exists):
            raise BackupFailed(f"Không thấy file ghi {mp4}")
        self.progress("Đang chấm bản ghi (ailive_ext.analyze)...")
        report = await self.analyze(prefix)
        recorded_s, has_audio, label_ok, missing, problems = check_recording(report, summary.get("stopped_by"))
        if summary.get("error"):
            problems.append(f"Bộ ghi của fork báo lỗi: {summary['error']}")

        self.backup_dir.mkdir(parents=True, exist_ok=True)
        video = (self.backup_dir / f"{name}.mp4").resolve()
        shutil.copyfile(mp4, video)
        sheet = BackupVideoSheet(
            name=name,
            video=str(video),
            made_at=made_at.isoformat(timespec="seconds"),
            customer_id=str(health["customer_id"]),
            avatar_id=str(health["avatar_id"]),
            catalog_version=str(health.get("catalog_version") or ""),
            content_source=content,  # type: ignore[arg-type]  # checked by check_request
            show_id=show_id,
            seconds=recorded_s,
            has_audio=has_audio,
            label_ok=label_ok,
            label_frames_missing=missing,
            ok=not problems,
            problems=tuple(problems),
        )
        (self.backup_dir / f"{name}.sheet.json").write_text(
            json.dumps(sheet.to_json(), ensure_ascii=False, indent=2), encoding="utf-8"
        )
        (self.backup_dir / f"{name}.sheet.md").write_text(render_markdown(sheet), encoding="utf-8")
        return sheet

    async def _get(self, client: httpx.AsyncClient, path: str, down: str, action: str) -> dict[str, Any]:
        try:
            response = await client.get(path)
        except httpx.TransportError as exc:
            raise BackupRefused(f"{down} ở {client.base_url}", action) from exc
        if response.status_code != 200:
            raise BackupRefused(f"{down} ở {client.base_url}: {_message(response)}", action)
        return response.json()

    async def _start_show(self, content: str) -> str:
        response = await self.app.post("/api/show/start", json={"content": content})
        if response.status_code != 200:
            raise BackupFailed(f"App không bắt đầu show: {_message(response)}")
        body = response.json()
        if body.get("already_running") or body.get("content") != content:
            raise BackupFailed("Đã có show khác đang chạy, video không ghi show của lệnh này")
        self.progress(f"Show {body['show_id']} bắt đầu, nội dung {content}")
        return str(body["show_id"])

    async def _show_state(self) -> str | None:
        snapshot = (await self.app.get("/api/show")).json()
        return None if snapshot is None else snapshot.get("state")

    async def _run_for(self, run_s: float, seconds: float) -> None:
        elapsed = 0.0
        while elapsed < run_s:
            step = min(PROGRESS_EVERY_S, run_s - elapsed)
            await self.sleep(step)
            elapsed += step
            state = await self._show_state()
            if state in (None, "ended"):
                raise BackupFailed(f"Show kết thúc sớm sau {elapsed:.0f} giây (xem trang điều khiển và log phiên)")
            self.progress(f"  {elapsed:.0f}/{seconds:g} giây, show {state}")

    async def _end_show(self) -> None:
        await self.app.post("/api/show/end")
        self.progress("Đang nói câu kết...")
        waited = 0.0
        while await self._show_state() != "ended":
            if waited >= END_WAIT_S:
                raise BackupFailed(f"Show chưa kết thúc sau {END_WAIT_S:g} giây kể từ lúc bấm kết thúc")
            await self.sleep(END_POLL_S)
            waited += END_POLL_S

    async def _stop_recording(self, session: str) -> dict[str, Any]:
        response = await self.fork.post(
            "/ailive/record/stop", params={"sessionid": session}, timeout=RECORD_STOP_TIMEOUT_S
        )
        if response.status_code != 200:
            raise BackupFailed(f"Fork không dừng ghi được: {_message(response)}")
        return response.json()

    async def _abort(self, session: str, show_may_run: bool) -> None:
        # Best effort: the error that brought us here is the one the operator must see.
        if show_may_run:
            try:
                await self.app.post("/api/show/end")
            except httpx.HTTPError:
                pass
        try:
            await self.fork.post("/ailive/record/stop", params={"sessionid": session}, timeout=RECORD_STOP_TIMEOUT_S)
        except httpx.HTTPError:
            pass


def render_result(sheet: BackupVideoSheet, backup_dir: Path) -> str:
    lines = [
        f"Kết quả: {'Đạt' if sheet.ok else 'Không đạt'}",
        f"  Video: {sheet.video}",
        f"  Tờ mô tả: {(backup_dir / f'{sheet.name}.sheet.md').resolve()}",
        f"  Độ dài {sheet.seconds:.1f} giây, tiếng {'có' if sheet.has_audio else 'không'}, "
        f'nhãn "AI" {"đủ" if sheet.label_ok else f"thiếu {sheet.label_frames_missing} khung"}',
    ]
    lines += [f"  - {p}" for p in sheet.problems]
    lines.append(f"  {NOTE}.")
    return "\n".join(lines)


def cli_backup_video(
    url: str,
    *,
    seconds: float,
    content: str,
    settings: Settings | None = None,
    fork_url: str | None = None,
    backup_dir: Path | None = None,
    analyze: Analyze | None = None,
    transport: httpx.AsyncBaseTransport | None = None,
    fork_transport: httpx.AsyncBaseTransport | None = None,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    now: Callable[[], datetime] | None = None,
) -> int:
    """Exit 0 when the sheet is ok, 1 when a check failed or the run broke, 2 when refused before starting."""
    if settings is None and (fork_url is None or backup_dir is None or analyze is None):
        from ai_live.core.config import get_settings

        settings = get_settings()
    if settings is not None:
        fork_url = fork_url or settings.livetalking_url
        backup_dir = backup_dir or settings.backup_video_dir
        analyze = analyze or fork_analyzer(settings.livetalking_python)
    assert fork_url is not None and backup_dir is not None and analyze is not None

    async def run() -> BackupVideoSheet:
        async with (
            httpx.AsyncClient(base_url=url.rstrip("/"), timeout=HTTP_TIMEOUT_S, transport=transport) as app,
            httpx.AsyncClient(base_url=fork_url.rstrip("/"), timeout=HTTP_TIMEOUT_S, transport=fork_transport) as fork,
        ):
            kwargs = {"now": now} if now is not None else {}
            maker = BackupVideoMaker(app, fork, backup_dir=backup_dir, analyze=analyze, sleep=sleep, **kwargs)
            return await maker.make(seconds, content)

    try:
        sheet = asyncio.run(run())
    except BackupRefused as exc:
        print(f"LỖI  {exc}\n  → {exc.action}")
        return 2
    except BackupFailed as exc:
        print(f"LỖI  {exc}\n  Show đã kết thúc, bản ghi đã dừng, chưa có video dự phòng mới.")
        return 1
    except KeyboardInterrupt:
        print("Đã dừng: show kết thúc, bản ghi đã dừng, không viết tờ mô tả.")
        return 130
    print(render_result(sheet, backup_dir))
    return 0 if sheet.ok else 1

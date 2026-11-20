"""Pre-demo readiness check (007 US1, data-model §1, research R8).

Every `check_*` is a pure function of values already read, so the table in data-model §1 is tested line by line without
an app. `run_readiness` gathers those values from the running app, `run_offline` from config and disk when the app is
down (the CLI). Neither calls an LLM, plays anything or touches the show (FR-004): the chain is read from its snapshot.
"""

from __future__ import annotations

import asyncio
import json
import time
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

import httpx

from ai_live.core.models import HostStatus, lipsync_label
from ai_live.ops.system import free_disk_gb, power_status

if TYPE_CHECKING:
    from ai_live.app.context import AppContext
    from ai_live.avatar.character import AvatarCharacter, UltralightInstall
    from ai_live.core.config import Settings
    from ai_live.products.models import ProductCatalog

FORK_HEALTH_TIMEOUT_S = 2.0
SHEET_SUFFIX = ".sheet.json"


class CheckStatus(StrEnum):
    OK = "ok"
    WARN = "warn"
    FAIL = "fail"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class ReadinessItem:
    id: str
    label: str
    status: CheckStatus
    message: str
    action: str | None = None

    def to_json(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "label": self.label,
            "status": self.status.value,
            "message": self.message,
            "action": self.action,
        }

    @classmethod
    def from_json(cls, raw: Mapping[str, Any]) -> ReadinessItem:
        return cls(raw["id"], raw["label"], CheckStatus(raw["status"]), raw["message"], raw.get("action"))


@dataclass(frozen=True)
class ReadinessResult:
    checked_at: str
    source: Literal["app", "offline"]
    ready: bool
    items: tuple[ReadinessItem, ...]
    manual: tuple[str, ...]
    duration_ms: int
    # 006: where the show goes out (`meet` | `obs`); information, not a check item (contracts/api.md §7).
    output_mode: str | None = None

    def to_json(self) -> dict[str, Any]:
        return {
            "checked_at": self.checked_at,
            "source": self.source,
            "ready": self.ready,
            "duration_ms": self.duration_ms,
            "output_mode": self.output_mode,
            "items": [item.to_json() for item in self.items],
            "manual": list(self.manual),
        }

    @classmethod
    def from_json(cls, raw: Mapping[str, Any]) -> ReadinessResult:
        return cls(
            checked_at=raw["checked_at"],
            source=raw["source"],
            ready=bool(raw["ready"]),
            items=tuple(ReadinessItem.from_json(item) for item in raw["items"]),
            manual=tuple(raw.get("manual") or ()),
            duration_ms=int(raw.get("duration_ms") or 0),
            output_mode=raw.get("output_mode"),
        )


# Fixed order of `items` (data-model §1): config first, then the parts, then the machine.
ITEM_IDS = (
    "app_env",
    "reply_engine",
    "tts_provider",
    "avatar_mode",
    "recording",
    "fork",
    "character",
    "lipsync_model",
    "host",
    "content",
    "scene",
    "ai_label",
    "backup_video",
    "llm_chain",
    "power",
    "disk",
)
LABELS = {
    "app_env": "Chế độ chạy",
    "reply_engine": "Bộ trả lời",
    "tts_provider": "Giọng đọc",
    "avatar_mode": "Chế độ nhân vật",
    "recording": "Ghi luồng thử",
    "fork": "Máy nhép miệng (fork)",
    "character": "Nhân vật và khách",
    "lipsync_model": "Model nhép miệng",
    "host": "Màn hình host",
    "content": "Nội dung sản phẩm",
    "scene": "Cảnh live",
    "ai_label": "Nhãn AI",
    "backup_video": "Video dự phòng",
    "llm_chain": "Chuỗi model LLM",
    "power": "Nguồn điện",
    "disk": "Ổ đĩa",
}
# What no machine can check (FR-005), from runbook §2–§3.
MANUAL_CHECKS = (
    "Văn bản đồng ý (hình + giọng) của người mẫu đã ký, bản ký lưu ngoài git",
    "Đã thử chia sẻ tab /host có âm thanh vào Meet từ một máy khác: thấy nhân vật, nhãn AI, nghe tiếng khớp miệng",
    "Không có RunPod nào đang bật",
)
APP_DOWN = "App chưa bật"
APP_DOWN_ACTION = "Bật app (runbook §3 bước 3) rồi kiểm lại"


def _item(item_id: str, status: CheckStatus, message: str, action: str | None = None) -> ReadinessItem:
    # An item that passes has nothing to do (data-model §1).
    return ReadinessItem(item_id, LABELS[item_id], status, message, None if status is CheckStatus.OK else action)


def _ok(item_id: str, message: str) -> ReadinessItem:
    return _item(item_id, CheckStatus.OK, message)


# ---------- Config (runbook §6) ----------


def check_app_env(value: str) -> ReadinessItem:
    if value == "dev":
        return _item(
            "app_env",
            CheckStatus.FAIL,
            "APP_ENV=dev: mở thêm route thử nghiệm và /docs",
            "Đặt APP_ENV=demo trong .env rồi bật lại app",
        )
    return _ok("app_env", f"APP_ENV={value}")


def check_reply_engine(value: str) -> ReadinessItem:
    if value == "fake":
        return _item(
            "reply_engine",
            CheckStatus.FAIL,
            "REPLY_ENGINE=fake: câu nói vô nghĩa, chỉ để thử luồng",
            "Đặt REPLY_ENGINE=chain trong .env rồi bật lại app",
        )
    if value == "gemini":
        return _item(
            "reply_engine",
            CheckStatus.WARN,
            "REPLY_ENGINE=gemini: runbook dùng chuỗi model (chain)",
            "Đặt REPLY_ENGINE=chain nếu không cố ý dùng Gemini",
        )
    return _ok("reply_engine", f"REPLY_ENGINE={value}")


def check_tts_provider(value: str) -> ReadinessItem:
    if value == "fake":
        return _item(
            "tts_provider",
            CheckStatus.FAIL,
            "TTS_PROVIDER=fake: không có giọng thật",
            "Đặt TTS_PROVIDER=vieneu trong .env rồi bật lại app",
        )
    if value == "gemini":
        return _item(
            "tts_provider",
            CheckStatus.WARN,
            "TTS_PROVIDER=gemini: hạn mức free chỉ đủ vài câu",
            "Đặt TTS_PROVIDER=vieneu cho buổi demo",
        )
    return _ok("tts_provider", f"TTS_PROVIDER={value}")


def check_avatar_mode(value: str) -> ReadinessItem:
    if value == "static":
        return _item(
            "avatar_mode",
            CheckStatus.WARN,
            "AVATAR_MODE=static: người xem chỉ thấy ảnh tĩnh, không nhép miệng",
            "Đặt AVATAR_MODE=livetalking nếu không cố ý chạy ảnh tĩnh",
        )
    return _ok("avatar_mode", f"AVATAR_MODE={value}")


# ---------- Fork (005) ----------


@dataclass(frozen=True)
class ForkHealth:
    """What `GET /ailive/health` answered; `reachable=False` when it did not answer in time."""

    reachable: bool
    sessions: tuple[str, ...] = ()
    record_enabled: bool | None = None  # None: a fork older than 007 that does not report it
    error: str | None = None
    fork_commit: str | None = None
    lipsync: dict[str, Any] | None = None  # 011: the model block; None from a fork older than 011

    @classmethod
    def from_body(cls, body: Mapping[str, Any]) -> ForkHealth:
        record = body.get("record_enabled")
        return cls(
            reachable=body.get("ok") is True,
            sessions=tuple(str(s) for s in body.get("sessions") or ()),
            record_enabled=record if isinstance(record, bool) else None,
            error=None if body.get("ok") is True else "fork không báo ok",
            fork_commit=str(body["fork_commit"]) if body.get("fork_commit") else None,
            lipsync=dict(body["lipsync"]) if isinstance(body.get("lipsync"), dict) else None,
        )


def check_recording(avatar_mode: str, fork: ForkHealth | None) -> ReadinessItem:
    if avatar_mode != "livetalking":
        return _ok("recording", "Không dùng nhép miệng (ảnh tĩnh), không có fork để ghi")
    if fork is None or not fork.reachable:
        return _item("recording", CheckStatus.UNKNOWN, "Không hỏi được fork", "Xem mục máy nhép miệng")
    if fork.record_enabled is None:
        return _item(
            "recording",
            CheckStatus.UNKNOWN,
            "Fork bản cũ không báo đang ghi hay không",
            "Kiểm tay: biến AILIVE_RECORD_DIR phải trống lúc bật fork",
        )
    if fork.record_enabled:
        return _item(
            "recording",
            CheckStatus.FAIL,
            "Fork đang bật ghi luồng thử (AILIVE_RECORD_DIR): tốn đĩa và lưu mặt, giọng người mẫu",
            "Tắt fork, xóa AILIVE_RECORD_DIR khỏi môi trường rồi bật lại fork",
        )
    return _ok("recording", "Fork không ghi luồng")


def check_fork(
    avatar_mode: str,
    fork: ForkHealth | None,
    *,
    active_mode: str | None = None,
    lipsync_connected: bool | None = None,
) -> ReadinessItem:
    """`active_mode`/`lipsync_connected` come from the running app; both None when checking offline."""
    if avatar_mode != "livetalking":
        return _ok("fork", "Không dùng nhép miệng (ảnh tĩnh)")
    if fork is None or not fork.reachable:
        detail = f" ({fork.error})" if fork is not None and fork.error else ""
        return _item(
            "fork",
            CheckStatus.FAIL,
            f"Không nối được fork nhép miệng{detail}",
            "Bật fork: powershell scripts/livetalking/run.ps1, chờ /ailive/health báo ok",
        )
    if active_mode == "static":
        return _item(
            "fork",
            CheckStatus.FAIL,
            "Người xem đang thấy ảnh tĩnh vì nhép miệng lỗi liên tiếp",
            'Bấm "Bật lại nhép miệng" trên trang điều khiển; lỗi lại thì bật lại fork',
        )
    if lipsync_connected is False or not fork.sessions:
        return _item(
            "fork",
            CheckStatus.WARN,
            "Fork chạy nhưng chưa có phiên của màn hình host",
            'Mở /host và bấm "Bắt đầu" để nối hình nhép miệng',
        )
    return _ok("fork", "Fork chạy, đã nối với màn hình host")


# ---------- Character, host, content, scene, label ----------


def check_character(
    customer_id: str,
    avatar_id: str,
    character_id: str | None = None,
    *,
    prepared_commit: str | None = None,
    running_commit: str | None = None,
) -> ReadinessItem:
    """`prepared_commit` is `character.json` `prepare.fork_commit`, `running_commit` what `/ailive/health` reports."""
    missing = [name for name, value in (("CUSTOMER_ID", customer_id), ("AVATAR_ID", avatar_id)) if not value.strip()]
    if missing:
        return _item(
            "character",
            CheckStatus.FAIL,
            f"Thiếu {' và '.join(missing)}: không biết nhân vật thuộc khách nào (ràng buộc 3)",
            "Điền CUSTOMER_ID và AVATAR_ID của khách demo trong .env rồi bật lại app",
        )
    loaded = f", đã nạp nhân vật {character_id}" if character_id else ""
    if prepared_commit and running_commit and prepared_commit != running_commit:
        # Face crops and clip caches come from the fork that prepared them; another fork build may read them wrongly.
        return _item(
            "character",
            CheckStatus.WARN,
            f"Nhân vật {avatar_id} chuẩn bị với fork {prepared_commit[:8]}, fork đang chạy là {running_commit[:8]}",
            "Chuẩn bị lại: uv run python -m ai_live.avatar prepare <thư mục nhân vật>, "
            f"hoặc bật đúng bản fork {prepared_commit[:8]}",
        )
    return _ok("character", f"Khách {customer_id}, nhân vật {avatar_id}{loaded}")


def check_lipsync_model(
    avatar_mode: str,
    model: str,
    teacher: str,
    character_id: str | None,
    lipsync_models: Iterable[str] | None,
    *,
    install: UltralightInstall | None = None,
    install_problem: str | None = None,
    fork: ForkHealth | None = None,
) -> ReadinessItem:
    """011 contract §6: the configured model fits the character, is installed (Ultralight) and is what the fork runs.

    `install`/`install_problem` are `read_ultralight_install`'s result (hashed in a thread by the caller). The fork
    step compares `model` only; teacher, character and checkpoint are compared by US3 (T054).
    """
    if avatar_mode != "livetalking":
        return _ok("lipsync_model", "Không dùng nhép miệng (ảnh tĩnh)")
    if lipsync_models is None:
        # The character item already says why it could not be read.
        return _item(
            "lipsync_model",
            CheckStatus.UNKNOWN,
            "Chưa đọc được nhân vật nên chưa biết model nhép miệng",
            "Sửa mục Nhân vật trước",
        )
    who = character_id or "đang dùng"
    if model not in lipsync_models:
        return _item(
            "lipsync_model",
            CheckStatus.FAIL,
            f"Nhân vật {who} không có model {model}",
            "Đặt LIVETALKING_MODEL bằng một model trong lipsync_models của character.json rồi bật lại fork và app",
        )
    ultralight = model == "ultralight"
    if ultralight and install is None:
        detail = f" ({install_problem})" if install_problem else ""
        return _item(
            "lipsync_model",
            CheckStatus.FAIL,
            f"Chưa cài model Ultralight thầy {teacher} cho {who}{detail}",
            "Cài model đã huấn luyện: cd vendor/livetalking; .venv/Scripts/python -m ailive_ext.ultralight install "
            f"<thư mục tải>/ultralight_out/{who}/{teacher} --video <video thầy> (quickstart 011)",
        )
    label = "Model: " + lipsync_label(model, teacher if ultralight else None, character_id)
    if fork is None or not fork.reachable:
        return _ok("lipsync_model", f"{label} (chưa kiểm fork)")
    # A fork older than 011 sends no block and can only run Wav2Lip.
    running = fork.lipsync.get("model") if fork.lipsync is not None else "wav2lip"
    if running != model:
        return _item(
            "lipsync_model",
            CheckStatus.FAIL,
            f"Phần nhép miệng đang chạy {running}, cấu hình là {model}: bật lại fork",
            "Tắt fork rồi bật lại: powershell scripts/livetalking/run.ps1 (đọc LIVETALKING_MODEL trong .env)",
        )
    return _ok("lipsync_model", label)


def check_host(
    host_ready: bool | None,
    status: HostStatus | None,
    active_mode: str | None,
    *,
    output_mode: str = "meet",
    role: str | None = None,
    app_port: int = 8000,
) -> ReadinessItem:
    """`host_ready=None` means the app is down (offline check). `role` is who holds playback (006 `host_role`)."""
    if host_ready is None:
        return _item("host", CheckStatus.FAIL, APP_DOWN, APP_DOWN_ACTION)
    if output_mode == "obs":
        return _check_obs_source(host_ready, status, active_mode, role, app_port)
    if not host_ready:
        return _item(
            "host",
            CheckStatus.FAIL,
            'Màn hình host chưa mở hoặc chưa bấm "Bắt đầu" (chưa mở khóa âm thanh)',
            'Mở trang /host của app trên Chrome và bấm "Bắt đầu"',
        )
    if status is None:
        return _item(
            "host",
            CheckStatus.WARN,
            "Màn hình host đã sẵn sàng nhưng chưa gửi nhịp trạng thái (trang bản cũ?)",
            'Tải lại trang /host (Ctrl+F5) rồi bấm "Bắt đầu"',
        )
    if active_mode == "livetalking":
        if status.video_muted or status.video_paused:
            return _item(
                "host",
                CheckStatus.FAIL,
                "Hình nhép miệng trên /host đang bị tắt tiếng hoặc dừng",
                "Bấm vào trang /host để phát tiếp, bỏ tắt tiếng của tab",
            )
    elif status.audio != "running":
        return _item(
            "host",
            CheckStatus.FAIL,
            f"Âm thanh trên /host chưa chạy (trạng thái {status.audio or 'không rõ'})",
            'Bấm "Bắt đầu" trên trang /host để mở khóa âm thanh',
        )
    return _ok("host", "Màn hình host đã mở, âm thanh sẵn sàng")


def _check_obs_source(
    host_ready: bool, status: HostStatus | None, active_mode: str | None, role: str | None, app_port: int
) -> ReadinessItem:
    """`OUTPUT_MODE=obs`: the playing connection must be the OBS Browser Source (006 contracts/api.md §7)."""
    if not host_ready:
        return _item(
            "host",
            CheckStatus.FAIL,
            "Nguồn OBS chưa nối",
            f"Trong OBS thêm Browser Source, URL http://127.0.0.1:{app_port}/obs, 720×1248, "
            'bật "Control audio via OBS" (runbook §8)',
        )
    if role != "obs":
        return _item(
            "host",
            CheckStatus.FAIL,
            "Đang phát ở trang host trên Chrome, chưa phải OBS",
            "Thêm nguồn /obs trong OBS (nguồn OBS sẽ nhận quyền phát), rồi đóng tab /host",
        )
    if status is None:
        return _item(
            "host",
            CheckStatus.WARN,
            "Nguồn OBS đã nối nhưng chưa gửi nhịp trạng thái",
            "Chuột phải nguồn trong OBS → Refresh",
        )
    if active_mode == "livetalking":
        if status.video_muted or status.video_paused:
            return _item(
                "host",
                CheckStatus.FAIL,
                "Hình nhép miệng trong nguồn OBS đang tắt tiếng hoặc dừng",
                "Chuột phải nguồn → Refresh",
            )
    elif status.audio != "running":
        return _item(
            "host",
            CheckStatus.FAIL,
            f"Âm thanh trong nguồn OBS chưa chạy (trạng thái {status.audio or 'không rõ'})",
            "Chuột phải nguồn → Refresh; nếu mở /obs trên Chrome thường thì dùng OBS thay vì Chrome",
        )
    return _ok("host", "Nguồn OBS đã nối, âm thanh sẵn sàng")


def check_content(
    catalog: ProductCatalog | None, error: str | None = None, *, changed_after_load: bool = False
) -> ReadinessItem:
    if error is not None:
        return _item(
            "content",
            CheckStatus.FAIL,
            f"File nội dung lỗi: {error}",
            "Sửa file Word theo lỗi trên (uv run python -m ai_live.products validate <file>)",
        )
    if catalog is None or not catalog.products:
        return _item(
            "content", CheckStatus.FAIL, "Chưa có sản phẩm nào", "Nạp file nội dung của khách trên trang điều khiển"
        )
    summary = f"{len(catalog.products)} sản phẩm từ {catalog.source_name} (bản {catalog.version})"
    if changed_after_load:
        return _item(
            "content",
            CheckStatus.WARN,
            f"{summary}; file đã sửa sau khi nạp",
            "Nạp lại file nội dung trên trang điều khiển để show dùng bản mới",
        )
    return _ok("content", summary)


def check_scene(enabled: bool, issues: Iterable[Mapping[str, Any]] = ()) -> ReadinessItem:
    """`issues` are scene issues as `SceneIssue.to_json()` gives them."""
    if not enabled:
        return _ok("scene", "Không bật cảnh live (SCENE_ENABLED=false)")
    issues = list(issues)
    placeholders = sorted({str(i.get("product_id")) for i in issues if i.get("code") == "placeholder"})
    if placeholders:
        return _item(
            "scene",
            CheckStatus.FAIL,
            f"Bộ cảnh còn ảnh mẫu: {', '.join(placeholders)}",
            "Thay bằng ảnh thật của khách (009 quickstart) rồi kiểm lại bộ cảnh",
        )
    # 012 FR-019: an uploaded image without confirmed rights, or a manifest nobody can read, must stop the session;
    # other scene errors only leave a part undrawn and stay a warning as in 009/007.
    blocking = [i for i in issues if i.get("code") in ("missing_confirmation", "bad_uploads")]
    if blocking:
        return _item(
            "scene",
            CheckStatus.FAIL,
            f"Ảnh tải lên chưa dùng được ({len(blocking)} lỗi): {blocking[0].get('message')}",
            "Mở mục Ảnh sản phẩm trên trang điều khiển: xác nhận quyền dùng ảnh hoặc gỡ ảnh, "
            "rồi chạy uv run python -m ai_live.scene check",
        )
    errors = [i for i in issues if i.get("level") == "error"]
    if errors:
        return _item(
            "scene",
            CheckStatus.WARN,
            f"Bộ cảnh có {len(errors)} lỗi, phần lỗi không được vẽ: {errors[0].get('message')}",
            "Chạy uv run python -m ai_live.scene check và sửa theo lời nhắn",
        )
    return _ok("scene", "Bộ cảnh dùng ảnh thật của khách")


def check_ai_label(text: str) -> ReadinessItem:
    if not text.strip():
        return _item(
            "ai_label",
            CheckStatus.FAIL,
            "Nhãn AI đang rỗng: người xem không biết host là AI",
            'Đặt AI_LABEL_TEXT (mặc định "AI-GENERATED CONTENT") trong .env rồi bật lại app và fork',
        )
    return _ok("ai_label", f'Nhãn "{text}" được ghép vào hình')


# ---------- Backup video (US4) ----------


def latest_sheet(directory: Path) -> tuple[dict[str, Any] | None, str | None]:
    """Newest `<name>.sheet.json` in `directory` and a problem text when it cannot be used."""
    try:
        sheets = sorted(directory.glob(f"*{SHEET_SUFFIX}"), key=lambda p: p.stat().st_mtime)
    except OSError as exc:
        return None, f"không đọc được thư mục {directory}: {exc}"
    if not sheets:
        return None, None
    path = sheets[-1]
    try:
        sheet = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return None, f"tờ mô tả {path.name} hỏng: {exc}"
    if not isinstance(sheet, dict):
        return None, f"tờ mô tả {path.name} hỏng"
    video = Path(str(sheet.get("video") or ""))
    if not video.is_file():
        return sheet, f"thiếu file video {video.name or '(trống)'} của tờ mô tả {path.name}"
    return sheet, None


def check_backup_video(
    sheet: Mapping[str, Any] | None,
    problem: str | None,
    *,
    customer_id: str,
    avatar_id: str,
    catalog_version: str | None,
) -> ReadinessItem:
    make = "Làm video dự phòng: uv run python -m ai_live.ops backup-video (007 quickstart §5)"
    if sheet is None:
        return _item("backup_video", CheckStatus.FAIL, problem or "Chưa có video dự phòng", make)
    if problem is not None:
        return _item("backup_video", CheckStatus.FAIL, problem, make)
    if not sheet.get("ok"):
        problems = "; ".join(str(p) for p in sheet.get("problems") or ()) or "kiểm không đạt"
        return _item("backup_video", CheckStatus.FAIL, f"Video {sheet.get('name')} kiểm không đạt: {problems}", make)
    differs = [
        what
        for what, have, want in (
            ("khách", sheet.get("customer_id"), customer_id),
            ("nhân vật", sheet.get("avatar_id"), avatar_id),
            ("bản nội dung", sheet.get("catalog_version"), catalog_version),
        )
        if want is not None and have != want
    ]
    if differs:
        return _item(
            "backup_video",
            CheckStatus.WARN,
            f"Video {sheet.get('name')} làm với {', '.join(differs)} khác lúc này",
            f"Làm lại nếu cần khớp: {make}",
        )
    return _ok("backup_video", f"Video {sheet.get('name')} ({sheet.get('seconds')} giây) đã kiểm đạt")


# ---------- LLM chain (008), power, disk ----------


def check_llm_chain(
    reply_engine: str, snapshot: Mapping[str, Any] | None, *, app_running: bool = True
) -> ReadinessItem:
    if reply_engine != "chain":
        return _ok("llm_chain", "Không dùng chuỗi model")
    if not app_running:
        return _item("llm_chain", CheckStatus.FAIL, APP_DOWN, APP_DOWN_ACTION)
    if snapshot is None:
        return _item(
            "llm_chain",
            CheckStatus.UNKNOWN,
            "Không đọc được trạng thái chuỗi model",
            "Xem khu Model LLM trên trang điều khiển",
        )
    entries = list(snapshot.get("entries") or ())
    ready = [e for e in entries if e.get("status") == "ready"]
    if not ready:
        return _item(
            "llm_chain",
            CheckStatus.FAIL,
            "Không model nào sẵn sàng: show sẽ đọc nguyên văn file sản phẩm",
            "Chờ hết giờ nghỉ của model (khu Model LLM) hoặc kiểm khóa API trong .env",
        )
    resting = [e for e in entries if e.get("status") == "resting"]
    if resting:
        names = ", ".join(f"{e.get('label')} ({e.get('reason')})" for e in resting)
        return _item(
            "llm_chain",
            CheckStatus.WARN,
            f"{len(ready)}/{len(entries)} model sẵn sàng; đang nghỉ: {names}",
            "Show vẫn chạy bằng model dự phòng; theo dõi khu Model LLM",
        )
    return _ok("llm_chain", f"{len(ready)}/{len(entries)} model sẵn sàng (trạng thái gần nhất, không gọi thử)")


def check_power(status: str | None) -> ReadinessItem:
    if status == "ac":
        return _ok("power", "Đang cắm sạc")
    if status == "battery":
        return _item("power", CheckStatus.WARN, "Đang chạy pin: fps nhép miệng có thể giảm", "Cắm sạc laptop")
    return _item(
        "power", CheckStatus.UNKNOWN, "Không đọc được nguồn điện trên máy này", "Kiểm tay: laptop đang cắm sạc"
    )


def check_disk(free_gb: float | None, min_gb: float, path: Path) -> ReadinessItem:
    if free_gb is None:
        return _item("disk", CheckStatus.UNKNOWN, f"Không đọc được chỗ trống của {path}", "Kiểm tay chỗ trống ổ đĩa")
    if free_gb < min_gb:
        return _item(
            "disk",
            CheckStatus.WARN,
            f"Còn {free_gb:.1f} GB trống ở ổ chứa {path} (dưới {min_gb:g} GB)",
            "Dọn bớt file (bản ghi thử, video cũ) trước buổi demo",
        )
    return _ok("disk", f"Còn {free_gb:.1f} GB trống")


# ---------- Result ----------


def build_result(
    items: Iterable[ReadinessItem],
    source: Literal["app", "offline"],
    started: float,
    *,
    clock=time.perf_counter,
    output_mode: str | None = None,
) -> ReadinessResult:
    by_id = {item.id: item for item in items}
    ordered = tuple(by_id[i] for i in ITEM_IDS if i in by_id)
    return ReadinessResult(
        checked_at=datetime.now(UTC).isoformat(timespec="milliseconds"),
        source=source,
        ready=all(item.status is not CheckStatus.FAIL for item in ordered),
        items=ordered,
        manual=MANUAL_CHECKS,
        duration_ms=round((clock() - started) * 1000),
        output_mode=output_mode,
    )


async def fetch_fork_health(url: str, *, transport: httpx.AsyncBaseTransport | None = None) -> ForkHealth:
    try:
        async with httpx.AsyncClient(timeout=FORK_HEALTH_TIMEOUT_S, transport=transport) as client:
            response = await client.get(f"{url.rstrip('/')}/ailive/health")
            response.raise_for_status()
            body = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        return ForkHealth(reachable=False, error=type(exc).__name__)
    if not isinstance(body, dict):
        return ForkHealth(reachable=False, error="trả lời không phải JSON object")
    return ForkHealth.from_body(body)


def _machine_items(settings: Settings) -> list[ReadinessItem]:
    """Blocking: power (Windows API) and disk; run in a thread."""
    path = settings.session_data_dir
    try:
        free: float | None = free_disk_gb(path)
    except OSError:
        free = None
    return [check_power(power_status()), check_disk(free, settings.readiness_min_free_gb, path)]


def _config_items(settings: Settings) -> list[ReadinessItem]:
    return [
        check_app_env(settings.app_env),
        check_reply_engine(settings.reply_engine),
        check_tts_provider(settings.tts_provider),
        check_avatar_mode(settings.avatar_mode),
        check_ai_label(settings.ai_label_text),
    ]


def _backup_item(settings: Settings, catalog_version: str | None) -> ReadinessItem:
    sheet, problem = latest_sheet(settings.backup_video_dir)
    return check_backup_video(
        sheet, problem, customer_id=settings.customer_id, avatar_id=settings.avatar_id, catalog_version=catalog_version
    )


def _file_changed_after_load(settings: Settings, catalog: ProductCatalog) -> bool:
    # Only when the loaded catalog came from that file; an upload on the control page has no file to compare.
    path = settings.product_data_path
    if catalog.source_name != path.name:
        return False
    try:
        return datetime.fromtimestamp(path.stat().st_mtime, UTC) > catalog.loaded_at
    except OSError:
        return False


async def run_readiness(ctx: AppContext, *, fork_transport: httpx.AsyncBaseTransport | None = None) -> ReadinessResult:
    """Check the running app (`GET /api/readiness`). Reads state only; never calls the LLM or plays anything."""
    started = time.perf_counter()
    settings = ctx.settings
    livetalking = settings.avatar_mode == "livetalking"
    fork = await fetch_fork_health(settings.livetalking_url, transport=fork_transport) if livetalking else None
    mode = getattr(ctx.renderer, "mode", None)
    active_mode = getattr(mode, "active", None) or settings.avatar_mode
    health = getattr(getattr(ctx.renderer, "lipsync", None), "health", None)
    catalog = ctx.store.catalog
    scene_issues = ctx.scene.status().get("issues", []) if ctx.scene is not None else []
    character = ctx.character
    install, install_problem = await _ultralight_install(settings, character)

    def blocking() -> list[ReadinessItem]:
        return [
            *_machine_items(settings),
            _backup_item(settings, catalog.version),
            check_content(catalog, changed_after_load=_file_changed_after_load(settings, catalog)),
        ]

    items = [
        *_config_items(settings),
        check_recording(settings.avatar_mode, fork),
        check_fork(
            settings.avatar_mode,
            fork,
            active_mode=active_mode,
            lipsync_connected=getattr(health, "connected", None) if livetalking else None,
        ),
        check_character(
            settings.customer_id,
            settings.avatar_id,
            character.character_id if character else None,
            prepared_commit=_prepared_commit(character),
            running_commit=fork.fork_commit if fork is not None else None,
        ),
        _lipsync_model_item(settings, character, install, install_problem, fork),
        check_host(
            ctx.renderer.host_ready,
            getattr(ctx.renderer, "host_status", None),
            active_mode,
            output_mode=settings.output_mode,
            role=getattr(ctx.renderer, "host_role", None),
            app_port=settings.app_port,
        ),
        check_scene(ctx.scene is not None and ctx.scene.enabled, scene_issues),
        check_llm_chain(settings.reply_engine, dict(ctx.chain.snapshot()) if ctx.chain is not None else None),
        *await asyncio.to_thread(blocking),
    ]
    return build_result(items, "app", started, output_mode=settings.output_mode)


async def _ultralight_install(
    settings: Settings, character: AvatarCharacter | None
) -> tuple[UltralightInstall | None, str | None]:
    """The install record of the configured teacher, read only when it matters; hashing ~49 MB runs in a thread."""
    if settings.avatar_mode != "livetalking" or settings.livetalking_model != "ultralight" or character is None:
        return None, None
    from ai_live.avatar.character import read_ultralight_install

    return await asyncio.to_thread(
        read_ultralight_install, character.avatar_dir, settings.livetalking_ultralight_teacher
    )


def _lipsync_model_item(
    settings: Settings,
    character: AvatarCharacter | None,
    install: UltralightInstall | None,
    install_problem: str | None,
    fork: ForkHealth | None,
) -> ReadinessItem:
    return check_lipsync_model(
        settings.avatar_mode,
        settings.livetalking_model,
        settings.livetalking_ultralight_teacher,
        character.character_id if character is not None else None,
        character.lipsync_models if character is not None else None,
        install=install,
        install_problem=install_problem,
        fork=fork,
    )


def _prepared_commit(character: AvatarCharacter | None) -> str | None:
    return character.prepare.fork_commit if character is not None and character.prepare is not None else None


def _offline_character(settings: Settings) -> AvatarCharacter | None:
    """The character folder as on disk; None when it cannot be read (`python -m ai_live.avatar check` reports why)."""
    from ai_live.avatar.character import CharacterError, load_character

    try:
        return load_character(settings.avatar_dir)
    except (CharacterError, OSError, ValueError):
        return None


def _offline_content(settings: Settings) -> tuple[ProductCatalog | None, str | None]:
    from ai_live.products.docx_loader import load_catalog_file
    from ai_live.products.models import ContentLoadError

    try:
        return load_catalog_file(settings.product_data_path, settings.content_max_bytes), None
    except ContentLoadError as exc:
        return None, "; ".join(issue.message for issue in exc.issues[:3])
    except OSError as exc:
        return None, f"không đọc được {settings.product_data_path}: {exc.strerror or exc}"


def _offline_scene(settings: Settings, catalog: ProductCatalog | None) -> list[dict[str, Any]]:
    from ai_live.scene.loader import load_scene_set

    product_ids = [p.id for p in catalog.products] if catalog is not None else []
    scene = load_scene_set(settings.scene_dir, product_ids, customer_id=settings.customer_id)
    return [issue.to_json() for issue in scene.issues]


async def run_offline(settings: Settings, *, fork_transport: httpx.AsyncBaseTransport | None = None) -> ReadinessResult:
    """What the CLI can still check when the app is down (research R8): config, files, fork, machine."""
    started = time.perf_counter()
    livetalking = settings.avatar_mode == "livetalking"
    fork = await fetch_fork_health(settings.livetalking_url, transport=fork_transport) if livetalking else None

    def blocking() -> list[ReadinessItem]:
        catalog, error = _offline_content(settings)
        scene_issues = _offline_scene(settings, catalog) if settings.scene_enabled else []
        return [
            check_content(catalog, error),
            check_scene(settings.scene_enabled, scene_issues),
            _backup_item(settings, catalog.version if catalog is not None else None),
            *_machine_items(settings),
        ]

    character = await asyncio.to_thread(_offline_character, settings) if livetalking else None
    install, install_problem = await _ultralight_install(settings, character)
    items = [
        *_config_items(settings),
        check_recording(settings.avatar_mode, fork),
        check_fork(settings.avatar_mode, fork),
        check_character(
            settings.customer_id,
            settings.avatar_id,
            prepared_commit=_prepared_commit(character),
            running_commit=fork.fork_commit if fork is not None else None,
        ),
        _lipsync_model_item(settings, character, install, install_problem, fork),
        check_host(None, None, None),
        check_llm_chain(settings.reply_engine, None, app_running=False),
        *await asyncio.to_thread(blocking),
    ]
    return build_result(items, "offline", started, output_mode=settings.output_mode)


# ---------- CLI (contracts/cli.md `readiness`) ----------

CLI_TIMEOUT_S = 10.0
OUTPUT_LABELS = {"obs": "OBS (nguồn Browser Source /obs)", "meet": "Meet (chia sẻ tab /host)"}
MARKS = {CheckStatus.OK: "ĐẠT ", CheckStatus.WARN: "CHÚ Ý", CheckStatus.FAIL: "LỖI ", CheckStatus.UNKNOWN: "?    "}


def render_text(result: ReadinessResult) -> str:
    where = "app đang chạy" if result.source == "app" else "app chưa bật, chỉ kiểm phần không cần app"
    lines = [f"Kiểm tra trước demo ({where}), {result.duration_ms} ms"]
    if result.output_mode:
        lines.append(f"Đầu ra: {OUTPUT_LABELS.get(result.output_mode, result.output_mode)}")
    lines.append("")
    for item in result.items:
        lines.append(f"{MARKS[item.status]}  {item.label}: {item.message}")
        if item.action:
            lines.append(f"       → {item.action}")
    lines += ["", "Việc tự xác nhận:"]
    lines += [f"  [ ] {task}" for task in result.manual]
    lines += ["", "Kết luận: SẴN SÀNG" if result.ready else "Kết luận: CHƯA SẴN SÀNG (còn mục LỖI)"]
    return "\n".join(lines)


async def fetch_or_offline(
    url: str,
    settings: Settings | None = None,
    *,
    transport: httpx.AsyncBaseTransport | None = None,
    fork_transport: httpx.AsyncBaseTransport | None = None,
) -> ReadinessResult:
    """Ask the running app; when nothing answers, check what can be checked without it (research R8)."""
    try:
        async with httpx.AsyncClient(timeout=CLI_TIMEOUT_S, transport=transport) as client:
            response = await client.get(f"{url.rstrip('/')}/api/readiness")
            response.raise_for_status()
            return ReadinessResult.from_json(response.json())
    except httpx.TransportError:
        pass
    if settings is None:
        from ai_live.core.config import get_settings

        settings = get_settings()
    return await run_offline(settings, fork_transport=fork_transport)


def cli_readiness(
    url: str,
    *,
    as_json: bool = False,
    settings: Settings | None = None,
    transport: httpx.AsyncBaseTransport | None = None,
    fork_transport: httpx.AsyncBaseTransport | None = None,
) -> int:
    """Exit 0 when ready, 1 when not."""
    try:
        result = asyncio.run(fetch_or_offline(url, settings, transport=transport, fork_transport=fork_transport))
    except (httpx.HTTPStatusError, ValueError, KeyError) as exc:
        # The app answered, so it is not "down": checking offline would hide that it is broken.
        print(f"LỖI  App ở {url} trả lời nhưng không đọc được kết quả kiểm tra: {exc}")
        return 1
    if as_json:
        print(json.dumps(result.to_json(), ensure_ascii=False, indent=2))
    else:
        print(render_text(result))
    return 0 if result.ready else 1

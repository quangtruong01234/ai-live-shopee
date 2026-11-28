"""Character folder `AVATAR_DIR` (005 data-model §2–§3, 011 data-model §2): load, session checks and `prepare`.

The app only checks that files exist and the records are complete; decoding clips and finding faces is the fork's job
(`ailive_ext.prepare`, run in the fork's own venv because it needs torch).
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

from ai_live.core.logging import log_event

if TYPE_CHECKING:
    from ai_live.core.config import Settings

logger = logging.getLogger(__name__)

ClipKind = Literal["idle", "talk"]
LipsyncModel = Literal["wav2lip", "ultralight"]
PrepareStatus = Literal["preparing", "ready", "failed"]
ForkRun = Callable[[list[str], Path], Awaitable[tuple[int, str, str]]]

SCHEMA_VERSION = 1
PROVENANCE_KIND = "ai_generated_fictional_face"
_ID_RE = re.compile(r"^[a-z0-9_-]{1,64}$")
_FACE_SUFFIXES = {".png", ".jpg", ".jpeg"}
_CLIP_KINDS: tuple[ClipKind, ...] = ("idle", "talk")
_LIPSYNC_MODELS: tuple[LipsyncModel, ...] = ("wav2lip", "ultralight")
# Same bounds as `layout.desk_top` in the scene loader (009), so a desk drawn in the image fits the layout maths.
DESK_TOP_RANGE = (0.55, 0.92)
HandsZone = tuple[float, float, float, float]
_PROVENANCE_TEXT_FIELDS = ("character_id", "created_by", "created_at", "platform")
# Written by the fork's `ailive_ext.ultralight install` next to the trained model (011 data-model §3); read only here.
INSTALL_RECORD = "ultralight_install.json"
# `vendor/livetalking` next to `src/`: where `ailive_ext.prepare` must run so the fork finds its own files.
DEFAULT_FORK_DIR = Path(__file__).resolve().parents[3] / "vendor" / "livetalking"


class AvatarModeError(ValueError):
    """The configured avatar mode cannot start; the app refuses to boot instead of showing the wrong face.

    `code` names the failed check when callers must tell checks apart (e.g. `model_not_supported`, 011).
    """

    def __init__(self, message: str, code: str | None = None) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class PrepareError:
    code: str
    message: str
    clip_id: str | None = None
    frame: int | None = None

    def to_json(self) -> dict[str, Any]:
        return {"code": self.code, "clip_id": self.clip_id, "frame": self.frame, "message": self.message}

    def describe(self) -> str:
        where = f" {self.clip_id}" if self.clip_id else ""
        frame = f" (khung {self.frame})" if self.frame is not None else ""
        return f"[{self.code}]{where}: {self.message}{frame}"


class CharacterError(AvatarModeError):
    """Every problem found in the folder at once, so the operator fixes it in one pass."""

    def __init__(self, errors: list[PrepareError]) -> None:
        super().__init__("Hồ sơ nhân vật không hợp lệ:\n" + "\n".join(e.describe() for e in errors))
        self.errors = errors


@dataclass(frozen=True)
class BaseClip:
    clip_id: str
    file: Path
    kind: ClipKind


@dataclass
class PrepareResult:
    status: PrepareStatus
    prepared_at: str | None = None
    fork_commit: str | None = None
    frame_size: list[int] | None = None
    clips: dict[str, Any] = field(default_factory=dict)
    errors: list[PrepareError] = field(default_factory=list)

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> PrepareResult:
        return cls(
            status=data.get("status", "failed"),
            prepared_at=data.get("prepared_at"),
            fork_commit=data.get("fork_commit"),
            frame_size=data.get("frame_size"),
            clips=dict(data.get("clips") or {}),
            errors=[_prepare_error(e) for e in data.get("errors") or []],
        )

    def to_json(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "prepared_at": self.prepared_at,
            "fork_commit": self.fork_commit,
            "frame_size": self.frame_size,
            "clips": self.clips,
            "errors": [e.to_json() for e in self.errors],
        }


@dataclass
class AvatarCharacter:
    avatar_dir: Path
    character_id: str
    customer_id: str
    face: Path
    provenance: Path
    clips: list[BaseClip]
    prepare: PrepareResult | None = None
    warnings: list[str] = field(default_factory=list)
    lipsync_models: list[LipsyncModel] = field(default_factory=lambda: ["wav2lip"])
    # True: the desk is part of the character image, so the scene draws no desk layer (011 FR-011).
    desk_in_image: bool = False
    desk_top: float | None = None
    # 013: where the hands move, as frame fractions (x1, y1, x2, y2); the realistic layout keeps products out of it.
    hands_zone: HandsZone | None = None

    def clips_of(self, kind: ClipKind) -> list[BaseClip]:
        return [c for c in self.clips if c.kind == kind]


def _prepare_error(data: Any) -> PrepareError:
    if not isinstance(data, dict):
        return PrepareError("fork_failed", str(data))
    frame = data.get("frame")
    return PrepareError(
        code=str(data.get("code") or "fork_failed"),
        message=str(data.get("message") or ""),
        clip_id=data.get("clip_id"),
        frame=frame if isinstance(frame, int) else None,
    )


def _inside(avatar_dir: Path, rel: Any) -> Path | None:
    """Resolve a relative path that must stay inside the folder; None for absolute paths or `..`."""
    if not isinstance(rel, str) or not rel:
        return None
    path = Path(rel)
    if path.is_absolute() or ".." in path.parts:
        return None
    return avatar_dir / path


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def load_character(avatar_dir: Path) -> AvatarCharacter:
    """Read `character.json` and `provenance.json`; raise `CharacterError` listing every problem found."""
    avatar_dir = Path(avatar_dir)
    meta_path = avatar_dir / "character.json"
    if not meta_path.is_file():
        raise CharacterError([PrepareError("missing_file", f"Không thấy {meta_path}")])
    try:
        data = _read_json(meta_path)
    except (OSError, ValueError) as exc:
        raise CharacterError([PrepareError("bad_character", f"character.json không đọc được: {exc}")]) from exc
    if not isinstance(data, dict):
        raise CharacterError([PrepareError("bad_character", "character.json phải là một object JSON")])

    errors: list[PrepareError] = []
    warnings: list[str] = []

    if data.get("schema_version") != SCHEMA_VERSION:
        errors.append(PrepareError("bad_character", f"schema_version phải là {SCHEMA_VERSION}"))

    character_id = data.get("character_id")
    if not isinstance(character_id, str) or not _ID_RE.match(character_id):
        errors.append(PrepareError("bad_character", "character_id phải gồm a-z, 0-9, _ hoặc -, tối đa 64 ký tự"))
        character_id = ""
    elif character_id != avatar_dir.name:
        errors.append(
            PrepareError("bad_character", f"character_id '{character_id}' khác tên thư mục '{avatar_dir.name}'")
        )

    customer_id = data.get("customer_id")
    if not isinstance(customer_id, str) or not customer_id.strip():
        errors.append(PrepareError("missing_customer", "Thiếu customer_id: mỗi nhân vật thuộc đúng một khách"))
        customer_id = ""

    face = _inside(avatar_dir, data.get("face"))
    if face is None or face.suffix.lower() not in _FACE_SUFFIXES:
        errors.append(PrepareError("bad_character", "face phải là đường dẫn tương đối tới ảnh PNG/JPG trong thư mục"))
        face = avatar_dir / "face.png"
    elif not face.is_file():
        errors.append(PrepareError("missing_file", f"Không thấy ảnh mặt {face.name}"))

    lipsync_models = _load_lipsync_models(data.get("lipsync_models", ["wav2lip"]), errors)
    # Clips are the Wav2Lip library; a character with only its own model has none (011 data-model §2).
    clips = _load_clips(avatar_dir, data.get("clips"), errors, warnings, require_kinds="wav2lip" in lipsync_models)
    desk_in_image, desk_top, hands_zone = _load_scene(data.get("scene", {}), errors)

    provenance = _inside(avatar_dir, data.get("provenance"))
    if provenance is None or not provenance.is_file():
        errors.append(
            PrepareError("missing_provenance", "Thiếu hồ sơ nguồn gốc (provenance.json): không dùng nhân vật này")
        )
        provenance = avatar_dir / "provenance.json"
    else:
        _check_provenance(provenance, character_id, clips, errors)

    prepare = None
    if isinstance(data.get("prepare"), dict):
        prepare = PrepareResult.from_json(data["prepare"])

    if errors:
        raise CharacterError(errors)
    return AvatarCharacter(
        avatar_dir=avatar_dir,
        character_id=character_id,
        customer_id=customer_id,
        face=face,
        provenance=provenance,
        clips=clips,
        prepare=prepare,
        warnings=warnings,
        lipsync_models=lipsync_models,
        desk_in_image=desk_in_image,
        desk_top=desk_top,
        hands_zone=hands_zone,
    )


def _load_lipsync_models(raw: Any, errors: list[PrepareError]) -> list[LipsyncModel]:
    if (
        not isinstance(raw, list)
        or not raw
        or not all(isinstance(m, str) and m in _LIPSYNC_MODELS for m in raw)
        or len(set(raw)) != len(raw)
    ):
        errors.append(
            PrepareError(
                "bad_character", "lipsync_models phải là danh sách không rỗng, không lặp, gồm wav2lip/ultralight"
            )
        )
        return ["wav2lip"]
    return list(raw)


def _load_scene(raw: Any, errors: list[PrepareError]) -> tuple[bool, float | None, HandsZone | None]:
    if not isinstance(raw, dict):
        errors.append(PrepareError("bad_character", "scene phải là một object"))
        return False, None, None
    return (*_load_desk(raw, errors), _load_hands_zone(raw.get("hands_zone"), errors))


def _load_hands_zone(raw: Any, errors: list[PrepareError]) -> HandsZone | None:
    if raw is None:
        return None
    if (
        not isinstance(raw, list)
        or len(raw) != 4
        or not all(isinstance(v, int | float) and not isinstance(v, bool) and 0 <= v <= 1 for v in raw)
        or not (raw[0] < raw[2] and raw[1] < raw[3])
    ):
        errors.append(
            PrepareError("bad_character", "scene.hands_zone phải là [x1, y1, x2, y2] trong [0; 1], x1 < x2 và y1 < y2")
        )
        return None
    x1, y1, x2, y2 = (float(v) for v in raw)
    return x1, y1, x2, y2


def _load_desk(raw: dict[str, Any], errors: list[PrepareError]) -> tuple[bool, float | None]:
    desk_in_image = raw.get("desk_in_image", False)
    if not isinstance(desk_in_image, bool):
        errors.append(PrepareError("bad_character", "scene.desk_in_image phải là true hoặc false"))
        return False, None
    desk_top = raw.get("desk_top")
    low, high = DESK_TOP_RANGE
    if desk_top is None:
        if desk_in_image:
            errors.append(
                PrepareError("bad_character", "scene.desk_top bắt buộc khi bàn nằm trong ảnh (desk_in_image)")
            )
        return desk_in_image, None
    if isinstance(desk_top, bool) or not isinstance(desk_top, int | float) or not low <= desk_top <= high:
        errors.append(PrepareError("bad_character", f"scene.desk_top phải là số trong [{low}; {high}]"))
        return desk_in_image, None
    return desk_in_image, float(desk_top)


def _load_clips(
    avatar_dir: Path, raw: Any, errors: list[PrepareError], warnings: list[str], *, require_kinds: bool = True
) -> list[BaseClip]:
    clips: list[BaseClip] = []
    seen: set[str] = set()
    if not isinstance(raw, list):
        errors.append(PrepareError("bad_character", "clips phải là một danh sách"))
        raw = []
    for entry in raw:
        if not isinstance(entry, dict):
            errors.append(PrepareError("bad_character", "Mỗi clip phải là một object"))
            continue
        clip_id, kind = entry.get("clip_id"), entry.get("kind")
        if not isinstance(clip_id, str) or not _ID_RE.match(clip_id):
            errors.append(PrepareError("bad_character", f"clip_id '{clip_id}' không hợp lệ"))
            continue
        if clip_id in seen:
            errors.append(PrepareError("bad_character", f"clip_id '{clip_id}' bị trùng", clip_id=clip_id))
            continue
        seen.add(clip_id)
        if kind not in _CLIP_KINDS:
            errors.append(
                PrepareError("bad_character", f"kind phải là idle hoặc talk, đang là '{kind}'", clip_id=clip_id)
            )
            continue
        path = _inside(avatar_dir, entry.get("file"))
        if path is None or path.suffix.lower() != ".mp4":
            errors.append(
                PrepareError("bad_character", "file phải là .mp4 nằm trong thư mục nhân vật", clip_id=clip_id)
            )
            continue
        if not path.is_file():
            errors.append(PrepareError("missing_file", f"Không thấy {entry['file']}", clip_id=clip_id))
        if path.stem.endswith("_pingpong"):
            # R7: the fork plays clips back and forth itself; a pre-made ping-pong copy only doubles memory.
            warnings.append(f"{clip_id}: dùng bản _pingpong làm tốn gấp đôi bộ nhớ, nên dùng clip gốc")
        clips.append(BaseClip(clip_id=clip_id, file=path, kind=kind))
    for kind in _CLIP_KINDS if require_kinds else ():
        if not any(c.kind == kind for c in clips):
            errors.append(PrepareError("kind_missing", f"Cần ít nhất một clip loại {kind}"))
    return clips


def _check_provenance(path: Path, character_id: str, clips: list[BaseClip], errors: list[PrepareError]) -> None:
    def incomplete(message: str, clip_id: str | None = None) -> None:
        errors.append(PrepareError("provenance_incomplete", message, clip_id=clip_id))

    try:
        prov = _read_json(path)
    except (OSError, ValueError) as exc:
        incomplete(f"provenance.json không đọc được: {exc}")
        return
    if not isinstance(prov, dict):
        incomplete("provenance.json phải là một object JSON")
        return
    for name in _PROVENANCE_TEXT_FIELDS:
        value = prov.get(name)
        if not isinstance(value, str) or not value.strip():
            incomplete(f"Thiếu trường {name}")
    if character_id and prov.get("character_id") not in (None, character_id):
        incomplete("character_id trong provenance.json khác character.json")
    if prov.get("kind") != PROVENANCE_KIND:
        incomplete(f"kind phải là {PROVENANCE_KIND}: chưa nhận khuôn mặt người thật")

    # data-model §3 describes a list; the real `demo_host_01` file keys models by role and names each by its
    # Hugging Face `repo`. Accept both.
    models = prov.get("models")
    entries = list(models.values()) if isinstance(models, dict) else models
    if not isinstance(entries, list) or not entries:
        incomplete("Thiếu trường models")
    elif not all(isinstance(m, dict) and (m.get("name") or m.get("repo")) and m.get("license") for m in entries):
        incomplete("Mỗi model phải có name (hoặc repo) và license")

    records = prov.get("clips", prov.get("assets"))
    records = records if isinstance(records, list) else []
    for clip in clips:
        if not any(_record_matches(r, clip) for r in records):
            incomplete("Thiếu mục nguồn gốc cho clip này", clip_id=clip.clip_id)

    if prov.get("adult_fictional_confirmed") is not True:
        incomplete("adult_fictional_confirmed phải là true (người tạo xác nhận mặt người lớn, hư cấu)")


def _record_matches(record: Any, clip: BaseClip) -> bool:
    if not isinstance(record, dict):
        return False
    if clip.clip_id in (record.get("clip_id"), record.get("name")):
        return True
    files = record.get("files") or [record.get("file")]
    return any(isinstance(f, str) and Path(f).name == clip.file.name for f in files)


@dataclass(frozen=True)
class UltralightInstall:
    """What the app knows of an installed Ultralight model: the record's claims and the hash of the file itself."""

    character_id: str | None
    teacher: str | None
    sha256: str  # of the model file on disk now
    recorded_sha256: str | None  # what `install` wrote; differs from `sha256` when the file changed since
    fork_commit: str | None
    record: dict[str, Any]


def ultralight_dir(avatar_dir: Path, teacher: str) -> Path:
    return avatar_dir / "ultralight" / teacher


def _file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def read_ultralight_install(avatar_dir: Path, teacher: str) -> tuple[UltralightInstall | None, str | None]:
    """Read `<AVATAR_DIR>/ultralight/<teacher>/ultralight_install.json` and hash the model it names.

    Returns (install, None), or (None, a Vietnamese reason). Hashing reads ~49 MB, so async callers run this through
    `asyncio.to_thread`. Comparing against the character and the config is the caller's job.
    """
    folder = ultralight_dir(avatar_dir, teacher)
    path = folder / INSTALL_RECORD
    if not path.is_file():
        return None, f"thiếu {INSTALL_RECORD} của thầy {teacher} trong {folder}"
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
        checkpoint = record.get("checkpoint") or {}
        name, recorded = checkpoint.get("file"), checkpoint.get("sha256")
    except (OSError, ValueError, AttributeError) as exc:
        return None, f"{INSTALL_RECORD} của thầy {teacher} hỏng ({exc.__class__.__name__})"
    if not isinstance(name, str) or not name or Path(name).name != name:
        return None, f"{INSTALL_RECORD} của thầy {teacher} không ghi tên file model"
    model = folder / name
    if not model.is_file():
        return None, f"thiếu file model {name} của thầy {teacher} trong {folder}"
    return (
        UltralightInstall(
            character_id=record.get("character_id"),
            teacher=record.get("teacher"),
            sha256=_file_sha256(model),
            recorded_sha256=recorded if isinstance(recorded, str) else None,
            fork_commit=record.get("fork_commit"),
            record=record,
        ),
        None,
    )


def ultralight_first_frame(avatar_dir: Path, teacher: str, fork_dir: Path = DEFAULT_FORK_DIR) -> Path | None:
    """First frame of the fork avatar the install record names for Ultralight, or None when any piece is missing.

    The training clip rarely starts from `face.png` (another pose, another room), so this is the picture that matches
    what viewers see. Reads one small JSON and lists one folder; it does not hash the model.
    """
    try:
        record = json.loads((ultralight_dir(avatar_dir, teacher) / INSTALL_RECORD).read_text(encoding="utf-8"))
        name = (record.get("avatars") or {}).get("ultralight")
    except (OSError, ValueError, AttributeError):
        return None
    # A bare folder name only: the record must not point the app at files outside the fork's avatars.
    if not isinstance(name, str) or not name or Path(name).name != name or name in {".", ".."}:
        return None
    full = fork_dir / "data" / "avatars" / name / "full_imgs"
    try:
        frames = sorted(p for p in full.iterdir() if p.suffix.lower() in {".png", ".jpg", ".jpeg"} and p.is_file())
    except OSError:
        return None
    return frames[0] if frames else None


def validate_for_session(character: AvatarCharacter, settings: Settings) -> None:
    """Refuse a `livetalking` session with someone else's character, a model it lacks, or unprepared clips.

    005 FR-004, constitution II; 011 FR-008: `prepare` covers only the Wav2Lip clip library.
    """
    if settings.customer_id != character.customer_id:
        raise AvatarModeError(
            f"Nhân vật {character.character_id} thuộc khách '{character.customer_id}', "
            f"không phải khách đang cấu hình CUSTOMER_ID='{settings.customer_id}'"
        )
    if settings.avatar_id != character.character_id:
        raise AvatarModeError(
            f"AVATAR_ID='{settings.avatar_id}' khác character_id '{character.character_id}' của thư mục"
        )
    model = settings.livetalking_model
    if model not in character.lipsync_models:
        raise AvatarModeError(
            f"Nhân vật {character.character_id} không có model {model} "
            f"(lipsync_models: {', '.join(character.lipsync_models)}); đổi LIVETALKING_MODEL hoặc AVATAR_DIR",
            code="model_not_supported",
        )
    if model != "wav2lip":
        return
    if character.prepare is None or character.prepare.status != "ready":
        status = character.prepare.status if character.prepare else "chưa chạy"
        command = f"uv run python -m ai_live.avatar prepare {character.avatar_dir}"
        raise AvatarModeError(f"Nhân vật chưa prepare xong ({status}). Chạy: {command}")


def _write_character(avatar_dir: Path, prepare: dict[str, Any]) -> None:
    """Rewrite only the `prepare` part, atomically, so an interrupted run never leaves half a file."""
    meta_path = avatar_dir / "character.json"
    data = _read_json(meta_path)
    data["prepare"] = prepare
    tmp = meta_path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, meta_path)


async def _subprocess_run(args: list[str], cwd: Path) -> tuple[int, str, str]:
    # A missing fork folder raises OSError here, which prepare reports as "cannot run".
    proc = await asyncio.create_subprocess_exec(
        *args,
        cwd=cwd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    out, err = await proc.communicate()
    return proc.returncode or 0, out.decode("utf-8", "replace"), err.decode("utf-8", "replace")


def _now() -> str:
    return datetime.now(UTC).astimezone().isoformat(timespec="seconds")


async def prepare_character(
    avatar_dir: Path,
    fork_python: Path,
    *,
    run: ForkRun | None = None,
    fork_dir: Path | None = None,
) -> PrepareResult:
    """Check the folder, then let the fork decode every clip and cache face crops (contracts/adapters.md §7).

    An invalid folder raises `CharacterError` before the fork runs; fork-side problems come back as a `failed` result.
    """
    # File work runs in a thread so a caller with a live event loop is not blocked.
    avatar_dir, character, args, cwd = await asyncio.to_thread(_begin_prepare, avatar_dir, fork_python, fork_dir)
    previous_commit = character.prepare.fork_commit if character.prepare else None
    try:
        returncode, stdout, stderr = await (run or _subprocess_run)(args, cwd)
    except OSError as exc:
        returncode, stdout, stderr = -1, "", f"Không chạy được {args[0]}: {exc}"

    result = _parse_fork_output(returncode, stdout, stderr)
    result.prepared_at = _now()
    _write_character(avatar_dir, result.to_json())
    if previous_commit and result.fork_commit and previous_commit != result.fork_commit:
        log_event(
            logger,
            "avatar_prepared_with_other_fork",
            logging.WARNING,
            prepared_commit=previous_commit,
            running_commit=result.fork_commit,
        )
    log_event(logger, "avatar_prepare_done", status=result.status, errors=[e.code for e in result.errors])
    return result


def _begin_prepare(
    avatar_dir: Path, fork_python: Path, fork_dir: Path | None
) -> tuple[Path, AvatarCharacter, list[str], Path]:
    avatar_dir = Path(avatar_dir).resolve()
    character = load_character(avatar_dir)
    _write_character(avatar_dir, {"status": "preparing", "prepared_at": _now(), "errors": []})
    args = [str(Path(fork_python).resolve()), "-m", "ailive_ext.prepare", str(avatar_dir), "--json"]
    return avatar_dir, character, args, fork_dir or DEFAULT_FORK_DIR


def _parse_fork_output(returncode: int, stdout: str, stderr: str) -> PrepareResult:
    # rc 0 = ready, 1 = the fork found problems in the clips (listed in JSON), anything else = the script itself broke.
    data: Any = None
    if returncode in (0, 1) and stdout.strip():
        try:
            data = json.loads(stdout)
        except ValueError:
            data = None
    if not isinstance(data, dict) or data.get("status") not in ("ready", "failed"):
        detail = (stderr or stdout).strip().splitlines()[-1:] or [f"mã thoát {returncode}"]
        return PrepareResult(
            status="failed", errors=[PrepareError("fork_failed", f"Script prepare của fork lỗi: {detail[0]}")]
        )
    result = PrepareResult.from_json(data)
    if result.status == "ready" and result.errors:
        result.status = "failed"
    return result

"""Character folder: load, session checks and `prepare` (005 T022, T023; data-model §2–§3, contracts/adapters.md §7)."""

from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path

import pytest

from ai_live.avatar.character import (
    AvatarModeError,
    CharacterError,
    load_character,
    prepare_character,
    read_ultralight_install,
    validate_for_session,
)
from ai_live.core.config import Settings
from fixtures.character_builder import (
    CHARACTER_ID,
    CUSTOMER_ID,
    DEFAULT_CLIPS,
    READY_PREPARE,
    default_provenance,
    make_character_dir,
    read_character,
)

pytestmark = pytest.mark.anyio


@pytest.fixture
def session_settings(settings: Settings) -> Settings:
    return settings.model_copy(update={"customer_id": CUSTOMER_ID, "avatar_id": CHARACTER_ID})


def _codes(exc: CharacterError) -> list[str]:
    return [e.code for e in exc.errors]


def _load_error(avatar_dir: Path) -> CharacterError:
    with pytest.raises(CharacterError) as info:
        load_character(avatar_dir)
    return info.value


# ---------- T022: load_character / validate_for_session ----------


def test_load_valid_character(tmp_path: Path) -> None:
    avatar_dir = make_character_dir(tmp_path, prepare=READY_PREPARE)
    character = load_character(avatar_dir)
    assert character.character_id == CHARACTER_ID
    assert character.customer_id == CUSTOMER_ID
    assert character.face == avatar_dir / "face.png"
    assert [c.clip_id for c in character.clips_of("idle")] == ["idle_01", "idle_02"]
    assert [c.clip_id for c in character.clips_of("talk")] == ["talk_01", "talk_02"]
    assert character.prepare is not None and character.prepare.status == "ready"
    assert character.prepare.fork_commit == "fakecommit0"
    assert character.warnings == []


def test_accepts_many_clips_per_kind(tmp_path: Path) -> None:
    clips = [*DEFAULT_CLIPS, {"clip_id": "talk_03", "file": "clips/talk_03.mp4", "kind": "talk"}]
    avatar_dir = make_character_dir(tmp_path, character={"clips": clips})
    assert len(load_character(avatar_dir).clips_of("talk")) == 3


def test_session_accepts_matching_ready_character(tmp_path: Path, session_settings: Settings) -> None:
    character = load_character(make_character_dir(tmp_path, prepare=READY_PREPARE))
    validate_for_session(character, session_settings)


def test_session_rejects_other_customer(tmp_path: Path, session_settings: Settings) -> None:
    """FR-004: a character belongs to exactly one customer."""
    character = load_character(make_character_dir(tmp_path, prepare=READY_PREPARE))
    with pytest.raises(AvatarModeError, match="khách"):
        validate_for_session(character, session_settings.model_copy(update={"customer_id": "khach_khac"}))


def test_session_rejects_other_avatar_id(tmp_path: Path, session_settings: Settings) -> None:
    character = load_character(make_character_dir(tmp_path, prepare=READY_PREPARE))
    with pytest.raises(AvatarModeError, match="AVATAR_ID"):
        validate_for_session(character, session_settings.model_copy(update={"avatar_id": "other_host"}))


@pytest.mark.parametrize(
    "prepare",
    [None, {**READY_PREPARE, "status": "failed"}, {**READY_PREPARE, "status": "preparing"}],
    ids=["never_prepared", "failed", "preparing"],
)
def test_session_rejects_unprepared_character(tmp_path: Path, session_settings: Settings, prepare: dict | None) -> None:
    character = load_character(make_character_dir(tmp_path, prepare=prepare))
    with pytest.raises(AvatarModeError, match="prepare"):
        validate_for_session(character, session_settings)


def test_character_error_is_avatar_mode_error() -> None:
    """The app catches one error type to refuse startup, whatever the reason."""
    assert issubclass(CharacterError, AvatarModeError)


def test_missing_character_json(tmp_path: Path) -> None:
    error = _load_error(tmp_path)
    assert _codes(error) == ["missing_file"]


def test_missing_customer(tmp_path: Path) -> None:
    error = _load_error(make_character_dir(tmp_path, character={"customer_id": None}))
    assert "missing_customer" in _codes(error)


def test_missing_provenance(tmp_path: Path) -> None:
    """US1 #6: no provenance record, no character."""
    error = _load_error(make_character_dir(tmp_path, write_provenance=False))
    assert "missing_provenance" in _codes(error)


@pytest.mark.parametrize("field", ["created_by", "created_at", "platform", "models", "character_id"])
def test_provenance_missing_field(tmp_path: Path, field: str) -> None:
    prov = default_provenance()
    del prov[field]
    error = _load_error(make_character_dir(tmp_path, provenance=prov))
    assert "provenance_incomplete" in _codes(error)


def test_provenance_rejects_other_kind(tmp_path: Path) -> None:
    error = _load_error(make_character_dir(tmp_path, provenance={**default_provenance(), "kind": "real_person"}))
    assert "provenance_incomplete" in _codes(error)


def test_provenance_model_without_license(tmp_path: Path) -> None:
    prov = default_provenance()
    prov["models"]["video"] = {"repo": "org/video-model"}
    error = _load_error(make_character_dir(tmp_path, provenance=prov))
    assert "provenance_incomplete" in _codes(error)


def test_provenance_model_without_name_or_repo(tmp_path: Path) -> None:
    prov = default_provenance()
    prov["models"]["video"] = {"file": "video.safetensors", "license": "apache-2.0"}
    error = _load_error(make_character_dir(tmp_path, provenance=prov))
    assert "provenance_incomplete" in _codes(error)


def test_provenance_accepts_model_list(tmp_path: Path) -> None:
    """data-model §3 describes `models[]` as a list; the real file uses a dict. Both are accepted."""
    prov = {**default_provenance(), "models": [{"name": "face-model", "license": "apache-2.0"}]}
    load_character(make_character_dir(tmp_path, provenance=prov))


def test_provenance_missing_clip_entry(tmp_path: Path) -> None:
    prov = default_provenance()
    prov["clips"] = [c for c in prov["clips"] if c["name"] != "talk_02"]
    error = _load_error(make_character_dir(tmp_path, provenance=prov))
    [incomplete] = [e for e in error.errors if e.code == "provenance_incomplete"]
    assert incomplete.clip_id == "talk_02"


@pytest.mark.parametrize("value", [False, None, "true"], ids=["false", "missing", "string"])
def test_provenance_requires_adult_confirmation(tmp_path: Path, value: object) -> None:
    """FR-005: the creator must confirm the face looks adult and fictional."""
    prov = default_provenance()
    if value is None:
        del prov["adult_fictional_confirmed"]
    else:
        prov["adult_fictional_confirmed"] = value
    error = _load_error(make_character_dir(tmp_path, provenance=prov))
    assert "provenance_incomplete" in _codes(error)
    assert any("adult_fictional_confirmed" in e.message for e in error.errors)


@pytest.mark.parametrize("missing_kind", ["idle", "talk"])
def test_kind_missing(tmp_path: Path, missing_kind: str) -> None:
    """FR-002, FR-012: at least one idle clip and one talk clip."""
    clips = [c for c in DEFAULT_CLIPS if c["kind"] != missing_kind]
    error = _load_error(make_character_dir(tmp_path, character={"clips": clips}))
    assert "kind_missing" in _codes(error)


def test_clip_file_missing(tmp_path: Path) -> None:
    error = _load_error(make_character_dir(tmp_path, skip_files=("clips/talk_01.mp4",)))
    [missing] = [e for e in error.errors if e.code == "missing_file"]
    assert missing.clip_id == "talk_01"


def test_face_file_missing(tmp_path: Path) -> None:
    error = _load_error(make_character_dir(tmp_path, skip_files=("face.png",)))
    assert "missing_file" in _codes(error)


@pytest.mark.parametrize(
    "clip",
    [
        {"clip_id": "talk_09", "file": "../outside.mp4", "kind": "talk"},
        {"clip_id": "talk_09", "file": "clips/talk_09.mov", "kind": "talk"},
        {"clip_id": "talk_09", "file": "clips/talk_09.mp4", "kind": "dance"},
        {"clip_id": "Talk 09", "file": "clips/talk_09.mp4", "kind": "talk"},
        {"clip_id": "talk_01", "file": "clips/talk_01b.mp4", "kind": "talk"},
    ],
    ids=["path_escape", "not_mp4", "bad_kind", "bad_id", "duplicate_id"],
)
def test_bad_clip_entry(tmp_path: Path, clip: dict[str, str]) -> None:
    error = _load_error(make_character_dir(tmp_path, character={"clips": [*DEFAULT_CLIPS, clip]}))
    assert "bad_character" in _codes(error)


def test_bad_schema_version(tmp_path: Path) -> None:
    error = _load_error(make_character_dir(tmp_path, character={"schema_version": 2}))
    assert "bad_character" in _codes(error)


def test_pingpong_clip_is_only_a_warning(tmp_path: Path) -> None:
    """R7: the `_pingpong` copy doubles memory; warn, do not block."""
    clips = [*DEFAULT_CLIPS[:3], {"clip_id": "talk_02", "file": "clips/talk_02_pingpong.mp4", "kind": "talk"}]
    character = load_character(make_character_dir(tmp_path, character={"clips": clips}))
    assert any("_pingpong" in w for w in character.warnings)


def test_reports_every_error_at_once(tmp_path: Path) -> None:
    """The operator fixes the folder in one pass instead of one error per run."""
    clips = [c for c in DEFAULT_CLIPS if c["kind"] != "talk"]
    error = _load_error(
        make_character_dir(tmp_path, character={"clips": clips, "customer_id": None}, write_provenance=False)
    )
    assert {"kind_missing", "missing_customer", "missing_provenance"} <= set(_codes(error))


# ---------- T023: prepare_character ----------


class FakeForkRun:
    """Stands in for `LIVETALKING_PYTHON -m ailive_ext.prepare`: records the call and what `character.json` held."""

    def __init__(self, returncode: int = 0, stdout: str | dict = "", stderr: str = "") -> None:
        self.returncode = returncode
        self.stdout = json.dumps(stdout) if isinstance(stdout, dict) else stdout
        self.stderr = stderr
        self.calls: list[tuple[list[str], Path]] = []
        self.status_during_run: str | None = None

    async def __call__(self, args: list[str], cwd: Path) -> tuple[int, str, str]:
        self.calls.append((args, cwd))
        avatar_dir = Path(args[3])
        self.status_during_run = read_character(avatar_dir).get("prepare", {}).get("status")
        return self.returncode, self.stdout, self.stderr


def _fork_ready(commit: str = "abc1234") -> dict:
    return {
        "status": "ready",
        "fork_commit": commit,
        "frame_size": [480, 832],
        "clips": {
            c["clip_id"]: {"frames": 121, "fps": 24.0, "avatar_dir": f"data/avatars/{CHARACTER_ID}__{c['clip_id']}"}
            for c in DEFAULT_CLIPS
        },
        "errors": [],
    }


async def test_prepare_ready_writes_result(tmp_path: Path) -> None:
    avatar_dir = make_character_dir(tmp_path)
    run = FakeForkRun(0, _fork_ready())
    fork_python = tmp_path / "py" / "python.exe"
    fork_dir = tmp_path / "fork"

    result = await prepare_character(avatar_dir, fork_python, run=run, fork_dir=fork_dir)

    assert result.status == "ready"
    [(args, cwd)] = run.calls
    assert args == [str(fork_python.resolve()), "-m", "ailive_ext.prepare", str(avatar_dir.resolve()), "--json"]
    assert cwd == fork_dir
    saved = read_character(avatar_dir)
    assert saved["prepare"]["status"] == "ready"
    assert saved["prepare"]["fork_commit"] == "abc1234"
    assert saved["prepare"]["frame_size"] == [480, 832]
    assert saved["prepare"]["clips"]["talk_01"]["frames"] == 121
    assert saved["prepare"]["errors"] == []
    assert saved["prepare"]["prepared_at"]
    # The hand-written part is kept as is.
    assert saved["customer_id"] == CUSTOMER_ID
    assert [c["clip_id"] for c in saved["clips"]] == [c["clip_id"] for c in DEFAULT_CLIPS]


async def test_prepare_marks_preparing_while_running(tmp_path: Path) -> None:
    avatar_dir = make_character_dir(tmp_path, prepare=READY_PREPARE)
    run = FakeForkRun(0, _fork_ready())
    await prepare_character(avatar_dir, tmp_path / "python.exe", run=run, fork_dir=tmp_path)
    assert run.status_during_run == "preparing"


async def test_prepare_face_count_names_clip_and_frame(tmp_path: Path) -> None:
    """US1 #5, FR-003: a frame without exactly one face fails the clip, naming the clip and the frame."""
    avatar_dir = make_character_dir(tmp_path)
    out = {
        **_fork_ready(),
        "status": "failed",
        "errors": [{"code": "face_count", "clip_id": "talk_01", "frame": 84, "message": "Khung 84 có 2 khuôn mặt"}],
    }
    result = await prepare_character(avatar_dir, tmp_path / "python.exe", run=FakeForkRun(1, out), fork_dir=tmp_path)

    assert result.status == "failed"
    [error] = result.errors
    assert (error.code, error.clip_id, error.frame) == ("face_count", "talk_01", 84)
    saved = read_character(avatar_dir)["prepare"]
    assert saved["status"] == "failed"
    assert saved["errors"][0] == {
        "code": "face_count",
        "clip_id": "talk_01",
        "frame": 84,
        "message": "Khung 84 có 2 khuôn mặt",
    }


@pytest.mark.parametrize("code", ["size_mismatch", "bad_video"])
async def test_prepare_passes_fork_error_codes(tmp_path: Path, code: str) -> None:
    avatar_dir = make_character_dir(tmp_path)
    out = {
        **_fork_ready(),
        "status": "failed",
        "errors": [{"code": code, "clip_id": "idle_02", "frame": None, "message": "x"}],
    }
    result = await prepare_character(avatar_dir, tmp_path / "python.exe", run=FakeForkRun(1, out), fork_dir=tmp_path)
    assert result.status == "failed"
    assert [e.code for e in result.errors] == [code]


@pytest.mark.parametrize(
    ("returncode", "stdout"),
    [(2, "Traceback (most recent call last): ..."), (0, "not json"), (1, "")],
    ids=["exit_2", "bad_json", "empty"],
)
async def test_prepare_fork_failure(tmp_path: Path, returncode: int, stdout: str) -> None:
    avatar_dir = make_character_dir(tmp_path)
    run = FakeForkRun(returncode, stdout, stderr="CUDA error")
    result = await prepare_character(avatar_dir, tmp_path / "python.exe", run=run, fork_dir=tmp_path)
    assert result.status == "failed"
    assert [e.code for e in result.errors] == ["fork_failed"]
    assert read_character(avatar_dir)["prepare"]["status"] == "failed"


async def test_prepare_missing_fork_python(tmp_path: Path) -> None:
    """The default runner cannot start a missing venv: `fork_failed`, not a crash."""
    avatar_dir = make_character_dir(tmp_path)
    result = await prepare_character(avatar_dir, tmp_path / "no_such_python.exe", fork_dir=tmp_path)
    assert result.status == "failed"
    assert [e.code for e in result.errors] == ["fork_failed"]


async def test_prepare_refuses_invalid_character_without_calling_fork(tmp_path: Path) -> None:
    avatar_dir = make_character_dir(tmp_path, write_provenance=False)
    run = FakeForkRun(0, _fork_ready())
    with pytest.raises(CharacterError):
        await prepare_character(avatar_dir, tmp_path / "python.exe", run=run, fork_dir=tmp_path)
    assert run.calls == []
    assert "prepare" not in read_character(avatar_dir)


async def test_prepare_with_other_fork_commit_logs_warning(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    avatar_dir = make_character_dir(tmp_path, prepare=READY_PREPARE)
    caplog.set_level(logging.INFO)
    await prepare_character(
        avatar_dir, tmp_path / "python.exe", run=FakeForkRun(0, _fork_ready("newcommit9")), fork_dir=tmp_path
    )
    [record] = [r for r in caplog.records if r.getMessage() == "avatar_prepared_with_other_fork"]
    assert record.fields == {"prepared_commit": "fakecommit0", "running_commit": "newcommit9"}


# ---------- 011: lip-sync models and scene block (data-model §2, FR-002, FR-008, FR-011, FR-016, SC-008) ----------
_ULTRALIGHT_ONLY = {"clips": [], "lipsync_models": ["ultralight"]}


def test_missing_lipsync_models_defaults_to_wav2lip_and_loads_as_before(tmp_path: Path) -> None:
    character = load_character(make_character_dir(tmp_path, prepare=READY_PREPARE))
    assert character.lipsync_models == ["wav2lip"]
    assert character.desk_in_image is False
    assert character.desk_top is None
    assert [c.clip_id for c in character.clips] == [c["clip_id"] for c in DEFAULT_CLIPS]


@pytest.mark.parametrize(
    "value",
    [[], ["wav2lip", "wav2lip"], ["musetalk"], "ultralight", ["ultralight", 3]],
    ids=["empty", "duplicate", "unknown", "not_list", "not_str"],
)
def test_bad_lipsync_models_is_rejected(tmp_path: Path, value: object) -> None:
    with pytest.raises(CharacterError) as info:
        load_character(make_character_dir(tmp_path, character={"lipsync_models": value}))
    assert "bad_character" in _codes(info.value)


def test_ultralight_only_character_needs_no_clips_or_prepare(tmp_path: Path) -> None:
    character = load_character(make_character_dir(tmp_path, character=_ULTRALIGHT_ONLY))
    assert character.lipsync_models == ["ultralight"]
    assert character.clips == []
    assert character.prepare is None


def test_wav2lip_in_list_still_needs_both_clip_kinds(tmp_path: Path) -> None:
    clips = [c for c in DEFAULT_CLIPS if c["kind"] == "idle"]
    avatar_dir = make_character_dir(tmp_path, character={"clips": clips, "lipsync_models": ["ultralight", "wav2lip"]})
    with pytest.raises(CharacterError) as info:
        load_character(avatar_dir)
    assert _codes(info.value) == ["kind_missing"]


def test_desk_in_image_with_desk_top_loads(tmp_path: Path) -> None:
    scene = {"desk_in_image": True, "desk_top": 0.71}
    character = load_character(make_character_dir(tmp_path, character={**_ULTRALIGHT_ONLY, "scene": scene}))
    assert character.desk_in_image is True
    assert character.desk_top == pytest.approx(0.71)


@pytest.mark.parametrize(
    "scene",
    [
        {"desk_in_image": True, "desk_top": None},
        {"desk_in_image": True},
        {"desk_in_image": True, "desk_top": 0.5},
        {"desk_in_image": True, "desk_top": 0.95},
        {"desk_in_image": True, "desk_top": "0.7"},
        {"desk_in_image": "yes"},
        "desk",
    ],
    ids=["null", "missing", "too_high_on_screen", "too_low_on_screen", "string", "flag_not_bool", "not_object"],
)
def test_bad_scene_block_is_rejected(tmp_path: Path, scene: object) -> None:
    with pytest.raises(CharacterError) as info:
        load_character(make_character_dir(tmp_path, character={**_ULTRALIGHT_ONLY, "scene": scene}))
    assert "bad_character" in _codes(info.value)


def test_session_rejects_model_the_character_lacks(tmp_path: Path, session_settings: Settings) -> None:
    character = load_character(make_character_dir(tmp_path, prepare=READY_PREPARE))
    with pytest.raises(AvatarModeError) as info:
        validate_for_session(character, session_settings.model_copy(update={"livetalking_model": "ultralight"}))
    assert info.value.code == "model_not_supported"
    assert "ultralight" in str(info.value)


def test_session_accepts_ultralight_character_without_prepare(tmp_path: Path, session_settings: Settings) -> None:
    character = load_character(make_character_dir(tmp_path, character=_ULTRALIGHT_ONLY))
    validate_for_session(character, session_settings.model_copy(update={"livetalking_model": "ultralight"}))
    with pytest.raises(AvatarModeError) as info:
        validate_for_session(character, session_settings)
    assert info.value.code == "model_not_supported"


def test_ultralight_character_belongs_to_one_customer(tmp_path: Path, session_settings: Settings) -> None:
    character = load_character(make_character_dir(tmp_path, character=_ULTRALIGHT_ONLY))
    other = session_settings.model_copy(update={"customer_id": "other_customer", "livetalking_model": "ultralight"})
    with pytest.raises(AvatarModeError, match="other_customer"):
        validate_for_session(character, other)


# ---------- 011 T013: Ultralight install record in <AVATAR_DIR>/ultralight/<teacher>/ ----------

_MODEL_BYTES = b"fake ultralight weights"


def _install(avatar_dir: Path, teacher: str = "musetalk", **overrides: object) -> Path:
    evidence = avatar_dir / "ultralight" / teacher
    evidence.mkdir(parents=True)
    (evidence / "best_trainloss.pth").write_bytes(_MODEL_BYTES)
    record = {
        "character_id": CHARACTER_ID,
        "teacher": teacher,
        "fork_commit": "fakecommit0",
        "checkpoint": {"file": "best_trainloss.pth", "sha256": hashlib.sha256(_MODEL_BYTES).hexdigest()},
        "frames": 250,
    }
    record.update(overrides)
    (evidence / "ultralight_install.json").write_text(json.dumps(record), encoding="utf-8")
    return evidence


def test_install_record_gives_character_teacher_and_model_hash(tmp_path: Path) -> None:
    avatar_dir = make_character_dir(tmp_path, character=_ULTRALIGHT_ONLY)
    _install(avatar_dir)
    install, reason = read_ultralight_install(avatar_dir, "musetalk")
    assert reason is None and install is not None
    sha = hashlib.sha256(_MODEL_BYTES).hexdigest()
    assert (install.character_id, install.teacher) == (CHARACTER_ID, "musetalk")
    # The hash of the file on disk, and the one the record holds: US3 compares them (checkpoint_mismatch).
    assert install.sha256 == sha and install.recorded_sha256 == sha
    assert install.fork_commit == "fakecommit0"


def test_install_hash_is_of_the_file_not_copied_from_the_record(tmp_path: Path) -> None:
    avatar_dir = make_character_dir(tmp_path, character=_ULTRALIGHT_ONLY)
    _install(avatar_dir, checkpoint={"file": "best_trainloss.pth", "sha256": "0" * 64})
    install, _ = read_ultralight_install(avatar_dir, "musetalk")
    assert install is not None and install.recorded_sha256 == "0" * 64 and install.sha256 != "0" * 64


@pytest.mark.parametrize("missing", ["record", "model", "folder"])
def test_missing_install_gives_none_and_a_reason(tmp_path: Path, missing: str) -> None:
    avatar_dir = make_character_dir(tmp_path, character=_ULTRALIGHT_ONLY)
    if missing != "folder":
        evidence = _install(avatar_dir)
        (evidence / ("ultralight_install.json" if missing == "record" else "best_trainloss.pth")).unlink()
    install, reason = read_ultralight_install(avatar_dir, "musetalk")
    assert install is None
    assert reason is not None and "musetalk" in reason


def test_install_of_another_teacher_is_not_read(tmp_path: Path) -> None:
    avatar_dir = make_character_dir(tmp_path, character=_ULTRALIGHT_ONLY)
    _install(avatar_dir, teacher="infinitetalk")
    install, reason = read_ultralight_install(avatar_dir, "musetalk")
    assert install is None and reason is not None


@pytest.mark.parametrize("raw", ["{not json", "[]", '{"checkpoint": "x"}'])
def test_broken_install_record_gives_a_reason(tmp_path: Path, raw: str) -> None:
    avatar_dir = make_character_dir(tmp_path, character=_ULTRALIGHT_ONLY)
    evidence = _install(avatar_dir)
    (evidence / "ultralight_install.json").write_text(raw, encoding="utf-8")
    install, reason = read_ultralight_install(avatar_dir, "musetalk")
    assert install is None and reason is not None

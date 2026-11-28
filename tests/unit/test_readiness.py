"""007 US1: the pre-demo checks, line by line against data-model §1 (no app, no network)."""

from __future__ import annotations

import json
import os
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from ai_live.core.models import HostStatus
from ai_live.ops import readiness as r
from ai_live.ops.readiness import CheckStatus, ForkHealth, ReadinessResult
from fixtures.scene_builder import catalog, product

OK, WARN, FAIL, UNKNOWN = CheckStatus.OK, CheckStatus.WARN, CheckStatus.FAIL, CheckStatus.UNKNOWN
FORK_UP = ForkHealth(reachable=True, sessions=("s1",), record_enabled=False)


def host(audio="running", muted=False, paused=False) -> HostStatus:
    return HostStatus(frames=10, audio=audio, video_muted=muted, video_paused=paused, visible=True, received_at=1.0)


def sheet(**over) -> dict:
    base = {
        "name": "backup_20261113-1000_shop",
        "video": "",
        "customer_id": "shop",
        "avatar_id": "host_a",
        "catalog_version": "v1",
        "seconds": 150.0,
        "ok": True,
        "problems": [],
    }
    return base | over


def demo_day_items() -> list[r.ReadinessItem]:
    """Runbook §6 values with every part up: the "Sẵn sàng" baseline the SC-001 cases break one at a time."""
    return [
        r.check_app_env("demo"),
        r.check_reply_engine("chain"),
        r.check_tts_provider("vieneu"),
        r.check_avatar_mode("livetalking"),
        r.check_recording("livetalking", FORK_UP),
        r.check_fork("livetalking", FORK_UP, active_mode="livetalking", lipsync_connected=True),
        r.check_character("shop", "host_a", "host_a"),
        r.check_lipsync_model("livetalking", "wav2lip", "musetalk", "host_a", ["wav2lip"], fork=FORK_UP),
        r.check_host(True, host(), "livetalking"),
        r.check_content(catalog(product("p1", primary=True))),
        r.check_scene(True, []),
        check_bg(bg_status(None, reviewed=True)),  # 014, defined below
        r.check_ai_label("AI"),
        r.check_backup_video(sheet(), None, customer_id="shop", avatar_id="host_a", catalog_version="v1"),
        r.check_llm_chain("chain", {"entries": [{"label": "A", "status": "ready"}]}),
        r.check_power("ac"),
        r.check_disk(50.0, 5, Path("data/sessions")),
    ]


def result_of(items) -> ReadinessResult:
    return r.build_result(items, "app", time.perf_counter())


# ---------- One line of the table per test ----------


@pytest.mark.parametrize(
    ("check", "value", "status"),
    [
        (r.check_app_env, "dev", FAIL),
        (r.check_app_env, "demo", OK),
        (r.check_app_env, "prod", OK),
        (r.check_reply_engine, "fake", FAIL),
        (r.check_reply_engine, "gemini", WARN),
        (r.check_reply_engine, "chain", OK),
        (r.check_tts_provider, "fake", FAIL),
        (r.check_tts_provider, "gemini", WARN),
        (r.check_tts_provider, "vieneu", OK),
        (r.check_avatar_mode, "static", WARN),
        (r.check_avatar_mode, "livetalking", OK),
        (r.check_ai_label, "", FAIL),
        (r.check_ai_label, "   ", FAIL),
        (r.check_ai_label, "AI", OK),
    ],
)
def test_config_checks(check, value, status):
    assert check(value).status is status


@pytest.mark.parametrize(
    ("mode", "fork", "status"),
    [
        ("static", None, OK),
        ("livetalking", None, UNKNOWN),
        ("livetalking", ForkHealth(reachable=False, error="ConnectError"), UNKNOWN),
        ("livetalking", ForkHealth(reachable=True, sessions=("s",), record_enabled=None), UNKNOWN),
        ("livetalking", ForkHealth(reachable=True, sessions=("s",), record_enabled=True), FAIL),
        ("livetalking", FORK_UP, OK),
    ],
)
def test_recording(mode, fork, status):
    assert r.check_recording(mode, fork).status is status


def test_static_mode_says_lipsync_is_not_used():
    assert "không dùng nhép miệng" in r.check_recording("static", None).message.lower()
    assert "không dùng nhép miệng" in r.check_fork("static", None).message.lower()


@pytest.mark.parametrize(
    ("fork", "kwargs", "status"),
    [
        (ForkHealth(reachable=False, error="ConnectError"), {}, FAIL),
        (FORK_UP, {"active_mode": "static", "lipsync_connected": True}, FAIL),
        (ForkHealth(reachable=True, sessions=(), record_enabled=False), {}, WARN),
        (FORK_UP, {"active_mode": "livetalking", "lipsync_connected": False}, WARN),
        (FORK_UP, {"active_mode": "livetalking", "lipsync_connected": True}, OK),
        (FORK_UP, {}, OK),  # offline: only the fork itself is known
    ],
)
def test_fork(fork, kwargs, status):
    assert r.check_fork("livetalking", fork, **kwargs).status is status


@pytest.mark.parametrize(
    ("customer", "avatar", "status"),
    [("", "host_a", FAIL), ("shop", " ", FAIL), ("", "", FAIL), ("shop", "host_a", OK)],
)
def test_character(customer, avatar, status):
    assert r.check_character(customer, avatar).status is status


@pytest.mark.parametrize(
    ("ready", "status_msg", "mode", "status"),
    [
        (None, None, None, FAIL),  # app down
        (False, None, "static", FAIL),
        (True, None, "static", WARN),
        (True, host(audio="suspended"), "static", FAIL),
        (True, host(audio=None), "static", FAIL),
        (True, host(), "static", OK),
        (True, host(muted=True), "livetalking", FAIL),
        (True, host(paused=True), "livetalking", FAIL),
        (True, host(audio="suspended"), "livetalking", OK),  # the WebRTC video carries the sound
        (True, host(), "livetalking", OK),
    ],
)
def test_host(ready, status_msg, mode, status):
    assert r.check_host(ready, status_msg, mode).status is status


def test_host_offline_says_app_is_down():
    assert r.check_host(None, None, None).message == r.APP_DOWN


# ---------- 006 T020: the `host` item follows OUTPUT_MODE (006 contracts/api.md §7) ----------


@pytest.mark.parametrize(
    ("ready", "role", "status_msg", "mode", "status", "message"),
    [
        (None, None, None, None, FAIL, r.APP_DOWN),
        (False, None, None, "static", FAIL, "Nguồn OBS chưa nối"),
        (True, "host", host(), "static", FAIL, "Đang phát ở trang host trên Chrome, chưa phải OBS"),
        (True, "obs", None, "static", WARN, "Nguồn OBS đã nối nhưng chưa gửi nhịp trạng thái"),
        (
            True,
            "obs",
            host(muted=True),
            "livetalking",
            FAIL,
            "Hình nhép miệng trong nguồn OBS đang tắt tiếng hoặc dừng",
        ),
        (
            True,
            "obs",
            host(paused=True),
            "livetalking",
            FAIL,
            "Hình nhép miệng trong nguồn OBS đang tắt tiếng hoặc dừng",
        ),
        (
            True,
            "obs",
            host(audio="suspended"),
            "static",
            FAIL,
            "Âm thanh trong nguồn OBS chưa chạy (trạng thái suspended)",
        ),
        (True, "obs", host(audio="suspended"), "livetalking", OK, "Nguồn OBS đã nối, âm thanh sẵn sàng"),
        (True, "obs", host(), "static", OK, "Nguồn OBS đã nối, âm thanh sẵn sàng"),
    ],
)
def test_host_obs_mode(ready, role, status_msg, mode, status, message):
    item = r.check_host(ready, status_msg, mode, output_mode="obs", role=role, app_port=8123)
    assert (item.status, item.message) == (status, message)
    if status is not OK:
        assert item.action


def test_host_obs_not_connected_names_the_source_url():
    item = r.check_host(False, None, "static", output_mode="obs", app_port=8123)
    assert "http://127.0.0.1:8123/obs" in item.action
    assert "Control audio via OBS" in item.action


@pytest.mark.parametrize("role", [None, "host", "obs"])
def test_host_meet_mode_keeps_007_wording(role):
    # `meet` (and the legacy `webrtc`, which settings turn into `meet`) ignores the role: any page that plays is fine.
    assert r.check_host(True, host(), "static", output_mode="meet", role=role) == r.check_host(True, host(), "static")
    assert r.check_host(False, None, "static", output_mode="meet", role=role).message.startswith(
        "Màn hình host chưa mở"
    )


def test_result_carries_output_mode_and_text_shows_it():
    result = r.build_result([r.check_app_env("demo")], "app", time.perf_counter(), output_mode="obs")
    assert result.to_json()["output_mode"] == "obs"
    assert ReadinessResult.from_json(result.to_json()).output_mode == "obs"
    assert "Đầu ra: OBS" in r.render_text(result)
    old = result.to_json()
    del old["output_mode"]
    assert ReadinessResult.from_json(old).output_mode is None


def test_content():
    full = catalog(product("p1", primary=True), product("p2"))
    assert r.check_content(full).status is OK
    assert "2 sản phẩm" in r.check_content(full).message
    assert r.check_content(None).status is FAIL
    assert r.check_content(catalog()).status is FAIL
    assert r.check_content(None, "thiếu bảng giá").status is FAIL
    assert "thiếu bảng giá" in r.check_content(None, "thiếu bảng giá").message
    assert r.check_content(full, changed_after_load=True).status is WARN


def test_content_file_changed_after_load(tmp_path):
    path = tmp_path / "demo.docx"
    path.write_bytes(b"x")
    settings = _settings(product_data_path=path)
    loaded_before = catalog(product("p1", primary=True))
    loaded_before = type(loaded_before)(
        "v1", "demo.docx", datetime.now(UTC) - timedelta(hours=1), loaded_before.products
    )
    assert r._file_changed_after_load(settings, loaded_before)
    loaded_after = type(loaded_before)(
        "v1", "demo.docx", datetime.now(UTC) + timedelta(hours=1), loaded_before.products
    )
    assert not r._file_changed_after_load(settings, loaded_after)
    # An upload from the control page has another name: nothing to compare with.
    uploaded = type(loaded_before)("v1", "khach.docx", loaded_before.loaded_at, loaded_before.products)
    assert not r._file_changed_after_load(settings, uploaded)


def test_scene():
    assert r.check_scene(False, [{"code": "placeholder", "level": "warning", "product_id": "p1"}]).status is OK
    assert r.check_scene(True, []).status is OK
    placeholder = r.check_scene(
        True,
        [
            {"code": "placeholder", "level": "warning", "product_id": "p2", "message": "ảnh mẫu"},
            {"code": "placeholder", "level": "warning", "product_id": "p1", "message": "ảnh mẫu"},
        ],
    )
    assert placeholder.status is FAIL
    assert "p1, p2" in placeholder.message
    broken = r.check_scene(
        True, [{"code": "missing_file", "level": "error", "product_id": "p1", "message": "thiếu ảnh"}]
    )
    assert broken.status is WARN
    assert (
        r.check_scene(True, [{"code": "small", "level": "warning", "product_id": "p1", "message": "nhỏ"}]).status is OK
    )


def test_scene_uploaded_images_without_confirmation_or_broken_manifest_fail():
    """012 FR-019: an uploaded image without confirmed rights, or a broken manifest, blocks the session."""
    unconfirmed = r.check_scene(
        True,
        [
            {"code": "missing_file", "level": "error", "product_id": "p2", "message": "thiếu ảnh"},
            {"code": "missing_confirmation", "level": "error", "product_id": "p1", "message": "chưa xác nhận quyền"},
        ],
    )
    assert unconfirmed.status is FAIL
    assert "chưa xác nhận quyền" in unconfirmed.message
    assert unconfirmed.action
    broken = r.check_scene(
        True, [{"code": "bad_uploads", "level": "error", "product_id": None, "message": "uploads/images.json hỏng"}]
    )
    assert broken.status is FAIL
    assert "images.json" in broken.message


def test_backup_video(tmp_path):
    common = {"customer_id": "shop", "avatar_id": "host_a", "catalog_version": "v1"}
    assert r.check_backup_video(None, None, **common).status is FAIL
    assert r.check_backup_video(None, "tờ mô tả hỏng", **common).status is FAIL
    assert r.check_backup_video(sheet(), "thiếu file video", **common).status is FAIL
    assert r.check_backup_video(sheet(ok=False, problems=["không có tiếng"]), None, **common).status is FAIL
    assert r.check_backup_video(sheet(), None, **common).status is OK
    other = r.check_backup_video(sheet(catalog_version="v0"), None, **common)
    assert other.status is WARN
    assert "bản nội dung" in other.message
    assert r.check_backup_video(sheet(avatar_id="host_b"), None, **common).status is WARN
    # Offline with a broken content file: the catalog version is unknown, so it is not compared.
    assert (
        r.check_backup_video(sheet(), None, customer_id="shop", avatar_id="host_a", catalog_version=None).status is OK
    )


def test_latest_sheet_picks_the_newest_and_checks_the_video(tmp_path):
    assert r.latest_sheet(tmp_path) == (None, None)
    assert r.latest_sheet(tmp_path / "missing") == (None, None)
    video = tmp_path / "b.mp4"
    video.write_bytes(b"v")
    old = tmp_path / "a.sheet.json"
    old.write_text(json.dumps(sheet(name="a", video=str(tmp_path / "gone.mp4"))), encoding="utf-8")
    os.utime(old, (1, 1))
    new = tmp_path / "b.sheet.json"
    new.write_text(json.dumps(sheet(name="b", video=str(video))), encoding="utf-8")
    found, problem = r.latest_sheet(tmp_path)
    assert found["name"] == "b" and problem is None
    video.unlink()
    found, problem = r.latest_sheet(tmp_path)
    assert found["name"] == "b" and "b.mp4" in problem
    new.write_text("{", encoding="utf-8")
    found, problem = r.latest_sheet(tmp_path)
    assert found is None and "hỏng" in problem


def test_llm_chain_reads_the_snapshot_only():
    assert r.check_llm_chain("fake", None).status is OK
    assert r.check_llm_chain("fake", None).message == "Không dùng chuỗi model"
    assert r.check_llm_chain("chain", None, app_running=False).status is FAIL
    assert r.check_llm_chain("chain", None).status is UNKNOWN
    resting = {"label": "B", "status": "resting", "reason": "rate_limit"}
    assert r.check_llm_chain("chain", {"entries": [resting]}).status is FAIL
    assert r.check_llm_chain("chain", {"entries": []}).status is FAIL
    mixed = r.check_llm_chain("chain", {"entries": [{"label": "A", "status": "ready"}, resting]})
    assert mixed.status is WARN
    assert "B (rate_limit)" in mixed.message


def test_power_and_disk():
    assert r.check_power("ac").status is OK
    assert r.check_power("battery").status is WARN
    assert r.check_power(None).status is UNKNOWN
    assert r.check_disk(4.9, 5, Path(".")).status is WARN
    assert r.check_disk(5.0, 5, Path(".")).status is OK
    assert r.check_disk(None, 5, Path(".")).status is UNKNOWN


# ---------- The whole result ----------


def test_demo_day_config_is_ready():
    result = result_of(demo_day_items())
    assert result.ready
    assert [item.id for item in result.items] == list(r.ITEM_IDS)
    assert all(item.status is OK for item in result.items)
    assert all(item.action is None for item in result.items)


def test_order_is_fixed_whatever_order_checks_ran_in():
    result = result_of(reversed(demo_day_items()))
    assert [item.id for item in result.items] == list(r.ITEM_IDS)


def test_warn_and_unknown_do_not_block_ready():
    items = demo_day_items()
    items[-2] = r.check_power(None)
    items[3] = r.check_avatar_mode("static")
    result = result_of(items)
    assert result.ready
    assert {i.status for i in result.items} == {OK, WARN, UNKNOWN}


def test_sc001_six_faults_give_exactly_six_failures():
    """SC-001: fake engine, dev, recording on, fork down... each one is a separate Lỗi naming what to do."""
    items = {item.id: item for item in demo_day_items()}
    items["reply_engine"] = r.check_reply_engine("fake")
    items["app_env"] = r.check_app_env("dev")
    items["recording"] = r.check_recording(
        "livetalking", ForkHealth(reachable=True, sessions=("s",), record_enabled=True)
    )
    items["fork"] = r.check_fork("livetalking", ForkHealth(reachable=False, error="ConnectError"))
    items["host"] = r.check_host(False, None, "livetalking")
    items["scene"] = r.check_scene(True, [{"code": "placeholder", "level": "warning", "product_id": "p1"}])
    result = result_of(items.values())
    failed = [item.id for item in result.items if item.status is FAIL]
    assert failed == ["app_env", "reply_engine", "recording", "fork", "host", "scene"]
    assert not result.ready


def test_every_problem_says_what_to_do_in_vietnamese():
    problems = [
        r.check_app_env("dev"),
        r.check_reply_engine("gemini"),
        r.check_tts_provider("fake"),
        r.check_avatar_mode("static"),
        r.check_recording("livetalking", ForkHealth(reachable=True, record_enabled=True)),
        r.check_fork("livetalking", None),
        r.check_character("", ""),
        r.check_lipsync_model("livetalking", "ultralight", "musetalk", "host_a", ["wav2lip"]),
        r.check_host(False, None, "static"),
        r.check_content(None),
        r.check_scene(True, [{"code": "placeholder", "product_id": "p1"}]),
        check_bg(bg_status("not_prepared")),
        r.check_ai_label(""),
        r.check_backup_video(None, None, customer_id="a", avatar_id="b", catalog_version="v"),
        r.check_llm_chain("chain", {"entries": []}),
        r.check_power("battery"),
        r.check_disk(1.0, 5, Path(".")),
    ]
    assert {p.id for p in problems} == set(r.ITEM_IDS)
    for item in problems:
        assert item.status is not OK
        assert item.action, item.id
        # Diacritics: written for the operator, not a code.
        assert any(ord(ch) > 127 for ch in item.message + item.action), item.id
        assert item.label == r.LABELS[item.id]


def test_manual_checks_cover_fr005():
    manual = " ".join(result_of(demo_day_items()).manual).lower()
    assert len(r.MANUAL_CHECKS) == 3
    assert "đồng ý" in manual and "meet" in manual and "runpod" in manual


def test_result_round_trips_through_json():
    result = result_of(demo_day_items()[:3] + [r.check_app_env("dev")])
    raw = json.loads(json.dumps(result.to_json(), ensure_ascii=False))
    assert set(raw) == {"checked_at", "source", "ready", "duration_ms", "output_mode", "items", "manual"}
    assert raw["items"][0] == {
        "id": "app_env",
        "label": "Chế độ chạy",
        "status": "fail",
        "message": raw["items"][0]["message"],
        "action": raw["items"][0]["action"],
    }
    assert ReadinessResult.from_json(raw) == result


def test_fork_health_parses_old_and_new_forks():
    assert ForkHealth.from_body({"ok": True, "sessions": ["a"], "record_enabled": False}) == FORK_UP.__class__(
        reachable=True, sessions=("a",), record_enabled=False
    )
    assert ForkHealth.from_body({"ok": True, "sessions": []}).record_enabled is None
    assert not ForkHealth.from_body({"ok": False}).reachable


def _settings(**over):
    from ai_live.core.config import Settings

    return Settings(_env_file=None, **over)


# --- Character prepared with another fork build (sửa lỗi 2026-11-17, data-model.md §1) ---


@pytest.mark.parametrize(
    ("prepared", "running", "status"),
    [("abc1234", "def5678", WARN), ("abc1234", "abc1234", OK), (None, "def5678", OK), ("abc1234", None, OK)],
)
def test_character_prepared_with_another_fork_warns(prepared, running, status):
    item = r.check_character("shop", "host_a", "host_a", prepared_commit=prepared, running_commit=running)
    assert item.status is status
    if status is WARN:
        assert "abc1234" in item.message and "def5678" in item.message


def test_fork_health_reads_the_running_commit():
    assert ForkHealth.from_body({"ok": True, "fork_commit": "477d4e40"}).fork_commit == "477d4e40"
    assert ForkHealth.from_body({"ok": True}).fork_commit is None


# ---------- 011 T015: "Model nhép miệng" (contracts/lipsync-selection.md §6, data-model §5) ----------

SHA = "c" * 64


def _install(character_id="demo_host_02", teacher="musetalk"):
    from ai_live.avatar.character import UltralightInstall

    record = {"character_id": character_id, "teacher": teacher, "checkpoint": {"file": "m.pth", "sha256": SHA}}
    return UltralightInstall(character_id, teacher, SHA, SHA, "fakecommit0", record)


def _fork(block):
    return ForkHealth(reachable=True, sessions=("s1",), record_enabled=False, lipsync=block)


WAV2LIP_BLOCK = {
    "model": "wav2lip",
    "teacher": None,
    "character_id": "demo_host_01",
    "avatar_id": "x",
    "checkpoint_sha256": None,
}
ULTRA_BLOCK = {
    "model": "ultralight",
    "teacher": "musetalk",
    "character_id": "demo_host_02",
    "avatar_id": "demo_host_02__ultralight_musetalk",
    "checkpoint_sha256": SHA,
}


def test_lipsync_model_item_sits_right_after_character():
    ids = list(r.ITEM_IDS)
    assert ids[ids.index("character") + 1] == "lipsync_model"
    assert r.LABELS["lipsync_model"] == "Model nhép miệng"


def test_default_wav2lip_with_matching_fork_is_ok():
    item = r.check_lipsync_model(
        "livetalking", "wav2lip", "musetalk", "demo_host_01", ["wav2lip"], fork=_fork(WAV2LIP_BLOCK)
    )
    assert item.status is OK
    assert item.message == "Model: Wav2Lip · demo_host_01"


def test_ultralight_with_install_and_matching_fork_is_ok():
    item = r.check_lipsync_model(
        "livetalking",
        "ultralight",
        "musetalk",
        "demo_host_02",
        ["ultralight"],
        install=_install(),
        fork=_fork(ULTRA_BLOCK),
    )
    assert item.status is OK
    assert item.message == "Model: Ultralight · thầy MuseTalk · demo_host_02"


def test_static_mode_does_not_check_the_model():
    assert r.check_lipsync_model("static", "ultralight", "musetalk", None, None).status is OK


def test_model_not_supported_by_the_character_fails():
    item = r.check_lipsync_model("livetalking", "ultralight", "musetalk", "demo_host_01", ["wav2lip"])
    assert item.status is FAIL
    assert item.message == "Nhân vật demo_host_01 không có model ultralight"
    assert "LIVETALKING_MODEL" in item.action


def test_missing_install_fails_and_says_how_to_install():
    item = r.check_lipsync_model(
        "livetalking",
        "ultralight",
        "infinitetalk",
        "demo_host_02",
        ["ultralight"],
        install_problem="thiếu ultralight_install.json của thầy infinitetalk",
        fork=_fork(ULTRA_BLOCK),
    )
    assert item.status is FAIL
    assert item.message.startswith("Chưa cài model Ultralight thầy infinitetalk cho demo_host_02")
    assert "install" in item.action


@pytest.mark.parametrize(
    ("model", "block"), [("ultralight", WAV2LIP_BLOCK), ("wav2lip", ULTRA_BLOCK), ("ultralight", None)]
)
def test_fork_running_another_model_fails(model, block):
    character = "demo_host_02"
    install = _install() if model == "ultralight" else None
    item = r.check_lipsync_model(
        "livetalking", model, "musetalk", character, ["wav2lip", "ultralight"], install=install, fork=_fork(block)
    )
    assert item.status is FAIL
    running = block["model"] if block else "wav2lip"
    assert item.message == f"Phần nhép miệng đang chạy {running}, cấu hình là {model}: bật lại fork"


def test_old_fork_without_block_is_fine_for_wav2lip():
    item = r.check_lipsync_model("livetalking", "wav2lip", "musetalk", "demo_host_01", ["wav2lip"], fork=_fork(None))
    assert item.status is OK


@pytest.mark.parametrize("fork", [None, ForkHealth(reachable=False, error="ConnectError")])
def test_without_fork_only_the_first_two_steps_run(fork):
    ok = r.check_lipsync_model(
        "livetalking", "ultralight", "musetalk", "demo_host_02", ["ultralight"], install=_install(), fork=fork
    )
    assert ok.status is OK and "chưa kiểm fork" in ok.message
    missing = r.check_lipsync_model(
        "livetalking", "ultralight", "musetalk", "demo_host_02", ["ultralight"], install_problem="thiếu", fork=fork
    )
    assert missing.status is FAIL


def test_fork_health_reads_the_lipsync_block():
    assert ForkHealth.from_body({"ok": True, "lipsync": ULTRA_BLOCK}).lipsync == ULTRA_BLOCK
    assert ForkHealth.from_body({"ok": True}).lipsync is None
    assert ForkHealth.from_body({"ok": True, "lipsync": "x"}).lipsync is None


@pytest.mark.anyio
async def test_offline_ultralight_character_without_clips(tmp_path):
    """Offline (fork down): the model item checks the install record; "Nhân vật" does not ask for clips."""
    import hashlib

    from fixtures.character_builder import CHARACTER_ID, CUSTOMER_ID, make_character_dir

    avatar_dir = make_character_dir(tmp_path, character={"clips": [], "lipsync_models": ["ultralight"]})
    evidence = avatar_dir / "ultralight" / "musetalk"
    evidence.mkdir(parents=True)
    (evidence / "best_trainloss.pth").write_bytes(b"w")
    record = {
        "character_id": CHARACTER_ID,
        "teacher": "musetalk",
        "checkpoint": {"file": "best_trainloss.pth", "sha256": hashlib.sha256(b"w").hexdigest()},
    }
    (evidence / "ultralight_install.json").write_text(json.dumps(record), encoding="utf-8")
    settings = _settings(
        avatar_mode="livetalking",
        avatar_dir=avatar_dir,
        avatar_id=CHARACTER_ID,
        customer_id=CUSTOMER_ID,
        livetalking_model="ultralight",
        livetalking_url="http://127.0.0.1:9",
        session_data_dir=tmp_path / "sessions",
        backup_video_dir=tmp_path / "backup",
        product_data_path=tmp_path / "none.docx",
        scene_enabled=False,
    )
    result = await r.run_offline(settings)
    items = {item.id: item for item in result.items}
    assert items["lipsync_model"].status is OK, items["lipsync_model"]
    assert "chưa kiểm fork" in items["lipsync_model"].message
    assert items["character"].status is OK
    assert "clip" not in items["character"].message


# ---------- 013 T021: realistic desk products ----------

HANDS_MISSING = {"code": "hands_zone_missing", "level": "warning", "product_id": None, "message": "chưa khai vùng tay"}


def test_scene_realistic_without_hands_zone_warns():
    item = r.check_scene(True, [HANDS_MISSING])
    assert item.status is WARN
    assert "vùng tay" in item.message
    assert "--debug-zones" in item.action and "hands_zone" in item.action
    # An error still wins: the operator sees the bigger problem first.
    bad = {"code": "bad_layout", "level": "error", "product_id": None, "message": "layout.mode lạ"}
    worse = r.check_scene(True, [HANDS_MISSING, bad])
    assert worse.status is WARN and "layout.mode lạ" in worse.message


def test_scene_bad_layout_is_an_error_like_009():
    item = r.check_scene(True, [{"code": "bad_layout", "level": "error", "product_id": None, "message": "mode lạ"}])
    assert item.status is WARN
    assert "1 lỗi" in item.message and "mode lạ" in item.message


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("layout", "hands", "warned"),
    [("realistic", None, True), ("realistic", [0.3, 0.77, 0.7, 1.0], False), ("rows", None, False)],
)
async def test_offline_scene_warns_only_realistic_without_hands_zone(tmp_path, layout, hands, warned):
    from fixtures.character_builder import CHARACTER_ID, CUSTOMER_ID, make_character_dir
    from fixtures.scene_builder import make_scene_dir

    avatar_dir = make_character_dir(tmp_path, desk_in_image=True, desk_top=0.868, hands_zone=hands)
    scene_dir = make_scene_dir(
        tmp_path / "scenes" / "demo", [], customer_id=CUSTOMER_ID, scene={"layout": {"mode": layout}}
    )
    settings = _settings(
        avatar_mode="livetalking",
        avatar_dir=avatar_dir,
        avatar_id=CHARACTER_ID,
        customer_id=CUSTOMER_ID,
        livetalking_url="http://127.0.0.1:9",
        session_data_dir=tmp_path / "sessions",
        backup_video_dir=tmp_path / "backup",
        product_data_path=tmp_path / "none.docx",
        scene_enabled=True,
        scene_dir=scene_dir,
    )
    result = await r.run_offline(settings)
    scene = next(item for item in result.items if item.id == "scene")
    assert ("vùng tay" in scene.message) is warned, scene
    if warned:
        assert scene.status is WARN


# ---------- 013 T036 (FR-018, research R10): a picture with its background, no matting model ----------

ART_BG = {"code": "art_has_background", "level": "warning", "product_id": "p1", "message": "Ảnh của p1 còn nền"}
NO_MATTING = {
    "code": "matting_model_missing",
    "level": "warning",
    "product_id": None,
    "message": "Chưa cài model tách nền",
}


def test_scene_picture_with_background_warns():
    item = r.check_scene(True, [ART_BG])
    assert item.status is WARN
    assert "còn nền" in item.message
    assert "Ảnh sản phẩm" in item.action


def test_scene_without_matting_model_warns():
    item = r.check_scene(True, [NO_MATTING])
    assert item.status is WARN
    assert "model tách nền" in item.message
    assert "MATTING_MODEL_PATH" in item.action


def test_scene_warnings_are_all_shown_together():
    item = r.check_scene(True, [HANDS_MISSING, ART_BG, NO_MATTING])
    assert item.status is WARN
    assert "vùng tay" in item.message and "còn nền" in item.message and "model tách nền" in item.message
    assert "hands_zone" in item.action and "Ảnh sản phẩm" in item.action and "MATTING_MODEL_PATH" in item.action


def _opaque_kit(scene_dir: Path, pid: str) -> None:
    from PIL import Image

    Image.new("RGBA", (120, 160), (200, 60, 40, 255)).save(scene_dir / "products" / f"{pid}.png")


def _scene_settings(tmp_path: Path, layout: str, **over):
    from fixtures.scene_builder import CUSTOMER, make_scene_dir

    scene_dir = make_scene_dir(
        tmp_path / "scenes" / "demo", ["p1"], customer_id=CUSTOMER, scene={"layout": {"mode": layout}}
    )
    _opaque_kit(scene_dir, "p1")
    values = {
        "avatar_mode": "static",
        "customer_id": CUSTOMER,
        "session_data_dir": tmp_path / "sessions",
        "backup_video_dir": tmp_path / "backup",
        "product_data_path": tmp_path / "none.docx",
        "scene_enabled": True,
        "scene_dir": scene_dir,
    }
    values.update(over)
    return _settings(**values)


@pytest.mark.anyio
@pytest.mark.parametrize(("layout", "warned"), [("realistic", True), ("rows", False)])
async def test_offline_scene_warns_about_a_picture_with_background_only_on_the_realistic_desk(
    tmp_path, monkeypatch, layout, warned
):
    monkeypatch.setattr(r, "_offline_content", lambda settings: (catalog(product("p1", primary=True)), None))
    model = tmp_path / "isnet-general-use.onnx"
    model.write_bytes(b"onnx")
    result = await r.run_offline(_scene_settings(tmp_path, layout, matting_model_path=model))
    scene = next(item for item in result.items if item.id == "scene")
    assert ("còn nền" in scene.message) is warned, scene
    assert "model tách nền" not in scene.message


@pytest.mark.anyio
@pytest.mark.parametrize("missing", ["unset", "no_file"])
async def test_offline_scene_warns_without_a_matting_model(tmp_path, monkeypatch, missing):
    monkeypatch.setattr(r, "_offline_content", lambda settings: (catalog(product("p1", primary=True)), None))
    path = None if missing == "unset" else tmp_path / "models" / "nope.onnx"
    result = await r.run_offline(_scene_settings(tmp_path, "rows", matting_model_path=path))
    scene = next(item for item in result.items if item.id == "scene")
    assert scene.status is WARN
    assert "model tách nền" in scene.message


# ---------- 014 T036 (contracts/api.md "Kiểm tra sẵn sàng"; FR-012, FR-015, SC-006): room behind the host ----------

BG_ID = "demo_host_01"
REVIEW = "assets/avatars/demo_host_01/background/review.jpg"
EVERY_FALLBACK = [
    "style_not_available",
    "no_product_art",
    "no_shop_photo",
    "shop_photo_unconfirmed",
    "plate_failed",
    "avatar_static",
    "fork_unsupported",
    "not_prepared",
    "mismatch:frame_not_prepared:3",
    "mismatch:size_mismatch",
    "mismatch:character_mismatch",
    "mismatch:mask_unreadable:masks/0002.png",
    "rejected:sai cỡ khung",
    "failed:lỗi ghép",
]


def bg_status(reason, *, style="ke_hang", active=None, reviewed=False, mask_status=None):
    from ai_live.scene.background import fallback_text

    if reason is None:
        message = None
    else:
        problem, fix = fallback_text(reason, BG_ID, style=style)
        message = f"{problem}: {fix}"
    if mask_status is None:
        mask_status = (
            "missing" if reason == "not_prepared" else "mismatch" if str(reason).startswith("mismatch") else "valid"
        )
    return {
        "style": style,
        "active": reason is None if active is None else active,
        "mask_status": mask_status,
        "fallback_reason": reason,
        "fallback_message": message,
        "reviewed": reviewed,
        "items": ["p1"],
        "changed_at": "2026-11-24T09:00:00+00:00",
    }


def check_bg(status, frames=81):
    return r.check_background(status, character_id=BG_ID, frames=frames, review_path=REVIEW)


def test_background_is_a_readiness_item_next_to_the_scene():
    assert r.ITEM_IDS.index("background") == r.ITEM_IDS.index("scene") + 1
    assert r.LABELS["background"] == "Nền sau host"


def test_background_original_room_is_ok():
    item = check_bg(bg_status("style_goc", style="goc", mask_status="unknown"))
    assert (item.status, item.message) == (OK, "Nền: phòng gốc")


def test_background_with_the_scene_off_is_ok():
    from ai_live.scene.background import disabled_background_status

    item = check_bg(disabled_background_status())
    assert (item.status, item.message) == (OK, "Nền: phòng gốc")


def test_background_not_prepared_warns_with_the_command():
    item = check_bg(bg_status("not_prepared"))
    assert item.status is WARN
    assert "Nhân vật chưa có nền, live sẽ hiện phòng gốc" in item.message
    assert f"uv run python -m ai_live.avatar background-prepare {BG_ID}" in item.action


def test_background_mismatch_warns_with_the_reason_and_the_command():
    item = check_bg(bg_status("mismatch:size_mismatch"))
    assert item.status is WARN
    assert "cỡ khung" in item.message
    assert f"background-prepare {BG_ID}" in item.action


def test_background_without_cut_out_products_warns():
    item = check_bg(bg_status("no_product_art"))
    assert item.status is WARN
    assert "Chưa có ảnh sản phẩm đã bỏ nền cho kệ hàng" in item.message


def test_background_valid_but_not_looked_at_warns_with_the_review_picture():
    item = check_bg(bg_status(None, reviewed=False))
    assert item.status is WARN
    assert "Mặt nạ nền chưa được duyệt bằng mắt" in item.message
    assert REVIEW in item.action and "--mark-reviewed" in item.action


def test_background_valid_and_reviewed_is_ok():
    item = check_bg(bg_status(None, reviewed=True))
    assert (item.status, item.message) == (OK, "Nền: kệ hàng, đã chuẩn bị 81 khung")


@pytest.mark.parametrize("reason", EVERY_FALLBACK)
def test_background_never_fails_and_reuses_the_fallback_message(reason):
    status = bg_status(reason)
    item = check_bg(status)
    assert item.status in (OK, WARN)
    if item.status is WARN:
        # One wording for the control page and readiness (T042): the status sentence, split into problem and fix.
        assert f"{item.message}: {item.action}" == status["fallback_message"]


def _bg_settings(tmp_path: Path, variant: str, *, reviewed: bool = False):
    from fixtures.background_builder import make_background_dir
    from fixtures.character_builder import CHARACTER_ID, CUSTOMER_ID, READY_PREPARE, make_character_dir
    from fixtures.scene_builder import make_scene_dir

    avatar_dir = make_character_dir(tmp_path / "avatars", prepare=READY_PREPARE)
    make_background_dir(avatar_dir, variant, reviewed=reviewed)
    scene_dir = make_scene_dir(
        tmp_path / "scenes" / "demo", ["p1"], customer_id=CUSTOMER_ID, scene={"background": {"style": "ke_hang"}}
    )
    return _settings(
        avatar_mode="livetalking",
        avatar_dir=avatar_dir,
        avatar_id=CHARACTER_ID,
        customer_id=CUSTOMER_ID,
        livetalking_url="http://127.0.0.1:9",
        session_data_dir=tmp_path / "sessions",
        backup_video_dir=tmp_path / "backup",
        product_data_path=tmp_path / "none.docx",
        scene_enabled=True,
        scene_dir=scene_dir,
    )


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("variant", "reviewed", "status", "needle"),
    [
        ("valid", False, WARN, "chưa được duyệt"),
        ("valid", True, OK, "đã chuẩn bị 3 khung"),
        ("missing", False, WARN, "chưa có nền"),
        ("mismatch", False, WARN, "nhân vật khác"),
    ],
)
async def test_offline_background_reads_the_masks_from_disk(tmp_path, monkeypatch, variant, reviewed, status, needle):
    # The fork is down (port 9): only the manifest on disk can tell.
    monkeypatch.setattr(r, "_offline_content", lambda settings: (catalog(product("p1", primary=True)), None))
    result = await r.run_offline(_bg_settings(tmp_path, variant, reviewed=reviewed))
    item = next(i for i in result.items if i.id == "background")
    assert item.status is status, item
    assert needle in item.message, item

"""005 HTTP routes (T028; contracts/api.md §1–§3): speak-audio, host-config, avatar image, renderer at startup."""

from __future__ import annotations

import io
import json
import wave
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from ai_live.app.main import AvatarModeError, create_app
from ai_live.avatar.static_renderer import StaticRenderer
from ai_live.avatar.switching_renderer import SwitchingRenderer
from fixtures.character_builder import CHARACTER_ID, CUSTOMER_ID, READY_PREPARE, make_character_dir

SPEAK_AUDIO = "/api/debug/speak-audio"


def make_wav(seconds: float = 0.5, *, rate: int = 16000, channels: int = 1, width: int = 2) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(channels)
        w.setsampwidth(width)
        w.setframerate(rate)
        w.writeframes(b"\x00" * width * channels * round(seconds * rate))
    return buf.getvalue()


def post_wav(client: TestClient, data: bytes, filename: str = "thu.wav"):
    return client.post(SPEAK_AUDIO, content=data, headers={"Content-Type": "audio/wav", "X-Filename": filename})


def host_play_one(ws, *, ack: bool = True) -> list[dict]:
    """Read messages up to `sentence_end`, acking like the real host page."""
    got: list[dict] = []
    while True:
        message = ws.receive()
        if message.get("text") is None:
            continue
        data = json.loads(message["text"])
        got.append(data)
        if ack and data["type"] == "sentence_start":
            ws.send_json({"type": "playback_started", "utterance_id": data["utterance_id"], "seq": data["seq"]})
        if data["type"] == "sentence_end":
            if ack:
                ws.send_json({"type": "sentence_played", "utterance_id": data["utterance_id"], "seq": data["seq"]})
            return got


@pytest.fixture
def client(app_settings):
    with TestClient(create_app(app_settings)) as c:
        yield c


@pytest.fixture
def lipsync_settings(app_settings, tmp_path: Path):
    avatar_dir = make_character_dir(tmp_path / "avatars", prepare=READY_PREPARE)
    return app_settings.model_copy(
        update={
            "avatar_mode": "livetalking",
            "customer_id": CUSTOMER_ID,
            "avatar_id": CHARACTER_ID,
            "avatar_dir": avatar_dir,
            # Nothing listens there: these tests never get a host-page WebRTC session, so the renderer never dials.
            "livetalking_url": "http://127.0.0.1:9",
        }
    )


# ---------- POST /api/debug/speak-audio ----------


def test_speak_audio_200_after_playback(client: TestClient) -> None:
    with client.websocket_connect("/ws/host") as host, ThreadPoolExecutor(1) as pool:
        host.send_json({"type": "ready"})
        future = pool.submit(post_wav, client, make_wav(0.5), "giong-mau.wav")
        got = host_play_one(host)
        r = future.result(timeout=5)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["utterance_id"].startswith("dbg-audio-")
    assert body["duration_s"] == pytest.approx(0.5, abs=0.01)
    assert isinstance(body["first_frame_s"], float) and body["first_frame_s"] >= 0
    assert "render_fps" in body and body["render_fps"] is None  # the still image measures no frame rate
    start = got[0]
    assert start["type"] == "sentence_start" and start["text"] == "giong-mau.wav"
    assert start["sample_rate"] == 16000


@pytest.mark.parametrize(
    "data",
    [
        make_wav(rate=44100),
        make_wav(channels=2),
        make_wav(width=1),
        b"RIFF0000WAVEnot really",
        b"",
    ],
    ids=["44khz", "stereo", "8bit", "garbage", "empty"],
)
def test_speak_audio_422_bad_format(client: TestClient, data: bytes) -> None:
    r = post_wav(client, data)
    assert r.status_code == 422
    body = r.json()
    assert body["error"] == "bad_audio"
    assert "PCM 16-bit, mono, 16 kHz" in body["message"]


def test_speak_audio_422_reports_read_format(client: TestClient) -> None:
    body = post_wav(client, make_wav(rate=44100, channels=2)).json()
    assert body["details"] == {"sample_rate": 44100, "channels": 2, "sample_width_bits": 16}


def test_speak_audio_422_over_5mb(client: TestClient) -> None:
    r = post_wav(client, make_wav(170))  # 170 s x 32 000 B/s > 5 MB
    assert r.status_code == 422
    assert r.json()["error"] == "bad_audio"


def test_speak_audio_409_while_speaking(client: TestClient) -> None:
    with client.websocket_connect("/ws/host") as host, ThreadPoolExecutor(1) as pool:
        host.send_json({"type": "ready"})
        future = pool.submit(post_wav, client, make_wav(0.3))
        first = host.receive_json()
        assert first["type"] == "sentence_start"
        busy = post_wav(client, make_wav(0.3))
        assert busy.status_code == 409
        assert busy.json()["error"] == "busy"
        assert busy.json()["message"] == "Đang có lượt nói, tạm dừng show rồi thử lại."
        host.send_json({"type": "playback_started", "utterance_id": first["utterance_id"], "seq": 0})
        host.send_json({"type": "sentence_played", "utterance_id": first["utterance_id"], "seq": 0})
        assert future.result(timeout=5).status_code == 200


def test_speak_audio_503_without_host(client: TestClient) -> None:
    r = post_wav(client, make_wav(0.2))
    assert r.status_code == 503
    assert r.json()["error"] == "host_unavailable"


def test_speak_audio_404_when_not_dev(app_settings) -> None:
    with TestClient(create_app(app_settings.model_copy(update={"app_env": "prod"}))) as c:
        assert post_wav(c, make_wav(0.2)).status_code == 404


def test_speak_audio_503_lipsync_unavailable(lipsync_settings) -> None:
    """Livetalking mode, host page open but `/offer` failed (no fork): the turn fails with the renderer's kind."""
    with TestClient(create_app(lipsync_settings)) as c, c.websocket_connect("/ws/host") as host:
        host.send_json({"type": "ready", "lipsync_session": None})
        r = post_wav(c, make_wav(0.2))
    assert r.status_code == 503
    assert r.json()["error"] == "lipsync_unavailable"
    assert r.json()["message"]


# ---------- GET /api/host-config ----------


def test_host_config_static(app_settings) -> None:
    s = app_settings.model_copy(update={"ai_label_text": "AI", "ai_label_position": "bottom-left"})
    with TestClient(create_app(s)) as c:
        body = c.get("/api/host-config").json()
    assert body == {
        "mode": "static",
        "active": "static",
        "livetalking_url": s.livetalking_url,
        "ai_label": {"text": "AI", "position": "bottom-left"},
    }


def test_host_config_livetalking(lipsync_settings) -> None:
    with TestClient(create_app(lipsync_settings)) as c:
        body = c.get("/api/host-config").json()
    assert body["mode"] == "livetalking"
    assert body["active"] == "livetalking"
    assert body["livetalking_url"] == "http://127.0.0.1:9"
    assert body["ai_label"]["text"] == lipsync_settings.ai_label_text


# ---------- Avatar image and renderer choice ----------


def test_livetalking_serves_character_face(lipsync_settings) -> None:
    face = (lipsync_settings.avatar_dir / "face.png").read_bytes()
    with TestClient(create_app(lipsync_settings)) as c:
        assert isinstance(c.app.state.ctx.renderer, SwitchingRenderer)
        r = c.get("/avatar-image")
        html = c.get("/host").text
    assert r.status_code == 200
    assert r.content == face
    assert "/avatar-image" in html


def test_livetalking_other_customer_does_not_start(lipsync_settings) -> None:
    s = lipsync_settings.model_copy(update={"customer_id": "khach_khac"})
    with pytest.raises(AvatarModeError, match="khách"):
        with TestClient(create_app(s)):
            pass


def test_livetalking_unprepared_character_does_not_start(app_settings, tmp_path: Path) -> None:
    avatar_dir = make_character_dir(tmp_path / "avatars")
    s = app_settings.model_copy(
        update={
            "avatar_mode": "livetalking",
            "customer_id": CUSTOMER_ID,
            "avatar_id": CHARACTER_ID,
            "avatar_dir": avatar_dir,
        }
    )
    with pytest.raises(AvatarModeError, match="prepare"):
        with TestClient(create_app(s)):
            pass


def test_static_mode_keeps_static_renderer(app_settings, tmp_path: Path) -> None:
    """FR-014: AVATAR_MODE=static runs exactly as in 001/004, no wrapper, the configured still image."""
    image = tmp_path / "idle.png"
    image.write_bytes(b"\x89PNG\r\nstatic")
    with TestClient(create_app(app_settings.model_copy(update={"avatar_static_image": image}))) as c:
        assert type(c.app.state.ctx.renderer) is StaticRenderer
        assert c.get("/avatar-image").content == image.read_bytes()


# ---------- 005 US2 (T052): /api/avatar, /api/avatar/lipsync, /health avatar (contracts/api.md §1–§2) ----------

NOT_LIPSYNC_MESSAGE = "Phiên đang chạy chế độ ảnh tĩnh theo cấu hình, không có nhân vật nhép miệng để bật lại."


def test_avatar_state_static(client: TestClient) -> None:
    body = client.get("/api/avatar").json()
    assert body["mode"]["configured"] == "static" and body["mode"]["active"] == "static"
    assert body["character"] is None
    assert body["lipsync"] is None


def test_avatar_state_livetalking(lipsync_settings) -> None:
    with TestClient(create_app(lipsync_settings)) as c:
        body = c.get("/api/avatar").json()
    assert body["mode"] == {
        "configured": "livetalking",
        "active": "livetalking",
        "reason": None,
        "consecutive_errors": 0,
        "changed_at": None,
    }
    assert body["character"] == {
        "character_id": CHARACTER_ID,
        "customer_id": CUSTOMER_ID,
        "clips": {"idle": 2, "talk": 2},
    }
    lipsync = body["lipsync"]
    assert set(lipsync) == {
        "connected",
        "boot_id",
        "fork_commit",
        "session_id",
        "vram_used_mb",
        "infer_fps",
        "last_error",
        "updated_at",
    }
    assert lipsync["connected"] is False  # nothing listens on the configured fork URL


def test_enable_lipsync_after_fallback(lipsync_settings) -> None:
    with TestClient(create_app(lipsync_settings)) as c:
        renderer = c.app.state.ctx.renderer
        assert isinstance(renderer, SwitchingRenderer)

        async def fall_back() -> None:
            renderer.record_render_outcome("u1", False, error_kind="lipsync_unavailable")
            renderer.record_render_outcome("u2", False, error_kind="lipsync_unavailable")

        c.portal.call(fall_back)
        before = c.get("/api/avatar").json()["mode"]
        assert before["active"] == "static" and before["reason"] == "render_errors"
        assert before["consecutive_errors"] == 2
        assert c.get("/health").json()["avatar"]["active"] == "static"

        r = c.post("/api/avatar/lipsync")
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["configured"] == "livetalking" and body["active"] == "livetalking"
        assert body["reason"] is None and body["consecutive_errors"] == 0
        assert body["changed_at"] is not None
        assert c.get("/api/avatar").json()["mode"]["active"] == "livetalking"


def test_enable_lipsync_409_in_static(client: TestClient) -> None:
    r = client.post("/api/avatar/lipsync")
    assert r.status_code == 409
    assert r.json()["error"] == "not_lipsync_mode"
    assert r.json()["message"] == NOT_LIPSYNC_MESSAGE


def test_health_avatar_static(client: TestClient) -> None:
    body = client.get("/health").json()
    assert body["avatar"] == {"configured": "static", "active": "static", "lipsync_connected": False}


def test_health_avatar_livetalking(lipsync_settings) -> None:
    with TestClient(create_app(lipsync_settings)) as c:
        body = c.get("/health").json()
    assert body["status"] == "ok"
    assert body["avatar"] == {"configured": "livetalking", "active": "livetalking", "lipsync_connected": False}

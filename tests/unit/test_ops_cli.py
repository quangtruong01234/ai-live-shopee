"""007 T020: `python -m ai_live.ops readiness` (contracts/cli.md): the app answers, or an offline check runs."""

from __future__ import annotations

import json
import time
from pathlib import Path

import httpx
import pytest

from ai_live.ops import __main__ as ops_main
from ai_live.ops import readiness as r
from ai_live.ops import rehearsal as rh
from fixtures.content_builder import valid_docx
from fixtures.session_logs import write_show_logs

APP = "http://127.0.0.1:8000"


def app_result(*, ready: bool) -> dict:
    items = [r.check_app_env("demo"), r.check_reply_engine("chain" if ready else "fake")]
    return r.build_result(items, "app", time.perf_counter()).to_json()


def app_answering(body: dict, seen: list[str] | None = None) -> httpx.MockTransport:
    def handle(request: httpx.Request) -> httpx.Response:
        if seen is not None:
            seen.append(str(request.url))
        return httpx.Response(200, json=body)

    return httpx.MockTransport(handle)


def app_down() -> httpx.MockTransport:
    def handle(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    return httpx.MockTransport(handle)


@pytest.fixture
def offline_settings(settings, tmp_path: Path):
    return settings.model_copy(
        update={
            "product_data_path": tmp_path / "missing.docx",
            "backup_video_dir": tmp_path / "backup",
            "session_data_dir": tmp_path,
        }
    )


def test_prints_the_apps_result_and_exits_0_when_ready(capsys):
    seen: list[str] = []
    code = r.cli_readiness(APP, transport=app_answering(app_result(ready=True), seen))
    out = capsys.readouterr().out
    assert code == 0
    assert seen == [f"{APP}/api/readiness"]
    assert "Chế độ chạy" in out and "Bộ trả lời" in out
    assert "Việc tự xác nhận" in out
    assert out.strip().endswith("Kết luận: SẴN SÀNG")


def test_exits_1_when_not_ready_and_says_what_to_do(capsys):
    code = r.cli_readiness(APP, transport=app_answering(app_result(ready=False)))
    out = capsys.readouterr().out
    assert code == 1
    assert "LỖI" in out
    assert "→ Đặt REPLY_ENGINE=chain" in out
    assert "CHƯA SẴN SÀNG" in out


def test_json_prints_the_result(capsys):
    body = app_result(ready=False)
    assert r.cli_readiness(APP, as_json=True, transport=app_answering(body)) == 1
    assert json.loads(capsys.readouterr().out) == body


def test_app_down_checks_offline(capsys, offline_settings):
    s = offline_settings.model_copy(update={"reply_engine": "chain"})
    code = r.cli_readiness(APP, as_json=True, settings=s, transport=app_down())
    body = json.loads(capsys.readouterr().out)
    assert code == 1
    assert body["source"] == "offline"
    items = {item["id"]: item for item in body["items"]}
    assert [item["id"] for item in body["items"]] == list(r.ITEM_IDS)
    for item_id in ("host", "llm_chain"):
        assert items[item_id]["status"] == "fail"
        assert items[item_id]["message"] == r.APP_DOWN
    # Files are still checked without the app.
    assert items["content"]["status"] == "fail"
    assert items["backup_video"]["status"] == "fail"


def test_offline_with_real_content(capsys, offline_settings, tmp_path: Path):
    content = tmp_path / "valid.docx"
    content.write_bytes(valid_docx())
    s = offline_settings.model_copy(update={"product_data_path": content})
    r.cli_readiness(APP, as_json=True, settings=s, transport=app_down())
    items = {item["id"]: item for item in json.loads(capsys.readouterr().out)["items"]}
    assert items["content"]["status"] == "ok"
    assert items["llm_chain"]["status"] == "ok"  # REPLY_ENGINE=fake: no chain to need


def test_offline_asks_the_fork_directly(capsys, offline_settings):
    asked: list[str] = []

    def fork(request: httpx.Request) -> httpx.Response:
        asked.append(request.url.path)
        return httpx.Response(200, json={"ok": True, "sessions": [], "record_enabled": True})

    s = offline_settings.model_copy(update={"avatar_mode": "livetalking", "livetalking_url": "http://127.0.0.1:8010"})
    r.cli_readiness(APP, as_json=True, settings=s, transport=app_down(), fork_transport=httpx.MockTransport(fork))
    items = {item["id"]: item for item in json.loads(capsys.readouterr().out)["items"]}
    assert asked == ["/ailive/health"]
    assert items["recording"]["status"] == "fail"
    assert items["fork"]["status"] == "warn"


def test_app_answering_an_error_is_not_treated_as_down(capsys, offline_settings):
    broken = httpx.MockTransport(lambda request: httpx.Response(500, text="boom"))
    assert r.cli_readiness(APP, settings=offline_settings, transport=broken) == 1
    out = capsys.readouterr().out
    assert "trả lời nhưng không đọc được" in out
    assert "offline" not in out


def test_main_dispatches_readiness(monkeypatch):
    calls: list[tuple] = []
    monkeypatch.setattr(r, "cli_readiness", lambda url, *, as_json: calls.append((url, as_json)) or 0)
    assert ops_main.main(["readiness", "--url", "http://x:1", "--json"]) == 0
    assert calls == [("http://x:1", True)]


# --- `report` (007 US3 T038) ---


def test_report_by_session_dir_writes_both_files_and_exits_0_when_passing(capsys, tmp_path: Path):
    show = write_show_logs(tmp_path)
    assert rh.cli_report(str(show.directory)) == 0
    out = capsys.readouterr().out
    assert "Tiêu chí 3" in out and "ĐẠT" in out
    assert (show.directory / f"rehearsal_{show.show_id}.md").is_file()
    assert (show.directory / f"rehearsal_{show.show_id}.json").is_file()


def test_report_by_session_id_looks_in_session_data_dir(capsys, settings, tmp_path: Path):
    show = write_show_logs(tmp_path, duration_s=600.0)
    s = settings.model_copy(update={"session_data_dir": tmp_path})
    assert rh.cli_report(show.session_id, settings=s) == 1  # SHORT is not a pass
    assert "Tiêu chí 4" in capsys.readouterr().out


def test_report_defaults_to_the_last_show_and_takes_show(capsys, tmp_path: Path):
    write_show_logs(tmp_path, show_id="first", gaps=[("script", 9.0)] * 3, duration_s=200.0)
    show = write_show_logs(tmp_path, show_id="second")
    assert rh.cli_report(str(show.directory), as_json=True) == 0
    assert json.loads(capsys.readouterr().out)["show_id"] == "second"
    assert rh.cli_report(str(show.directory), show_id="first", as_json=True) == 1
    data = json.loads(capsys.readouterr().out)
    assert data["show_id"] == "first"
    assert data["criterion_3"] == "fail"
    assert (show.directory / "rehearsal_first.json").is_file()


def test_report_exits_2_when_the_session_or_show_is_missing(capsys, settings, tmp_path: Path):
    s = settings.model_copy(update={"session_data_dir": tmp_path})
    assert rh.cli_report("no-such-session", settings=s) == 2
    assert "Không tìm thấy phiên" in capsys.readouterr().out
    show = write_show_logs(tmp_path)
    assert rh.cli_report(str(show.directory), show_id="missing") == 2
    assert "Không tìm thấy show" in capsys.readouterr().out
    empty = tmp_path / "empty"
    empty.mkdir()
    assert rh.cli_report(str(empty)) == 2
    assert "chưa có show" in capsys.readouterr().out


def test_main_dispatches_report(monkeypatch):
    calls: list[tuple] = []
    monkeypatch.setattr(
        rh, "cli_report", lambda session, *, show_id, as_json: calls.append((session, show_id, as_json)) or 0
    )
    assert ops_main.main(["report", "20261113-155721", "--show", "abc", "--json"]) == 0
    assert calls == [("20261113-155721", "abc", True)]

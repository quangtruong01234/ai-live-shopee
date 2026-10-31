"""T039, T063: run each stage on its own from the CLI (Article IV)."""

from __future__ import annotations

import re
import wave

import pytest

from ai_live.brain import __main__ as brain_cli
from ai_live.brain.fake_engine import FakeReplyEngine
from ai_live.comments import __main__ as comments_cli
from ai_live.tts import __main__ as tts_cli
from fixtures.content_builder import valid_docx


@pytest.fixture
def content(tmp_path):
    path = tmp_path / "valid.docx"
    path.write_bytes(valid_docx())
    return path


@pytest.fixture
def fake_env(monkeypatch):
    monkeypatch.setenv("REPLY_ENGINE", "fake")
    monkeypatch.setenv("TTS_PROVIDER", "fake")


_TIMED_LINE = re.compile(r"^\[\s*\d+\.\d{2} s\] .+")


def test_brain_ask_prints_each_sentence_with_time(fake_env, content, capsys):
    code = brain_cli.main(["ask", "giá bao nhiêu vậy shop?", "--author", "Lan", "--content", str(content)])
    out = capsys.readouterr().out
    assert code == 0
    lines = [line for line in out.splitlines() if _TIMED_LINE.match(line)]
    assert lines, out
    joined = " ".join(lines)
    assert "bạn Lan" in joined
    assert "250.000đ" in joined and "420.000đ" in joined


def test_brain_ask_prints_guard_reason_when_blocked(fake_env, content, capsys, monkeypatch):
    def fake_factory(settings):
        return FakeReplyEngine("Dạ kem này chữa khỏi mụn luôn nha bạn Lan. Giá chỉ 99k thôi.")

    monkeypatch.setattr(brain_cli, "create_reply_engine", fake_factory)
    code = brain_cli.main(["ask", "kem có trị mụn không?", "--author", "Lan", "--content", str(content)])
    out = capsys.readouterr().out
    assert code == 0
    assert "forbidden_claim" in out
    assert "Dạ phần này em chưa có thông tin, bạn Lan nhắn shop giúp em nha." in out
    # A block stops generation: later sentences must not be printed.
    assert "99k" not in out


def test_brain_ask_missing_content_file_exits_1(fake_env, tmp_path, capsys):
    code = brain_cli.main(["ask", "giá?", "--content", str(tmp_path / "missing.docx")])
    assert code == 1


def test_tts_say_writes_readable_wav(fake_env, tmp_path, capsys):
    out_file = tmp_path / "out.wav"
    code = tts_cli.main(["say", "Dạ chào bạn Lan", "--out", str(out_file)])
    out = capsys.readouterr().out
    assert code == 0
    assert "chunk đầu" in out
    with wave.open(str(out_file), "rb") as wav:
        assert wav.getnchannels() == 1
        assert wav.getsampwidth() == 2
        assert wav.getframerate() == 16000
        assert wav.getnframes() == pytest.approx(4 * 0.25 * 16000, rel=0.05)


def test_tts_say_unknown_provider_exits_1(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("TTS_PROVIDER", "elevenlabs")
    code = tts_cli.main(["say", "xin chào", "--out", str(tmp_path / "x.wav")])
    assert code == 1
    assert "TTS_PROVIDER" in capsys.readouterr().out


def test_comments_cli_prints_priority_drop_reason_and_queue_order(capsys):
    code = comments_cli.main(["Lan: giá bao nhiêu?", "Huy: hello shop", "x: http://a.b"])
    out = capsys.readouterr().out
    assert code == 0
    lines = out.splitlines()
    lan = next(line for line in lines if "giá bao nhiêu?" in line)
    huy = next(line for line in lines if "hello shop" in line)
    spam = next(line for line in lines if "http://a.b" in line)
    assert "HIGH" in lan
    assert "LOW" in huy
    assert "link" in spam
    # Queue order section: HIGH first, the dropped comment is not in it.
    order_start = next(i for i, line in enumerate(lines) if "hàng đợi" in line.lower())
    queue_lines = [line for line in lines[order_start + 1 :] if line.strip()]
    assert len(queue_lines) == 2
    assert "giá bao nhiêu?" in queue_lines[0]
    assert "hello shop" in queue_lines[1]


def test_comments_cli_argument_without_author(capsys):
    code = comments_cli.main(["chất liệu gì vậy?"])
    out = capsys.readouterr().out
    assert code == 0
    assert "MEDIUM" in out

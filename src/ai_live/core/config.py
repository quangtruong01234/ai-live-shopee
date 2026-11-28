"""Settings read from environment variables and `.env` (001 research R3).

`.env.example` is the reference list of variables and defaults.
"""

from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Annotated, Any, Literal
from urllib.parse import urlsplit

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    PrivateAttr,
    SecretStr,
    ValidationInfo,
    field_validator,
    model_validator,
)
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

_CHAIN_LABEL = re.compile(r"[a-z0-9_-]{1,24}")
_CHAIN_PLATFORM = re.compile(r"[a-z0-9_-]{1,32}")
_LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})
# The `.env.example` value before 006; still accepted as `meet` so an existing `.env` keeps working (ADR-058).
_LEGACY_OUTPUT_MODE = "webrtc"
# LIVETALKING_URL: the fork has no auth, so the app only ever talks to one on this machine (data-model §1).
_FORK_HOSTS = frozenset({"127.0.0.1", "localhost"})
_CUSTOMER_ID_RE = re.compile(r"[a-z0-9_-]{1,64}")
# Where the AI label may sit; the fork accepts the same names (vendor/livetalking/ailive_ext/label.py, ADR-076).
# `top-center` is the Meet demo default: one large line (ADR-090). `shopee-top` (ADR-085) is for Shopee via OBS:
# centred just below the band the Shopee app's title covers, wrapped into two lines.
AI_LABEL_POSITIONS = (
    "shopee-top",
    "top-center",
    "top-left",
    "top-right",
    "bottom-center",
    "bottom-left",
    "bottom-right",
)
AI_LABEL_DEFAULT_POSITION = "top-center"


class ChainEntryConfig(BaseModel):
    """One entry of `LLM_CHAIN` (feature 008, data-model §1, ADR-037).

    Only per-field checks live here. Checks that need the whole chain or the other settings (empty chain, `auto` model,
    loopback without `platform`, unknown `key_env`, empty key, duplicate label, forbidden `params`, total timeout) are
    done by `ChainReplyEngine.from_settings()`, so their messages can name the entry position (contracts/config.md §3).
    """

    model_config = ConfigDict(extra="forbid")

    label: str
    base_url: str
    model: str
    key_env: str
    first_sentence_timeout_s: float = Field(gt=0)
    platform: str | None = None
    params: dict[str, Any] = Field(default_factory=dict)

    # Set by `Settings` from the order in LLM_CHAIN; 0 means the entry was built outside a Settings object.
    _position: int = PrivateAttr(default=0)

    @field_validator("label")
    @classmethod
    def _label_format(cls, value: str) -> str:
        if not _CHAIN_LABEL.fullmatch(value):
            raise ValueError(f'nhãn "{value}" không hợp lệ: cần 1–24 ký tự a-z, 0-9, "_" hoặc "-"')
        return value

    @field_validator("base_url")
    @classmethod
    def _base_url_http(cls, value: str) -> str:
        url = value.strip()
        if not url.lower().startswith(("http://", "https://")) or not urlsplit(url).hostname:
            raise ValueError(f'base_url "{value}" phải bắt đầu bằng http:// hoặc https:// và có tên máy')
        # Stored without the trailing "/" so path joins ("{base_url}/models") never double it.
        return url.rstrip("/")

    @field_validator("platform")
    @classmethod
    def _platform_format(cls, value: str | None) -> str | None:
        if value is not None and not _CHAIN_PLATFORM.fullmatch(value):
            raise ValueError(f'platform "{value}" không hợp lệ: cần 1–32 ký tự a-z, 0-9, "_" hoặc "-"')
        return value

    @property
    def position(self) -> int:
        """1-based place in the chain."""
        return self._position

    @property
    def local(self) -> bool:
        """True when `base_url` points at this machine (the local key gateway, ADR-034)."""
        return urlsplit(self.base_url).hostname in _LOOPBACK_HOSTS


# contracts/config.md §2 (ADR-035 order, trimmed by ADR-040, Gemini appended by ADR-073).
# `.env.example` carries the same chain as one-line JSON.
# ADR-040: gpt-oss-120b failed SC-001 at T055; SEA-LION waits 2.5 s so a timed-out opening stays within 5 s.
DEFAULT_LLM_CHAIN: tuple[dict[str, Any], ...] = (
    {
        "label": "sealion",
        "base_url": "http://127.0.0.1:3001/v1",
        "model": "gemma-sea-lion-v4-27b",
        "key_env": "FREELLMAPI_KEY",
        "platform": "cloudflare",
        "first_sentence_timeout_s": 2.5,
    },
    {
        "label": "qwen",
        "base_url": "https://api.groq.com/openai/v1",
        "model": "qwen/qwen3.8-27b",
        "key_env": "GROQ_API_KEY",
        "first_sentence_timeout_s": 2.0,
        "params": {"reasoning_effort": "none"},
    },
    # ADR-073: last resort only, it is fast on average but stalls about one turn in ten.
    {
        "label": "gemini",
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai",
        "model": "models/gemini-3.5-flash-lite",
        "key_env": "GEMINI_API_KEY",
        "first_sentence_timeout_s": 2.0,
        "params": {"reasoning_effort": "low"},
    },
)


def _default_llm_chain() -> list[ChainEntryConfig]:
    return [ChainEntryConfig.model_validate(entry) for entry in DEFAULT_LLM_CHAIN]


class Settings(BaseSettings):
    """Variables used by features 001, 003, 004, 005 and 008.

    A new variable goes into `.env.example` too (test_config checks that both places match).
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        # An empty value in `.env` (e.g. GEMINI_API_KEY=) counts as unset, so the default applies.
        env_ignore_empty=True,
    )

    # ---------- General ----------
    app_env: Literal["dev", "demo", "prod"] = "dev"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    app_host: str = "127.0.0.1"
    app_port: int = 8000

    # ---------- Adapter selection ----------
    comment_source: Literal["mock", "youtube", "shopee"] = "mock"
    tts_provider: Literal["fake", "vieneu", "gemini"] = "fake"
    avatar_mode: Literal["static", "livetalking"] = "static"
    # 006: where the host is shown: `/host` shared into Meet or an OBS Browser Source on `/obs` (ADR-058). It only
    # changes what the readiness check and the watchdog require; both pages work in either mode.
    output_mode: Literal["meet", "obs"] = "meet"
    reply_engine: Literal["chain", "gemini", "fake"] = "chain"

    # ---------- LLM model chain (REPLY_ENGINE=chain, feature 008, ADR-035/037/038) ----------
    # NoDecode: the raw string reaches `_parse_llm_chain`, so bad JSON gets a message naming LLM_CHAIN.
    llm_chain: Annotated[list[ChainEntryConfig], NoDecode] = Field(default_factory=_default_llm_chain)
    llm_chain_cooldown_s: float = Field(60, ge=0)
    freellmapi_key: SecretStr | None = None
    groq_api_key: SecretStr | None = None

    # ---------- LLM (Gemini, ADR-018) ----------
    gemini_api_key: SecretStr | None = None
    llm_model: str = "gemini-3.8-flash"
    llm_thinking_level: str = "low"
    llm_max_tokens: int = Field(300, gt=0)
    llm_timeout_s: float = Field(8, gt=0)

    # ---------- TTS (feature 003, data-model §1, ADR-024/025) ----------
    tts_sample_rate: int = Field(16000, gt=0)
    tts_timeout_s: float = Field(5, gt=0)
    tts_quota_cooldown_s: float = Field(60, ge=0)
    fake_tts_delay_ms: int = Field(0, ge=0)
    vieneu_voice: str = "Thùy Dung"
    # Optional sample clip read by `vieneu_voice` itself; it pins the timbre and pronunciation (003 research R1).
    vieneu_ref_audio: Path | None = None
    vieneu_cpu_threads: int = Field(4, ge=1)
    # `validate_default` so the default `~` is expanded like a value from `.env`.
    vieneu_model_cache: Path = Field(Path("~/.cache/ai-live/hf"), validate_default=True)
    gemini_tts_model: str = "gemini-3.8-flash-tts"
    gemini_tts_voice: str = "Leda"
    # Only the path here; loading the table (and failing on a bad file) belongs to `create_tts()`.
    tts_abbreviations_path: Path = Path("data/rules/tts_abbreviations.json")

    # ---------- Avatar / LiveTalking (feature 005, data-model §1) ----------
    # The fork-only variables (LIVETALKING_BATCH_SIZE, _LIP_EVERY_N, _TRANSITION_S, _HOLD_S, _WATERMARK) are read by
    # scripts/livetalking/run.ps1, not by the app, so they have no field here.
    customer_id: str = ""
    avatar_id: str = ""
    avatar_dir: Path = Path("assets/avatars/demo_host_01")
    avatar_static_image: Path = Path("assets/avatars/demo/idle.png")
    avatar_fallback_after: int = Field(2, ge=1)
    livetalking_url: str = "http://127.0.0.1:8010"
    livetalking_python: Path = Path("vendor/livetalking/.venv/Scripts/python.exe")
    livetalking_first_frame_timeout_s: float = Field(10, gt=0)
    livetalking_reconnect_max_s: float = Field(10, gt=0)
    # 2.5 s cuts the audible gap between sentences from p95 2.98 s to under 1 s on the laptop (ADR-047).
    livetalking_lead_s: float = Field(2.5, ge=0)
    # Seconds of TTS audio held back before the fork gets a sentence: VieNeu on a busy CPU delivers chunks barely ahead
    # of playback, and every late chunk becomes a silence mid-sentence (ADR-070). 0 streams each chunk at once.
    livetalking_prebuffer_s: float = Field(0.6, ge=0)
    # wav2lip = the 005 clip library; ultralight = the character's own trained model (011, ADR-067).
    livetalking_model: Literal["wav2lip", "ultralight"] = "wav2lip"
    # Teacher of the Ultralight model: musetalk for dev (ADR-066), infinitetalk for prod (ADR-064).
    livetalking_ultralight_teacher: Literal["musetalk", "infinitetalk"] = "musetalk"
    # Shopee's AI content rules give this banner as the example of a clear AI label (ADR-065).
    ai_label_text: str = "AI-GENERATED CONTENT"
    # Bold outlined text centred at the top (ADR-076); the host page falls back to the default on an unknown value.
    ai_label_position: str = AI_LABEL_DEFAULT_POSITION
    # The spoken sentence as text on the host page. Off by default (ADR-092): it covered the host and the products.
    host_subtitles: bool = False
    renderer_ack_timeout_s: float = Field(3, gt=0)

    # ---------- Comment source ----------
    comment_max_age_s: float = Field(30, gt=0)
    comment_queue_max: int = Field(50, gt=0)
    comment_dedup_window_s: float = Field(60, ge=0)
    comment_max_chars: int = Field(300, gt=0)
    # Per-viewer limits (001 FR-027, ADR-077): more than AUTHOR_MAX comments in AUTHOR_WINDOW_S mutes the viewer for
    # AUTHOR_MUTE_S, so one fast account cannot take every reply turn.
    comment_author_max: int = Field(3, ge=1)
    comment_author_window_s: float = Field(30, gt=0)
    comment_author_mute_s: float = Field(120, ge=0)
    # A viewer is greeted back at most once in this window (001 FR-026); 0 greets every greeting.
    comment_greeting_repeat_s: float = Field(600, ge=0)
    profanity_list_path: Path = Path("data/rules/profanity.txt")
    priority_rules_path: Path = Path("data/rules/priority_keywords.json")
    greeting_rules_path: Path = Path("data/rules/greetings.json")

    # ---------- Scripted show (feature 004, plan "Biến môi trường mới") ----------
    # What the host says while nobody comments when "Bắt đầu show" sends no source (ADR-088): `loop` repeats one fixed
    # passage with invites to ask for advice; `script` is the LLM-written rotation; `verbatim` is the backup video.
    show_content: Literal["script", "verbatim", "loop"] = "loop"  # same values as core.models.CONTENT_SOURCES
    script_segment_min_sentences: int = Field(3, ge=1)
    script_segment_max_sentences: int = Field(6, ge=1)
    script_primary_share: float = Field(0.5, ge=0.5, le=0.9)
    script_fallback_after: int = Field(3, ge=1)
    script_llm_timeout_s: float = Field(10, gt=0)
    script_retry_timeout_s: float = Field(4, gt=0)
    script_history_sentences: int = Field(12, ge=0)
    script_max_tokens: int = Field(600, gt=0)
    # Only the path here; loading it (and failing on a missing file) belongs to the guard wiring.
    platform_phrases_path: Path = Path("data/rules/platform_phrases.txt")
    claim_phrases_path: Path = Path("data/rules/claim_phrases.txt")

    # ---------- Data ----------
    product_data_path: Path = Path("data/products/demo.docx")
    content_max_bytes: int = Field(5_242_880, gt=0)
    session_data_dir: Path = Path("data/sessions")

    # ---------- Live scene (feature 009, ADR-051) ----------
    scene_enabled: bool = False
    scene_dir: Path = Path("assets/scenes/demo")
    scene_subtitles: bool = False
    scene_font_path: Path | None = None

    # ---------- Background removal (feature 013, ADR-074) ----------
    # None = no model: plain-background images are still cleaned, busy ones are reported as `failed`.
    matting_model_path: Path | None = None
    # False = no model run while a show is live, so lip-sync never competes for the CPU (research R7).
    matting_during_show: bool = True

    # ---------- Background behind the host (feature 014, ADR-083) ----------
    # Empty = only the `plate` method; else the path to a hand-downloaded `.tflite` for
    # `background-prepare --method mediapipe`.
    background_segmenter_model: str = ""

    # ---------- Demo readiness (feature 007, ADR-057) ----------
    watchdog_enabled: bool = True
    watchdog_silence_s: float = Field(5, gt=0)
    watchdog_frozen_s: float = Field(3, gt=0)
    watchdog_autoskip_s: float = Field(15, gt=0)
    watchdog_audio_ack_s: float = Field(3, gt=0)
    watchdog_audio_ack_lipsync_s: float = Field(6, gt=0)
    # 006 FR-010, OUTPUT_MODE=obs only: an `/obs` source still connected but silent this long counts as lost.
    watchdog_host_stale_s: float = Field(10, gt=0)
    # Test-only knob: production keeps 0.25 s so a 5 s threshold is detected within a quarter second.
    watchdog_tick_s: float = Field(0.25, gt=0)
    readiness_min_free_gb: float = Field(5, ge=0)
    backup_video_dir: Path = Path("out/backup_video")

    # True when OUTPUT_MODE still holds the pre-006 value `webrtc`; startup logs `output_mode_legacy` once.
    _output_mode_legacy: bool = PrivateAttr(default=False)

    @field_validator("output_mode", mode="before")
    @classmethod
    def _normalize_output_mode(cls, value: Any) -> Any:
        if not isinstance(value, str):
            return value
        mode = value.strip().lower()
        if mode == _LEGACY_OUTPUT_MODE:
            return "meet"
        if mode not in ("meet", "obs"):
            # virtualcam / rtmp from the old `.env.example` are not built; failing beats silently showing nothing.
            raise ValueError(f'OUTPUT_MODE chỉ nhận meet hoặc obs (đang là "{value}")')
        return mode

    @model_validator(mode="wrap")
    @classmethod
    def _flag_legacy_output_mode(cls, data: Any, handler: Any) -> Settings:
        legacy = False
        if isinstance(data, dict):
            for key, value in data.items():
                if isinstance(key, str) and key.lower() == "output_mode" and isinstance(value, str):
                    legacy = value.strip().lower() == _LEGACY_OUTPUT_MODE
        settings = handler(data)
        settings._output_mode_legacy = legacy
        return settings

    @property
    def output_mode_legacy(self) -> bool:
        return self._output_mode_legacy

    @field_validator("ai_label_text")
    @classmethod
    def _label_not_empty(cls, value: str) -> str:
        # Article I: the AI label is always shown; an empty value fails at startup instead of silently dropping it.
        if not value.strip():
            raise ValueError("AI_LABEL_TEXT không được rỗng (nhãn AI bắt buộc hiển thị)")
        return value.strip()

    @field_validator("vieneu_voice", "gemini_tts_model", "gemini_tts_voice")
    @classmethod
    def _tts_name_not_empty(cls, value: str, info: ValidationInfo) -> str:
        if not value.strip():
            raise ValueError(f"{info.field_name.upper()} không được rỗng")
        return value.strip()

    @field_validator("vieneu_model_cache")
    @classmethod
    def _expand_model_cache(cls, value: Path) -> Path:
        return value.expanduser()

    @field_validator("vieneu_ref_audio", "scene_font_path", "matting_model_path", mode="before")
    @classmethod
    def _optional_ref_audio(cls, value: Any) -> Path | None:
        # `.env.example` ships `VIENEU_REF_AUDIO=` empty, meaning "use the preset voice as is".
        if value is None or (isinstance(value, str) and not value.strip()):
            return None
        return Path(value).expanduser()

    @field_validator("customer_id")
    @classmethod
    def _customer_id_format(cls, value: str) -> str:
        # Empty is allowed here; livetalking mode requires a value (`_lipsync_identity`).
        if value and not _CUSTOMER_ID_RE.fullmatch(value):
            raise ValueError(f'CUSTOMER_ID "{value}" không hợp lệ: cần 1–64 ký tự a-z, 0-9, "_" hoặc "-"')
        return value

    @field_validator("livetalking_url")
    @classmethod
    def _livetalking_url_loopback(cls, value: str) -> str:
        url = value.strip().rstrip("/")
        parts = urlsplit(url)
        if parts.scheme != "http" or parts.hostname not in _FORK_HOSTS:
            raise ValueError(
                f'LIVETALKING_URL "{value}" phải có dạng http://127.0.0.1:<cổng> hoặc http://localhost:<cổng> '
                "(fork LiveTalking chỉ chạy trên máy này)"
            )
        return url

    @model_validator(mode="after")
    def _lead_below_first_frame_timeout(self) -> Settings:
        # With the lead at or above the timeout, `speak` would give up on a sentence before its first frame (ADR-047).
        if self.livetalking_lead_s >= self.livetalking_first_frame_timeout_s:
            raise ValueError(
                f"LIVETALKING_LEAD_S ({self.livetalking_lead_s}) phải nhỏ hơn "
                f"LIVETALKING_FIRST_FRAME_TIMEOUT_S ({self.livetalking_first_frame_timeout_s})"
            )
        return self

    @field_validator("llm_chain", mode="before")
    @classmethod
    def _parse_llm_chain(cls, value: Any) -> Any:
        if not isinstance(value, str):
            return value
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError as exc:
            raise ValueError(
                f"LLM_CHAIN không phải JSON hợp lệ (dòng {exc.lineno}, cột {exc.colno}): {exc.msg}"
            ) from exc
        if not isinstance(parsed, list):
            raise ValueError("LLM_CHAIN phải là một mảng JSON các mục [{...}, {...}]")
        return parsed

    @field_validator("llm_chain", mode="after")
    @classmethod
    def _number_chain_entries(cls, value: list[ChainEntryConfig]) -> list[ChainEntryConfig]:
        # Copies, so an entry object shared between two Settings never carries the other chain's position.
        numbered = [entry.model_copy(deep=True) for entry in value]
        for position, entry in enumerate(numbered, start=1):
            entry._position = position
        return numbered

    @model_validator(mode="after")
    def _segment_bounds(self) -> Settings:
        # FR-003: a wrong pair stops the app at startup rather than producing segments of an impossible length.
        if self.script_segment_max_sentences < self.script_segment_min_sentences:
            raise ValueError(
                "SCRIPT_SEGMENT_MAX_SENTENCES phải lớn hơn hoặc bằng SCRIPT_SEGMENT_MIN_SENTENCES "
                f"(đang là {self.script_segment_max_sentences} < {self.script_segment_min_sentences})"
            )
        return self

    @model_validator(mode="after")
    def _watchdog_bounds(self) -> Settings:
        # The auto-skip fires after the silence warning; equal or lower would skip before anyone is warned.
        if self.watchdog_autoskip_s <= self.watchdog_silence_s:
            raise ValueError(
                "WATCHDOG_AUTOSKIP_S phải lớn hơn WATCHDOG_SILENCE_S "
                f"(đang là {self.watchdog_autoskip_s} ≤ {self.watchdog_silence_s})"
            )
        return self

    @model_validator(mode="after")
    def _lipsync_identity(self) -> Settings:
        if self.avatar_mode != "livetalking":
            return self
        # FR-004: a lip-sync character belongs to one customer, so the session must say whose it is.
        for name in ("customer_id", "avatar_id"):
            if not getattr(self, name):
                raise ValueError(f"AVATAR_MODE=livetalking cần {name.upper()} (nhân vật chỉ dùng cho đúng một khách)")
        # The fork draws the label with an ASCII-only font (research R5); a Vietnamese label would render as boxes.
        if not (self.ai_label_text.isascii() and self.ai_label_text.isprintable()):
            raise ValueError(
                f'AI_LABEL_TEXT "{self.ai_label_text}" ở AVATAR_MODE=livetalking'
                ' chỉ được dùng chữ ASCII in được (ví dụ "AI")'
            )
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()

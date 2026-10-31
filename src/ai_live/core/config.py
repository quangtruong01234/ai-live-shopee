"""Cấu hình đọc từ biến môi trường và `.env` (research R3).

`.env.example` là danh sách biến và giá trị mặc định chuẩn.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Chỉ gồm các biến feature 001 dùng.

    Thêm biến mới thì thêm cả vào `.env.example` (test_config kiểm hai nơi khớp nhau).
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        # Biến để trống trong `.env` (ví dụ GEMINI_API_KEY=) coi như chưa đặt, dùng mặc định.
        env_ignore_empty=True,
    )

    # ---------- Chung ----------
    app_env: Literal["dev", "demo", "prod"] = "dev"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    app_host: str = "127.0.0.1"
    app_port: int = 8000

    # ---------- Chọn adapter ----------
    comment_source: Literal["mock", "youtube", "shopee"] = "mock"
    tts_provider: Literal["fake", "elevenlabs", "oss"] = "fake"
    avatar_mode: Literal["static", "livetalking"] = "static"
    reply_engine: Literal["gemini", "fake"] = "gemini"

    # ---------- LLM (Gemini, ADR-018) ----------
    gemini_api_key: SecretStr | None = None
    llm_model: str = "gemini-3.8-flash"
    llm_thinking_level: str = "low"
    llm_max_tokens: int = Field(300, gt=0)
    llm_timeout_s: float = Field(8, gt=0)

    # ---------- TTS ----------
    tts_sample_rate: int = Field(16000, gt=0)
    tts_timeout_s: float = Field(5, gt=0)
    fake_tts_delay_ms: int = Field(0, ge=0)

    # ---------- Avatar ----------
    avatar_static_image: Path = Path("assets/avatars/demo/idle.png")
    ai_label_text: str = "AI"
    ai_label_position: str = "top-right"
    renderer_ack_timeout_s: float = Field(3, gt=0)

    # ---------- Nguồn comment ----------
    comment_max_age_s: float = Field(30, gt=0)
    comment_queue_max: int = Field(50, gt=0)
    comment_dedup_window_s: float = Field(60, ge=0)
    comment_max_chars: int = Field(300, gt=0)
    profanity_list_path: Path = Path("data/rules/profanity.txt")
    priority_rules_path: Path = Path("data/rules/priority_keywords.json")

    # ---------- Dữ liệu ----------
    product_data_path: Path = Path("data/products/demo.docx")
    content_max_bytes: int = Field(5_242_880, gt=0)
    session_data_dir: Path = Path("data/sessions")

    @field_validator("ai_label_text")
    @classmethod
    def _label_not_empty(cls, value: str) -> str:
        # Điều I: nhãn AI luôn hiển thị; cấu hình rỗng là lỗi khởi động, không âm thầm bỏ nhãn.
        if not value.strip():
            raise ValueError("AI_LABEL_TEXT không được rỗng (nhãn AI bắt buộc hiển thị)")
        return value.strip()


@lru_cache
def get_settings() -> Settings:
    return Settings()

"""Pick the AvatarRenderer from `AVATAR_MODE` (005, contracts/adapters.md §6)."""

from __future__ import annotations

from pathlib import Path

from ai_live.avatar.character import AvatarCharacter, load_character, validate_for_session
from ai_live.avatar.livetalking_renderer import LiveTalkingRenderer
from ai_live.avatar.static_renderer import StaticRenderer
from ai_live.avatar.switching_renderer import SwitchingRenderer
from ai_live.core.config import Settings
from ai_live.core.events import EventBus


def load_session_character(settings: Settings) -> AvatarCharacter | None:
    """The character a `livetalking` session runs with, checked against this customer; None in `static` mode.

    Raises `AvatarModeError` (Vietnamese message) so the app refuses to start with someone else's or an unprepared
    character (FR-004). Reads files: call it off the event loop.
    """
    if settings.avatar_mode != "livetalking":
        return None
    character = load_character(settings.avatar_dir)
    validate_for_session(character, settings)
    return character


def avatar_image_path(settings: Settings, character: AvatarCharacter | None) -> Path:
    """Still image for `/avatar-image`: the character's face in `livetalking` (the fallback picture too), else 001's."""
    return character.face if character is not None else settings.avatar_static_image


def create_renderer(
    settings: Settings, *, bus: EventBus, character: AvatarCharacter | None = None
) -> StaticRenderer | SwitchingRenderer:
    """`static` → `StaticRenderer` exactly as in 001/004 (FR-014); `livetalking` → lip-sync with a still-image fallback.

    `character` is the result of `load_session_character`; it is loaded here when not given.
    """
    if settings.avatar_mode == "static":
        return StaticRenderer(settings.renderer_ack_timeout_s, bus=bus)
    if character is None:
        character = load_session_character(settings)
    assert character is not None
    static = StaticRenderer(settings.renderer_ack_timeout_s, bus=bus)
    lipsync = LiveTalkingRenderer(
        settings.livetalking_url,
        static,
        first_frame_timeout_s=settings.livetalking_first_frame_timeout_s,
        ack_timeout_s=settings.renderer_ack_timeout_s,
        reconnect_max_s=settings.livetalking_reconnect_max_s,
        lead_s=settings.livetalking_lead_s,
        bus=bus,
        expected_fork_commit=character.prepare.fork_commit if character.prepare else None,
    )
    return SwitchingRenderer(
        lipsync,
        static,
        fallback_after=settings.avatar_fallback_after,
        configured="livetalking",
        bus=bus,
    )

"""Builds a character folder (005 data-model §2–§3) in a temp dir for tests.

Media files are placeholder bytes: the app only checks that they exist; decoding them is the fork's job (`prepare`).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

CHARACTER_ID = "demo_host_01"
CUSTOMER_ID = "demo_customer_01"

DEFAULT_CLIPS: list[dict[str, str]] = [
    {"clip_id": "idle_01", "file": "clips/idle_01.mp4", "kind": "idle"},
    {"clip_id": "idle_02", "file": "clips/idle_02.mp4", "kind": "idle"},
    {"clip_id": "talk_01", "file": "clips/talk_01.mp4", "kind": "talk"},
    {"clip_id": "talk_02", "file": "clips/talk_02.mp4", "kind": "talk"},
]

READY_PREPARE: dict[str, Any] = {
    "status": "ready",
    "prepared_at": "2026-11-07T10:00:00+07:00",
    "fork_commit": "fakecommit0",
    "frame_size": [480, 832],
    "clips": {c["clip_id"]: {"frames": 121, "fps": 24.0} for c in DEFAULT_CLIPS},
    "errors": [],
}


def default_provenance(clips: list[dict[str, str]] | None = None) -> dict[str, Any]:
    """Same shape as the real `demo_host_01` file: `models` keyed by role, clip entries matched by `name`."""
    return {
        "character_id": CHARACTER_ID,
        "created_by": "operator",
        "created_at": "2026-11-05T09:00:00+07:00",
        "kind": "ai_generated_fictional_face",
        "platform": "kaggle",
        "models": {
            "face": {"repo": "org/face-model", "file": "face.safetensors", "license": "apache-2.0"},
            "video": {"repo": "org/video-model", "file": "video.safetensors", "license": "apache-2.0"},
        },
        "clips": [{"name": c["clip_id"], "type": c["kind"], "files": [c["file"]]} for c in clips or DEFAULT_CLIPS],
        "adult_fictional_confirmed": True,
    }


def make_character_dir(
    root: Path,
    *,
    character: dict[str, Any] | None = None,
    provenance: dict[str, Any] | None = None,
    write_provenance: bool = True,
    prepare: dict[str, Any] | None = None,
    skip_files: tuple[str, ...] = (),
    desk_in_image: bool | None = None,
    desk_top: float | None = None,
    hands_zone: Any = None,
) -> Path:
    """Write `root/demo_host_01/` with `character.json`, `face.png`, clips and `provenance.json`; return the folder.

    `character` overrides top-level keys of `character.json` (a value of `None` removes the key).
    `desk_in_image`, `desk_top` and `hands_zone` go into the `scene` block when given (011, 013 contracts/scene-set.md
    §2); `hands_zone` takes any value so tests can write a malformed one.
    """
    avatar_dir = root / CHARACTER_ID
    (avatar_dir / "clips").mkdir(parents=True, exist_ok=True)
    data: dict[str, Any] = {
        "schema_version": 1,
        "character_id": CHARACTER_ID,
        "customer_id": CUSTOMER_ID,
        "face": "face.png",
        "provenance": "provenance.json",
        "clips": [dict(c) for c in DEFAULT_CLIPS],
    }
    if prepare is not None:
        data["prepare"] = prepare
    for key, value in (character or {}).items():
        if value is None:
            data.pop(key, None)
        else:
            data[key] = value
    scene_keys = {"desk_in_image": desk_in_image, "desk_top": desk_top, "hands_zone": hands_zone}
    scene = {k: v for k, v in scene_keys.items() if v is not None}
    if scene:
        block = data.get("scene")
        data["scene"] = {**block, **scene} if isinstance(block, dict) else scene
    (avatar_dir / "character.json").write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    files = ["face.png", *(c["file"] for c in data.get("clips", []) if isinstance(c, dict) and "file" in c)]
    for rel in files:
        if rel in skip_files:
            continue
        path = avatar_dir / rel
        if ".." in Path(rel).parts or Path(rel).is_absolute():
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"\x89PNG\r\n" if rel.endswith(".png") else b"\x00\x00\x00\x18ftypmp42")
    if write_provenance:
        prov = provenance if provenance is not None else default_provenance(data.get("clips"))
        (avatar_dir / "provenance.json").write_text(json.dumps(prov, ensure_ascii=False, indent=2), encoding="utf-8")
    return avatar_dir


def read_character(avatar_dir: Path) -> dict[str, Any]:
    return json.loads((avatar_dir / "character.json").read_text(encoding="utf-8"))

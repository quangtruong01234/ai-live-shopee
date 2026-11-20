"""Data types of the live scene (specs/009-live-scene-layout/data-model.md).

Coordinates are pixels in the output frame; boxes are `(x1, y1, x2, y2)` with x2/y2 exclusive.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

if TYPE_CHECKING:
    from PIL.Image import Image

Box = tuple[int, int, int, int]
IssueLevel = Literal["error", "warning"]
LayerName = Literal["base", "subtitle"]
ArtSource = Literal["kit", "upload"]

DEFAULT_WIDTH = 480
DEFAULT_HEIGHT = 832
# Space kept clear under the lowest face box: mouth crops are not pixel-exact and a product touching the chin reads
# as covering the face (FR-006).
FACE_MARGIN_PX = 8
# The fork checks keep-out boxes grown by this much (contracts/fork-protocol.md §2); the app punches the same area.
KEEP_OUT_PAD_PX = 4
WATERMARK_BOX: Box = (0, 0, 90, 30)

DEFAULT_DESK_COLOR = (0x8B, 0x5E, 0x3C)
DEFAULT_ACCENT_COLOR = (0xE8, 0x57, 0x3C)

# Limits on any image file the app opens: a scene file (009) or an upload (012).
MAX_IMAGE_BYTES = 10 * 1024 * 1024
MAX_IMAGE_SIDE = 4000

ALLOWED_EDITS = frozenset(
    {
        "remove_background",
        "crop",
        "resize",
        "brightness",
        "contrast",
        "white_balance",
        "shadow",
        "rotate_straighten",
    }
)
DESK_SOURCES = frozenset({"ai_generated", "own_photo", "licensed", "drawn"})
# Codes that only warn; any other code is an error and makes `check` exit 1 (data-model "SceneIssue").
WARNING_CODES = frozenset(
    {
        "missing_image",
        "overflow",
        "missing_desk",
        "placeholder",
        "orphan_image",
        "layout_keep_out",
        "unknown_key",
        "missing_scene_json",
    }
)


def grow(box: Box, pad: int) -> Box:
    x1, y1, x2, y2 = box
    return x1 - pad, y1 - pad, x2 + pad, y2 + pad


def intersects(a: Box, b: Box) -> bool:
    return a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]


@dataclass(frozen=True)
class SceneIssue:
    level: IssueLevel
    code: str
    message: str
    product_id: str | None = None

    @classmethod
    def of(cls, code: str, message: str, product_id: str | None = None) -> SceneIssue:
        return cls("warning" if code in WARNING_CODES else "error", code, message, product_id)

    def to_json(self) -> dict[str, Any]:
        return {"level": self.level, "code": self.code, "message": self.message, "product_id": self.product_id}


@dataclass(frozen=True)
class KeepOut:
    name: str
    box: Box


@dataclass(frozen=True)
class FrameGeometry:
    width: int = DEFAULT_WIDTH
    height: int = DEFAULT_HEIGHT
    face_bottom: int = round(DEFAULT_HEIGHT * 0.45)
    keep_out: tuple[KeepOut, ...] = ()
    source: Literal["estimate", "fork"] = "estimate"

    @property
    def face_zone(self) -> Box:
        return 0, 0, self.width, self.face_bottom + FACE_MARGIN_PX

    def keep_out_boxes(self) -> list[Box]:
        """Label and watermark boxes, grown as the fork grows them."""
        return [grow(k.box, KEEP_OUT_PAD_PX) for k in self.keep_out]

    def same_frame(self, other: FrameGeometry) -> bool:
        """Equal for layout purposes (the source alone does not need a redraw)."""
        return (self.width, self.height, self.face_bottom, self.keep_out) == (
            other.width,
            other.height,
            other.face_bottom,
            other.keep_out,
        )

    def to_json(self) -> dict[str, Any]:
        return {"width": self.width, "height": self.height, "face_bottom": self.face_bottom, "source": self.source}


@dataclass(frozen=True)
class LayoutParams:
    desk_top: float = 0.76
    max_slots: int = 5
    highlight_scale: float = 1.3
    show_promotion: bool = True


@dataclass(frozen=True)
class ProvenanceRecord:
    original: str | None
    edits: tuple[str, ...] = ()
    placeholder: bool = False


@dataclass(frozen=True)
class Provenance:
    customer_id: str | None
    desk_source: str | None
    products: dict[str, ProvenanceRecord] = field(default_factory=dict)


@dataclass(frozen=True, eq=False)
class ProductArt:
    product_id: str
    path: Path
    image: Image  # RGBA, cropped to its alpha > 0 area
    placeholder: bool = False
    # 012: which file the live desk shows, so the control page can tell the operator (data-model §3).
    source: ArtSource = "kit"
    version_id: str | None = None


@dataclass(frozen=True, eq=False)
class SceneSet:
    root: Path
    scene_id: str
    customer_id: str | None = None
    desk: Image | None = None
    desk_color: tuple[int, int, int] = DEFAULT_DESK_COLOR
    accent_color: tuple[int, int, int] = DEFAULT_ACCENT_COLOR
    layout: LayoutParams = field(default_factory=LayoutParams)
    art: dict[str, ProductArt] = field(default_factory=dict)
    provenance: Provenance | None = None
    issues: tuple[SceneIssue, ...] = ()

    @property
    def has_errors(self) -> bool:
        return any(i.level == "error" for i in self.issues)

    @property
    def blocked(self) -> bool:
        """Never draw another customer's scene (constitution Article I, CLAUDE.md constraint 3)."""
        return any(i.code in ("customer_mismatch", "missing_dir") for i in self.issues)


@dataclass(frozen=True)
class CardText:
    name_lines: tuple[str, ...]
    price_lines: tuple[str, ...]
    promotion_lines: tuple[str, ...] = ()
    name_size: int = 15
    price_size: int = 19
    promo_size: int = 13

    @property
    def price(self) -> str:
        return " ".join(self.price_lines)


@dataclass(frozen=True)
class Slot:
    product_id: str
    x_center: int
    width: int
    art_box: Box | None
    card_box: Box
    highlighted: bool = False
    primary: bool = False


@dataclass(frozen=True)
class SceneLayout:
    slots: tuple[Slot, ...]
    overflow: tuple[str, ...]
    desk_box: Box
    subtitle_box: Box
    issues: tuple[SceneIssue, ...] = ()

    @property
    def drawable(self) -> bool:
        return not any(i.code == "layout_keep_out" and i.level == "error" for i in self.issues)

    def slot(self, product_id: str) -> Slot | None:
        return next((s for s in self.slots if s.product_id == product_id), None)


@dataclass(frozen=True, eq=False)
class SceneLayer:
    name: LayerName
    x: int
    y: int
    image: Image | None  # RGBA cropped to its content; None clears the layer
    # The same image as PNG, encoded off the event loop by whoever drew it; the fork link sends these bytes.
    png: bytes | None = None

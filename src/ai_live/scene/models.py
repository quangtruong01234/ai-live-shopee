"""Data types of the live scene (specs/009-live-scene-layout/data-model.md).

Coordinates are pixels in the output frame; boxes are `(x1, y1, x2, y2)` with x2/y2 exclusive.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

if TYPE_CHECKING:
    from PIL.Image import Image

    from ai_live.scene.shop_photo import ShopPhoto

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
        "art_too_wide",  # 012 T071, FR-004a
        "unknown_key",
        "missing_scene_json",
        # 013 (data-model §10)
        "hands_zone_missing",
        "art_has_background",
        "matting_model_missing",
        "card_no_room",
        "cards_ignored",
        "layout_clamped",
        "no_room",  # a product with no free place on its side of the desk (research R1)
        "bad_derived_from",  # an upload version whose `derived_from` names no version (contracts/scene-set.md §3)
        # 013 FR-027, FR-028 (ADR-079)
        "art_low_resolution",
        "sticker_no_price",
        "sticker_no_room",
        # 013 FR-031, FR-032 (ADR-095)
        "price_tag_no_room",
        "promo_banner_no_room",
        # 014 data-model §1
        "background_clamped",
        "background_unknown_key",
        "background_as_is",  # FR-009a exception, ADR-102
    }
)
LayoutMode = Literal["rows", "realistic", "showcase"]
BackgroundStyle = Literal["goc", "ke_hang", "bang_shop", "anh_shop"]
CardsMode = Literal["none", "one", "all"]


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
    # Where the host's hands move (013 research R2). Products stay out of it, but it is never punched: only the
    # realistic layout reads it.
    hands_zone: Box | None = None

    @property
    def face_zone(self) -> Box:
        return 0, 0, self.width, self.face_bottom + FACE_MARGIN_PX

    def keep_out_boxes(self) -> list[Box]:
        """Label and watermark boxes, grown as the fork grows them."""
        return [grow(k.box, KEEP_OUT_PAD_PX) for k in self.keep_out]

    def same_frame(self, other: FrameGeometry) -> bool:
        """Equal for layout purposes (the source alone does not need a redraw)."""
        return (self.width, self.height, self.face_bottom, self.keep_out, self.hands_zone) == (
            other.width,
            other.height,
            other.face_bottom,
            other.keep_out,
            other.hands_zone,
        )

    def with_hands_zone(self, fractions: tuple[float, float, float, float] | None) -> FrameGeometry:
        """This frame with the hands zone given as frame fractions (the character's `scene.hands_zone`)."""
        if fractions is None:
            return replace(self, hands_zone=None)
        x1, y1, x2, y2 = fractions
        w, h = self.width, self.height
        return replace(self, hands_zone=(round(x1 * w), round(y1 * h), round(x2 * w), round(y2 * h)))

    def to_json(self) -> dict[str, Any]:
        return {"width": self.width, "height": self.height, "face_bottom": self.face_bottom, "source": self.source}


@dataclass(frozen=True)
class BackgroundConfig:
    """The `background` block of `scene.json` (014 data-model §1). `goc` keeps the original room behind the host."""

    style: BackgroundStyle = "goc"
    softness_px: float = 1.5
    brightness: float = 0.95
    max_items: int = 12
    # FR-009a exception (ADR-102), `anh_shop` only: the OBS layer scene already shows this photo sharp under the
    # host, so the fork gets it unblurred and ungraded; a blurred, brightened copy would not match the layer around it.
    as_is: bool = False


@dataclass(frozen=True)
class LayoutParams:
    desk_top: float = 0.76
    max_slots: int = 5
    highlight_scale: float = 1.3
    show_promotion: bool = True
    # 013 data-model §1. The defaults are the 009 behaviour; the loader picks the realistic defaults.
    mode: LayoutMode = "rows"
    cards: CardsMode = "all"
    brightness: float = 1.0
    # 013 FR-026, FR-027: only the showcase layout reads these.
    riser: bool = False
    sticker: bool = False
    # 014 FR-019, ADR-087: the showcase cluster stands clear of the Shopee app's comments and chat bar.
    avoid_app_overlay: bool = False
    # 013 FR-030 to FR-032 (ADR-095), showcase only: stock groups, a price tag per product, the promotions strip.
    stock: bool = False
    price_tags: bool = False
    promo_banner: bool = False


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
    # 013 FR-018: no transparent pixel at all, so the picture still has its background and looks pasted on.
    opaque: bool = False
    # 013 FR-030 (ADR-095): the stock group the showcase desk shows instead of `image`; None = one unit.
    stock: Image | None = None

    @property
    def desk_image(self) -> Image:
        """The picture the desk shows: the stock group when there is one. Shelves and thumbnails keep `image`."""
        return self.image if self.stock is None else self.stock


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
    background: BackgroundConfig = field(default_factory=BackgroundConfig)
    # 014 FR-009: read only when the background style is `anh_shop`.
    shop_photo: ShopPhoto | None = None

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
    card_box: Box | None  # None = no card for this product (013: cards none/one, card_no_room)
    highlighted: bool = False
    primary: bool = False
    station: str | None = None  # 013 realistic: the desk station name; None in rows
    shadow_box: Box | None = None  # 013 realistic: the area the soft shadow covers; rows draws no shadow


@dataclass(frozen=True)
class Sticker:
    """The round price sticker on the main product (013 FR-027). `text` is the catalog price, verbatim."""

    box: Box
    text: str
    product_id: str


@dataclass(frozen=True)
class PriceTag:
    """A small tag at a product's foot with its catalog price, verbatim (013 FR-031)."""

    box: Box
    text: str
    product_id: str


@dataclass(frozen=True)
class PromoBanner:
    """The strip on the desk front listing the placed products' promotions, verbatim and whole (013 FR-032).

    `box` is the most room the strip may take; each line is (product name, one promotion).
    """

    box: Box
    lines: tuple[tuple[str, str], ...]


@dataclass(frozen=True)
class SceneLayout:
    slots: tuple[Slot, ...]
    overflow: tuple[str, ...]
    desk_box: Box
    subtitle_box: Box
    issues: tuple[SceneIssue, ...] = ()
    mode: LayoutMode = "rows"
    # Product ids in paint order (realistic: far to near). Empty = slot order, the highlighted product last (009).
    draw_order: tuple[str, ...] = ()
    # 013 showcase (FR-026, FR-027): the white riser under the main product and the price sticker; None when off.
    riser_box: Box | None = None
    sticker: Sticker | None = None
    # 013 FR-031, FR-032 (ADR-095): empty / None when off or when there is no room.
    price_tags: tuple[PriceTag, ...] = ()
    promo_banner: PromoBanner | None = None

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

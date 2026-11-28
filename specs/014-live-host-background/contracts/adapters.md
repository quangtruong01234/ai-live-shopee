# Hợp đồng: Protocol và module phía app (014)

## 1. `BackgroundSink` (Protocol tuỳ chọn, `src/ai_live/core/protocols.py`)

```python
@dataclass(frozen=True)
class ForkBackgroundStatus:
    status: Literal["valid", "missing", "mismatch"]
    reason: str | None
    frames: int
    width: int
    height: int
    method: str | None
    reviewed: bool | None


@runtime_checkable
class BackgroundSink(Protocol):
    """A renderer whose fork can composite a backdrop under the host (014 fork-protocol §3)."""

    def set_scene_background(self, plate_png: bytes | None) -> None: ...
    def add_background_status_listener(self, callback: Callable[[ForkBackgroundStatus | None], None]) -> None: ...
```

- `LiveTalkingRenderer` cài: nhớ ảnh nền cuối cùng, gửi `scene_background` sau mỗi `hello` và mỗi lần ảnh nền đổi; báo
  `ForkBackgroundStatus` (hoặc `None` khi `hello` không có `background`) cho listener. Lỗi `background_rejected` / `background_failed`
  báo qua listener với cùng `status` và `reason` là `rejected:<message>` / `failed:<message>`.
- `SwitchingRenderer` chuyển tiếp xuống renderer lip-sync nếu nó cài.
- `StaticRenderer` không cài: lõi kiểm bằng `isinstance`, rơi về với lý do `avatar_static`.

## 2. `src/ai_live/scene/backdrop.py`

```python
@dataclass(frozen=True)
class BackdropResult:
    png: bytes | None           # RGB PNG, exactly (width, height)
    items: tuple[str, ...]      # product ids drawn on the shelves
    reason: str | None          # fallback code (data-model §5) when png is None


def render_backdrop(
    config: BackgroundConfig,
    art: Mapping[str, Image.Image],   # product id -> active cut-out (RGBA), only loaded products
    size: tuple[int, int],
    desk_top_px: int,
    light: LightStats | None,         # from the character's manifest (research R11); None = no light match
    photo: ShopPhoto | None = None,   # `anh_shop` only (data-model §3, ADR-100)
) -> BackdropResult: ...
```

- Hàm thuần (không I/O), chạy trong `asyncio.to_thread` (Điều "không chặn event loop"). Không vẽ chữ nào (test kiểm: ảnh nền không có
  điểm ảnh nào ngoài tường/kệ/LED/ảnh sản phẩm là không chứng minh được bằng test, nên test kiểm hàm không gọi `ImageDraw.text` và mọi
  ảnh sản phẩm dùng có id trong `art`).
- Cách vẽ (ADR-086, FR-018): dãy kệ phối cảnh một điểm tụ, kệ hai bên chạy vào kệ sau nhỏ và tối hơn, mọi tầng xếp kín các đơn vị
  sản phẩm lặp vòng theo `items`; khớp sáng bằng đường cong gamma (không cháy trắng). `shelf_geometry(width, height, desk_top) -> Aisle`
  công khai để test đo các đường ván và hộp kệ sau.
- `style = "ke_hang"`, `art` rỗng → `png=None`, `reason="no_product_art"`.
- `style = "bang_shop"` → `reason="style_not_available"` cho tới khi làm.
- `style = "anh_shop"` (ADR-100): `photo` là `None` → `no_shop_photo`; ảnh chưa xác nhận → lý do của ảnh (`shop_photo_unconfirmed`);
  có ảnh → cắt giữa phủ kín, mềm (ảnh `ai_generated` ít nhất 4 px), khớp sáng, `items=()`. Không cần `art`.

## 3. `BackgroundConfig` (`src/ai_live/scene/models.py`)

```python
@dataclass(frozen=True)
class BackgroundConfig:
    style: Literal["goc", "ke_hang", "bang_shop", "anh_shop"] = "goc"
    softness_px: float = 1.5
    brightness: float = 0.95
    max_items: int = 12
```

Gắn vào `SceneSet` (trường `background`), đọc bởi `load_scene_set` theo data-model §1.

## 4. `BackgroundController` (app)

Một lớp nhỏ trong `src/ai_live/scene/background.py`, do `AppContext` tạo khi `SCENE_ENABLED=true`, cạnh `SceneController`:

- Lúc khởi động: đọc `SceneSet.background`, manifest nhân vật (`assets/avatars/<id>/background/manifest.json`, chỉ để lấy `light`,
  `desk_top_px`, `reviewed`), ảnh sản phẩm đang dùng; vẽ ảnh nền một lần; gửi vào `BackgroundSink`; log `scene_background_started`.
- `status()` → dict theo data-model §5; `preview_png()` → research R13.
- Không vẽ lại khi đổi món nổi (highlight) hay phụ đề: ảnh nền chỉ phụ thuộc bộ cảnh và dữ liệu sản phẩm. Áp bộ sản phẩm mới (012
  `staging/apply`) thì vẽ lại một lần (các món trên kệ đổi theo, FR-007).

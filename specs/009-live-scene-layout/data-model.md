# Mô hình dữ liệu: 009 Bố cục cảnh live

> Kiểu Python ở `src/ai_live/scene/models.py` (dataclass bất biến, `frozen=True`, trừ chỗ ghi rõ). Tọa độ là pixel trong khung
> `(width, height)`; hộp viết `(x1, y1, x2, y2)`, x2/y2 không tính.

## SceneSet (bộ cảnh đã nạp)

| Trường | Kiểu | Ghi chú |
|--------|------|---------|
| `root` | `Path` | `SCENE_DIR` |
| `scene_id` | `str` | từ `scene.json`, mặc định tên thư mục |
| `customer_id` | `str \| None` | phải khớp `CUSTOMER_ID` khi cả hai có giá trị (Điều I) |
| `desk` | `Image (RGBA) \| None` | `None` → tô `desk_color` |
| `desk_color` | `tuple[int,int,int]` | mặc định `#8B5E3C` |
| `accent_color` | `tuple[int,int,int]` | mặc định `#E8573C` |
| `layout` | `LayoutParams` | `desk_top` 0,76 · `max_slots` 5 · `highlight_scale` 1,3 · `show_promotion` true |
| `art` | `dict[str, ProductArt]` | khóa là `product_id`; chỉ ảnh hợp lệ |
| `provenance` | `Provenance \| None` | |
| `issues` | `tuple[SceneIssue, ...]` | mọi vấn đề tìm thấy lúc nạp |

Quy tắc: nạp không bao giờ ném lỗi cho phiên; mọi lỗi thành `SceneIssue`. Thư mục không tồn tại → bộ cảnh rỗng + một issue `error`.

## ProductArt

| Trường | Kiểu | Ghi chú |
|--------|------|---------|
| `product_id` | `str` | tên file không đuôi |
| `path` | `Path` | |
| `image` | `Image (RGBA)` | đã cắt sát vùng alpha > 0 |
| `placeholder` | `bool` | theo `provenance.json` |

Ràng buộc: PNG/WebP có kênh alpha (JPEG → issue "cần nền trong suốt"); ≤ 10 MB; mỗi cạnh ≤ 4000 px; phải có ít nhất một điểm alpha > 0.

## Provenance / ProvenanceRecord

`provenance.json`, schema ở [contracts/scene-set.md](./contracts/scene-set.md).

| Trường | Kiểu | Ghi chú |
|--------|------|---------|
| `desk_source` | `"ai_generated" \| "own_photo" \| "licensed" \| "drawn" \| None` | ảnh AI chỉ được phép cho bàn |
| `products[id].original` | `str` | đường dẫn tương đối tới ảnh gốc trong `originals/` |
| `products[id].edits` | `list[str]` | chỉ trong `ALLOWED_EDITS` |
| `products[id].placeholder` | `bool` | |

`ALLOWED_EDITS = {remove_background, crop, resize, brightness, contrast, white_balance, shadow, rotate_straighten}`.

## SceneIssue

| Trường | Kiểu | Ghi chú |
|--------|------|---------|
| `level` | `"error" \| "warning"` | `error` → lệnh check trả mã 1 |
| `code` | `str` | `missing_dir`, `bad_scene_json`, `customer_mismatch`, `bad_image`, `no_alpha`, `too_large`, `missing_image`, `orphan_image`, `overflow`, `missing_provenance`, `bad_edit`, `missing_original`, `placeholder`, `ai_product`, `missing_desk`, `layout_keep_out` |
| `message` | `str` | tiếng Việt, nêu tên file / mã sản phẩm |
| `product_id` | `str \| None` | |

`missing_image`, `overflow`, `missing_desk` và `placeholder` là `warning`; các mã khác là `error`. Sản phẩm thiếu ảnh vẫn có thẻ (US1 #4).

## FrameGeometry

| Trường | Kiểu | Ghi chú |
|--------|------|---------|
| `width`, `height` | `int` | mặc định 480×832 |
| `face_bottom` | `int` | max y2 của mặt trên mọi clip; ước lượng từ `coords.pkl` hoặc 0,45·H; fork gửi giá trị thật trong `hello.scene` |
| `keep_out` | `tuple[KeepOut, ...]` | hộp nhãn "AI", watermark (tên + hộp) |
| `source` | `"estimate" \| "fork"` | |

Vùng cấm mặt: `(0, 0, width, face_bottom + FACE_MARGIN_PX)`, `FACE_MARGIN_PX = 8`.

## Slot và CardText (kết quả bố cục, thuần)

`Slot`: `product_id`, `x_center`, `width`, `art_box: Box | None`, `card_box: Box`, `highlighted: bool`, `primary: bool`.

`CardText`: `name_lines: tuple[str, ...]` (≤ 2 dòng, dòng cuối có "…" nếu cắt), `price: str` (`format_price`, khoảng giá "thấp – cao"),
`promotion_lines: tuple[str, ...]` (chỉ món nổi, khuyến mãi đầu tiên nguyên văn, ≤ 2 dòng).

`SceneLayout`: `slots`, `overflow: tuple[str, ...]` (mã sản phẩm không có chỗ), `desk_box`, `subtitle_box`.

## SceneState (trạng thái controller, có thay đổi)

| Trường | Kiểu | Ghi chú |
|--------|------|---------|
| `catalog` | `ProductCatalog \| None` | snapshot lúc `CONTENT_REPLACED` |
| `highlight` | `str \| None` | `product_id` |
| `subtitle` | `str \| None` | |
| `geometry` | `FrameGeometry` | |
| `version` | `int` | tăng mỗi lần vẽ lại lớp nền; ảnh tĩnh dùng `?v=` |
| `last_error` | `str \| None` | lỗi gần nhất (fork từ chối, vẽ lỗi) |
| `utterance_products` | `OrderedDict[str, str \| None]` | tối đa 256 mục |

## SceneLayer (gửi cho fork)

| Trường | Kiểu | Ghi chú |
|--------|------|---------|
| `name` | `"base" \| "subtitle"` | |
| `x`, `y` | `int` | góc trên trái trong khung |
| `image` | `Image (RGBA)` | đã cắt sát; `None` = xóa lớp |

Chuyển trạng thái của sản phẩm nổi (FR-015–FR-017):
`none` —(playback_started của câu kịch bản, phân đoạn có product_id có chỗ trên bàn)→ `product`;
`product` —(playback_started, phân đoạn về product_id khác có chỗ)→ `product'`;
bất kỳ —(playback_started của phân đoạn chung, hoặc phân đoạn về sản phẩm không có chỗ)→ `none`;
bất kỳ —(playback_started của câu trả lời comment, `playback_stopped`, show `paused`)→ giữ nguyên;
bất kỳ —(SHOW_STATE `idle`/`ended`, CONTENT_REPLACED làm mất sản phẩm đang nổi)→ `none`.

## LayoutParams và vùng cấm (FR-019)

`desk_top` ∈ [0,5; 0,95], `max_slots` ∈ [1; 6], `highlight_scale` ∈ [1,0; 1,6]. Ngoài khoảng → issue `bad_scene_json` và dùng giá trị
mặc định. Nếu với `face_bottom` hiện tại, đỉnh của sản phẩm nổi (đáy sản phẩm − cao × `highlight_scale`) hoặc đỉnh bàn rơi vào vùng cấm
mặt, bố cục tự thu nhỏ sản phẩm cho vừa và thêm issue `layout_keep_out` (`warning`); nếu vẫn không vừa (bàn chạm vùng mặt) thì
`error` và không vẽ lớp nền (khung ra như khi tắt cảnh, trang điều khiển báo lỗi, FR-021).

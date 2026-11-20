# Hợp đồng: bộ cảnh (`SCENE_DIR`) và lệnh kiểm

> **Bổ sung bởi 012, ADR-071:** bộ cảnh có thêm thư mục `uploads/` (ảnh tải lên từ trang điều khiển và sổ `images.json`), luật nạp
> ảnh tải lên, mã issue `missing_confirmation` / `bad_uploads` và một dòng tóm tắt ở lệnh `check`. Chi tiết ở
> [012 contracts/scene-set.md](../../012-product-image-upload/contracts/scene-set.md). Nội dung dưới đây giữ nguyên.

> Bộ cảnh là dữ liệu của khách, nằm **ngoài git** (`assets/scenes/` trong `.gitignore`). Một bộ cảnh thuộc đúng một khách.

## 1. Cấu trúc thư mục

```
<SCENE_DIR>/
├── scene.json            # tùy chọn; thiếu thì dùng mặc định (§2) + issue warning
├── desk.png              # tùy chọn; thiếu thì tô desk_color + issue `missing_desk`
├── products/<product_id>.png|.webp   # RGBA, nền trong suốt, tên file = product_id trong file dữ liệu
├── originals/            # ảnh gốc khách gửi (bất kỳ định dạng)
└── provenance.json       # hồ sơ nguồn gốc (§3)
```

## 2. `scene.json` (schema_version 1)

```json
{
  "schema_version": 1,
  "scene_id": "demo",
  "customer_id": "demo_customer_01",
  "desk": "desk.png",
  "desk_color": "#8B5E3C",
  "accent_color": "#E8573C",
  "products_dir": "products",
  "provenance": "provenance.json",
  "layout": {"desk_top": 0.76, "max_slots": 5, "highlight_scale": 1.3, "show_promotion": true}
}
```

- Mọi khóa đều tùy chọn; khóa lạ bị bỏ qua kèm issue `warning`.
- `customer_id` khác `CUSTOMER_ID` (khi cả hai có giá trị) → issue `error` `customer_mismatch` và **không vẽ cảnh** (Điều I: bộ cảnh của
  khách này không bao giờ hiện cho khách khác).
- Màu dạng `#RRGGBB`. Đường dẫn tương đối với `SCENE_DIR`, không được thoát ra ngoài (`..` → issue `error`).

## 3. `provenance.json` (schema_version 1)

```json
{
  "schema_version": 1,
  "customer_id": "demo_customer_01",
  "desk": {"source": "drawn", "tool": "scripts/make_demo_scene.py", "license": "own", "created": "2026-11-13", "notes": ""},
  "products": {
    "sp_chinh_01": {
      "original": "originals/sp_chinh_01.jpg",
      "received_from": "khách (Zalo)",
      "received_at": "2026-11-13",
      "edits": ["remove_background", "crop", "resize"],
      "placeholder": false
    }
  }
}
```

- `desk.source` ∈ `ai_generated | own_photo | licensed | drawn`. Ảnh AI chỉ được cho bàn.
- `products.<id>.edits` ⊆ `remove_background, crop, resize, brightness, contrast, white_balance, shadow, rotate_straighten`. Thao tác khác
  (ví dụ `inpaint`, `retouch_label`, `ai_generated`) → issue `error` `bad_edit` / `ai_product`.
- `original` phải tồn tại trong `SCENE_DIR` (trừ khi `placeholder: true`) → nếu không, `error` `missing_original`.
- Ảnh sản phẩm không có mục trong `provenance.json` → `error` `missing_provenance` (ảnh vẫn hiện để không chặn phiên, FR-003, nhưng lệnh
  kiểm trả mã 1).
- `placeholder: true` → `warning` `placeholder` ("ảnh mẫu, thay bằng ảnh thật của khách trước phiên thật").

## 4. Ảnh

- Sản phẩm: PNG hoặc WebP có kênh alpha, ≤ 10 MB, mỗi cạnh ≤ 4000 px, có ít nhất một điểm alpha > 0. JPEG/không alpha → `no_alpha`
  ("cần nền trong suốt"). Không mở được → `bad_image`.
- Bàn: PNG/JPEG/WebP bất kỳ, ≤ 10 MB; được phủ ngang dải bàn (scale theo chiều rộng, cắt phần thừa phía dưới).
- Ảnh trong `products/` không trùng `product_id` nào trong file dữ liệu đang nạp → `warning` `orphan_image` (không hiện).
- Sản phẩm không có ảnh → `warning` `missing_image` (thẻ vẫn hiện).
- Nhiều sản phẩm hơn `max_slots` → `warning` `overflow` liệt kê mã sản phẩm không có chỗ.

## 5. Lệnh

```bash
uv run python -m ai_live.scene check [SCENE_DIR] [--content PATH]      # in bảng vấn đề; mã 1 nếu có `error`
uv run python -m ai_live.scene preview [SCENE_DIR] --out FILE.png [--content PATH] [--highlight PRODUCT_ID] [--subtitle TEXT]
```

- `--content` mặc định là `PRODUCT_DATA_PATH` trong `.env`. `preview` ghép ảnh tĩnh của nhân vật (`AVATAR_STATIC_IMAGE` hoặc ảnh của
  `LIVETALKING_CHARACTER`) với cảnh và vẽ khung các vùng cấm bằng nét đứt nếu có `--debug-zones`.
- Đầu ra in tiếng Việt, mỗi dòng: `MỨC  mã  nội dung`.

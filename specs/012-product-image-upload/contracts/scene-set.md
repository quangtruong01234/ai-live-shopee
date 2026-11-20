# Hợp đồng: phần thêm vào bộ cảnh 009 (`SCENE_DIR/uploads/`)

> Bổ sung cho [009 contracts/scene-set.md](../../009-live-scene-layout/contracts/scene-set.md). Mọi điều 009 không nhắc lại ở đây giữ
> nguyên. Đề xuất ghi thành ADR-071. `uploads/` là dữ liệu của khách, ngoài git như cả bộ cảnh.

## 1. Cấu trúc thư mục

```
<SCENE_DIR>/
├── scene.json, desk.png, products/, originals/, provenance.json   # như 009, không đổi
└── uploads/                        # MỚI, do app ghi; không sửa tay khi app đang chạy
    ├── images.json                 # sổ ảnh (§2)
    └── <product_id>/
        └── <version_id>.png        # PNG RGBA đã chuẩn hóa, cạnh dài ≤ 1280 px
```

- App tạo `uploads/` khi tải ảnh đầu tiên. Không có `uploads/` hay `images.json` = mọi sản phẩm theo luật 009 (bộ cảnh 009 cũ chạy y như
  trước).
- Ghi `images.json` luôn qua file tạm cùng thư mục + `os.replace` (không bao giờ có sổ ghi dở).
- Đường dẫn chỉ ghép từ `product_id` khớp `^[a-z0-9]+(-[a-z0-9]+)*$` (≤ 120 ký tự) và `version_id` khớp `^[0-9a-f]{12}$`; kết quả phải nằm
  trong `uploads/`.

## 2. `uploads/images.json` (schema_version 1)

Lược đồ đầy đủ ở [data-model.md](../data-model.md) §2. Tóm tắt: `customer_id`, và cho từng `product_id`: `active`
(`"<version_id>"` | `null` = đã gỡ | `"kit"` = ảnh 009), `history`, `updated_at`, `versions` (mỗi phiên bản: `uploaded_at`,
`source_name`, `width`, `height`, `has_alpha`, `bytes`, `applied_at`, `rights_confirmed_at`).

## 3. Luật nạp (thay đổi trong `load_scene_set`)

Với mỗi `product_id` của catalog đang nạp:

| Trạng thái trong sổ | Ảnh dùng | Kiểm nguồn gốc | Issue |
|---------------------|----------|----------------|-------|
| không có mục, hoặc `"kit"` | `products/<id>.png\|.webp` (009) | `provenance.json` + `original` (009) | như 009 |
| `"<vid>"`, file có, `rights_confirmed_at` có | `uploads/<id>/<vid>.png` | **không** đòi `provenance.json` hay `original` | không |
| `"<vid>"`, thiếu `rights_confirmed_at` | không ảnh (chỉ thẻ) | | `error` `missing_confirmation` |
| `"<vid>"`, file thiếu / hỏng / không có trong `versions` | không ảnh | | `error` `bad_uploads` |
| `null` | không ảnh | | `warning` `missing_image` ("đã gỡ ảnh") |

- Ảnh tải lên đã chuẩn hóa nên luôn có alpha; luật `no_alpha` của 009 không áp cho chúng (ảnh JPEG đã thành RGBA đặc lúc tải, research R2).
  Bộ nạp vẫn cắt theo vùng alpha và thu ≤ 640 px như 009 (`_load_art`).
- File trong `products/` của một sản phẩm mà sổ đang chọn ảnh tải lên hay đã gỡ: không vẽ, không báo `orphan_image` (sản phẩm vẫn có trong
  catalog), không kiểm `provenance.json` cho nó.
- `ProductArt.source` = `"upload"` và `version_id` đặt cho ảnh tải lên; `"kit"` cho ảnh 009.
- `images.json` không đọc được, không phải JSON object, hay `schema_version` ≠ 1 → `error` `bad_uploads`, bỏ qua cả sổ (mọi sản phẩm theo
  luật 009).
- `images.json.customer_id` khác `CUSTOMER_ID` (cả hai khác rỗng) → `error` `customer_mismatch`, bộ cảnh không dùng được (như `scene.json`,
  009 §2, Điều I).
- Thư mục `uploads/<id>/` của sản phẩm không có trong catalog: không đọc, không báo (ảnh được giữ cho lần sau, FR-014).

## 4. Mã issue mới

| Mã | Mức | Câu (tiếng Việt) | Kiểm trước demo (007 `check_scene`) |
|----|-----|------------------|-------------------------------------|
| `missing_confirmation` | error | "Ảnh tải lên của sản phẩm {id} chưa có xác nhận quyền dùng: không hiện" | **LỖI** (như `placeholder`) |
| `bad_uploads` | error | "uploads/images.json hỏng: …" hoặc "Ảnh tải lên {vid} của sản phẩm {id} không đọc được" | **LỖI** |

Các issue `error` khác của bộ cảnh giữ mức CẢNH BÁO ở `check_scene` như 009/007.

## 5. Lệnh `python -m ai_live.scene check`

Không đổi cú pháp. Vì dùng cùng `load_scene_set` nên ảnh tải lên được chấp nhận tự động (FR-005). Thêm một dòng tóm tắt cuối:
`Ảnh tải lên: N đang dùng, M thiếu xác nhận, K đã gỡ`. Mã thoát 1 khi có `error` như 009.

## 6. Dọn tay

Muốn bỏ hẳn ảnh tải lên của một sản phẩm: tắt app, xóa `uploads/<id>/` và mục `<id>` trong `images.json` (hoặc xóa cả `uploads/` để về bộ
cảnh 009). App không tự xóa phiên bản nào (research R9).

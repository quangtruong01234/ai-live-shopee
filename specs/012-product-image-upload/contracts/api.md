# Hợp đồng: HTTP và sự kiện của 012

> Lỗi dùng khung `ApiError` có sẵn: `{"error": "<mã>", "message": "<tiếng Việt>", "details": …}`. Mọi route chỉ trang điều khiển dùng
> (không đăng nhập, như `PUT /api/content`). `{pid}`, `{vid}` sai dạng (contracts/scene-set.md §1) → 400 `bad_id`.

## 1. Ảnh của bộ đang live (US1, US3)

### `GET /api/scene/images`

Một mục `ProductImageStatus` (data-model §4) cho mỗi sản phẩm của catalog live, theo thứ tự file; kèm thông tin chung:

```json
{
  "scene_enabled": true,
  "scene_usable": true,
  "catalog_version": "a1b2c3d4e5f6",
  "products": [
    {"product_id": "kem-chong-nang-spf50", "name": "Kem chống nắng SPF50", "is_primary": true,
     "state": "upload", "version_id": "3f9a0c1b2d4e",
     "thumb_url": "/api/scene/images/kem-chong-nang-spf50/versions/3f9a0c1b2d4e.png",
     "uploaded_at": "…", "applied_at": "…", "rights_confirmed_at": "…", "has_alpha": false, "can_revert": true,
     "issues": [], "versions": [{"version_id": "3f9a0c1b2d4e", "uploaded_at": "…", "source_name": "kem moi.jpg", "applied_at": "…"}]}
  ],
  "uploads_bytes": 1392000
}
```

Đọc được cả khi cảnh tắt (`scene_enabled: false`): trang vẫn cho xem và chuẩn bị ảnh (trường hợp biên).

### `POST /api/scene/uploads?product_id={pid}`

Thân = nội dung file ảnh thô; header `X-Filename` (tên file, mã hóa phần trăm). Kiểm và chuẩn hóa (research R2), lưu phiên bản, **không** áp.
`pid` phải có trong catalog live **hoặc** bộ chuẩn bị (404 `unknown_product`).

- 201: `{"product_id", "version_id", "reused": bool, "width", "height", "has_alpha", "warnings": ["has_background"]?, "thumb_url"}`
  (`reused` = đã có phiên bản y hệt). `has_background` khi `has_alpha=false` (FR-004).
- Lỗi: §6. Không ghi gì khi lỗi.

### `GET /api/scene/images/{pid}/versions/{vid}.png`

PNG của phiên bản (ảnh nhỏ trên trang dùng `<img>` thu nhỏ bằng CSS). 404 nếu không có. `Cache-Control: max-age=31536000, immutable`
(nội dung cố định theo `vid`).

### `GET /api/scene/images/{pid}/kit.png`

Ảnh bộ cảnh 009 của sản phẩm (đã cắt alpha, ≤ 640 px) để làm ảnh nhỏ. 404 nếu không có. `Cache-Control: no-cache`.

### `GET /api/scene/preview.png?target=live|staging&product_id={pid}&version_id={vid}`

Khung hình tĩnh xem trước (research R4, data-model §5): mặt host + bàn + thẻ, sản phẩm `pid` dùng ảnh `vid`, giữ sản phẩm đang nổi.
`target=staging` vẽ catalog và ảnh của bộ chuẩn bị (pid, vid tùy chọn). Không đổi live.

- 200 `image/png`, `Cache-Control: no-store`.
- 409 `scene_disabled` (cảnh tắt), 409 `scene_unusable` (bộ cảnh không dùng được), 404 `unknown_product` / `unknown_version` /
  `no_staging`.

### `POST /api/scene/images/{pid}/apply`

```json
{"version_id": "3f9a0c1b2d4e", "rights_confirmed": true}
```

- `rights_confirmed` khác `true` → 422 `rights_not_confirmed` ("Chưa đánh dấu xác nhận quyền dùng ảnh"), không đổi gì (FR-006).
- `pid` không có trong catalog live → 404 `unknown_product` (trường hợp biên "file bị thay lúc xem trước").
- Bộ cảnh của khách khác → 409 `customer_mismatch` (FR-007).
- Ghi sổ lỗi → 500 `save_failed`, live giữ ảnh cũ (FR-011).
- 200:

```json
{"product_id": "…", "active": "3f9a0c1b2d4e", "applied_at": "…", "rights_confirmed_at": "…",
 "scene_version": 42, "to_frame_ms": 310.5, "scene_enabled": true}
```

`to_frame_ms` = từ lúc nhận request tới lúc lớp `base` mới đã giao cho renderer; `null` khi cảnh tắt (sổ vẫn ghi, ảnh dùng khi bật cảnh).

### `POST /api/scene/images/{pid}/revert`

Thân rỗng. 200 như `apply` (`active` có thể là vid, `null` hay `"kit"`). 409 `nothing_to_revert` khi không có ảnh trước (FR-016).

### `POST /api/scene/images/{pid}/remove`

```json
{"confirm": true}
```

`confirm` khác `true` → 422 `remove_not_confirmed` (FR-017). 409 `already_removed`. 200 như `apply` với `active: null`.

## 2. Bộ chuẩn bị (US2, US4)

### `POST /api/content/staging`

Thân = file `.docx` thô, `X-Filename`, giới hạn `CONTENT_MAX_BYTES` như `PUT /api/content`. Đọc bằng `store.parse` (không nạp). Lỗi file:
cùng mã và chi tiết như `PUT /api/content` (400 `content_invalid`, 413 `content_too_large`…). Đã có bộ chuẩn bị → thay bộ cũ.

200 = `StagedSetView`:

```json
{
  "staged_id": "b71c2e",
  "source_name": "bo-hang-moi.docx",
  "created_at": "…",
  "live_catalog_version": "a1b2c3d4e5f6",
  "live_changed": false,
  "products": [
    {"product_id": "son-moi-a", "name": "Son môi A", "is_primary": true,
     "image": "staged", "version_id": "c0ffee123456", "thumb_url": "…", "has_alpha": true,
     "rights_confirmed_at": "…"},
    {"product_id": "kem-chong-nang-spf50", "name": "…", "is_primary": false, "image": "reused_upload", "version_id": "3f9a0c1b2d4e",
     "thumb_url": "…"},
    {"product_id": "nuoc-hoa-b", "name": "…", "is_primary": false, "image": "missing", "version_id": null, "thumb_url": null}
  ],
  "missing": ["nuoc-hoa-b"]
}
```

`image` ∈ `staged | reused_upload | reused_kit | removed | missing` (data-model §6).

### `GET /api/content/staging`

200 `StagedSetView`; 404 `no_staging`.

### `DELETE /api/content/staging`

Hủy bộ chuẩn bị (FR-015a). 204; 404 `no_staging`. Không xóa ảnh nào.

### `POST /api/content/staging/images/{pid}`

```json
{"staged_id": "b71c2e", "version_id": "c0ffee123456", "rights_confirmed": true}
```

Gán ảnh (đã tải bằng `POST /api/scene/uploads`) cho một món của bộ chuẩn bị. `version_id: null` bỏ gán. 422 `rights_not_confirmed`,
404 `unknown_product` (không có trong bộ chuẩn bị), 404 `unknown_version`, 409 `staging_changed` (`staged_id` không khớp). 200 `StagedSetView`.
Không đổi live.

### `POST /api/content/staging/apply`

```json
{"staged_id": "b71c2e", "confirm_missing": false}
```

- Còn món `missing`/`removed` và `confirm_missing` khác `true` → 409 `missing_images`, `details: [{"product_id", "name"}]`; không đổi gì
  (FR-015 hỏi lại).
- 409 `staging_changed`, 409 `customer_mismatch`, 500 `save_failed` (live giữ bộ cũ, bộ chuẩn bị giữ nguyên).
- 200:

```json
{"version": 8, "products": [{"id": "…", "name": "…", "is_primary": true}], "images_written": 2, "missing_images": 1,
 "scene_version": 43, "to_frame_ms": 420.0}
```

Thân trả về có `version`, `products` giống `PUT /api/content` để trang dùng chung hàm cập nhật. Thành công thì bộ chuẩn bị bị bỏ.

## 3. Chi tiết sản phẩm (US4)

### `GET /api/content/products/{pid}` · `GET /api/content/staging/products/{pid}`

200 `ProductDetail` (data-model §8), `source` = `live` / `staging`. 404 `unknown_product`, 404 `no_staging`.

## 4. Thay đổi ở endpoint có sẵn

- `GET /api/state` (và tin `state` đầu tiên của `/ws/control`):
  - thêm `spoken`: list `SpokenSentence` (data-model §7), mới nhất trước, tối đa 100 (FR-021);
  - thêm `staging`: `{"staged_id", "source_name", "missing": int}` hoặc `null`, để trang mở lại biết đang có bộ chuẩn bị.
- `GET /api/scene`: mỗi mục `images` (009) thêm `source` (`kit` | `upload`) và `version_id`.
- Sự kiện bus `sentence` (từ show kịch bản): thêm khóa `topic` (giá trị `Topic` của 004). Khóa cũ giữ nguyên.

## 5. Sự kiện bus `scene` mới (qua `/ws/control`)

```json
{"type": "scene", "kind": "image_changed", "product_id": "kem-chong-nang-spf50", "action": "apply", "active": "3f9a0c1b2d4e",
 "scene_version": 42}
{"type": "scene", "kind": "staging", "action": "created|updated|cancelled|applied", "staged_id": "b71c2e"}
```

Mọi tab trang điều khiển tải lại `GET /api/scene/images` (và `GET /api/content/staging` với `kind: staging`) khi nhận (trường hợp biên
"hai tab"). Trang chèn câu vào "AI vừa nói" khi nhận `sentence` có `segment_id`.

## 6. Mã lỗi tải ảnh (`POST /api/scene/uploads`)

| HTTP | `error` | `message` |
|------|---------|-----------|
| 413 | `too_large` | "Ảnh quá lớn (tối đa 10 MB)" |
| 400 | `bad_image` | "Không đọc được file ảnh (hỏng hoặc không phải ảnh)" |
| 415 | `bad_format` | "Chỉ nhận ảnh PNG, WebP hoặc JPEG" |
| 400 | `too_big` | "Ảnh quá to: cạnh dài {n} điểm ảnh (tối đa 4000)" |
| 400 | `animated` | "Không nhận ảnh động" |
| 400 | `empty` | "Ảnh gần như trong suốt hoàn toàn, trên live sẽ không thấy gì" |
| 404 | `unknown_product` | "Không có sản phẩm {pid} trong file đang nạp hay bộ chuẩn bị" |
| 409 | `customer_mismatch` | "Bộ cảnh không thuộc khách của phiên này" |
| 500 | `save_failed` | "Không lưu được ảnh: {lý do}" |

## 7. Log JSONL

`scene_image_uploaded`, `scene_image_rejected`, `scene_image_changed`, `scene_staging_applied` (trường ở data-model §9), `scene_preview`
(`target`, `product_id`, `render_ms`). Cùng logger cảnh của 009; `scene_loaded` có thêm `uploads` (số ảnh tải lên đang dùng).

## 8. So với `docs/ARCHITECTURE.md` §3

Không thêm hay đổi Protocol adapter nào. `ProductStore.parse` đã có. `AvatarRenderer.set_scene_layer` không đổi. Bộ nạp cảnh và
`SceneController` không phải adapter; thay đổi của chúng ghi ở contracts/scene-set.md và plan.md.

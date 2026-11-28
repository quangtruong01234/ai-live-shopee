# Mô hình dữ liệu: 012-product-image-upload

Thời điểm lưu dạng ISO 8601 UTC có mili giây (`now_iso()` của `app/context.py`). `pid` = `product_id` (slug của tên sản phẩm, 001);
`vid` = `version_id`.

## 1. `UploadedImage` (một phiên bản ảnh trên đĩa)

File `SCENE_DIR/uploads/<pid>/<vid>.png`, PNG RGBA đã chuẩn hóa (research R2).

| Trường (trong sổ) | Kiểu | Quy tắc |
|-------------------|------|---------|
| `vid` | str | `^[0-9a-f]{12}$`, 12 ký tự hex đầu của SHA-256 của PNG đã chuẩn hóa; trùng thì dùng lại phiên bản cũ |
| `uploaded_at` | str | lúc tải lần đầu |
| `source_name` | str | tên file người dùng chọn (chỉ để hiện, không làm đường dẫn), ≤ 200 ký tự |
| `width`, `height` | int | cỡ sau chuẩn hóa, cạnh dài ≤ 1280 |
| `has_alpha` | bool | ảnh gốc có vùng trong suốt; `false` → trang cảnh báo "ảnh còn nền" (FR-004) |
| `bytes` | int | cỡ file PNG |
| `applied_at` | str \| null | lần áp gần nhất lên live (cả áp lẻ, áp bộ mới, hoàn tác về nó) |
| `rights_confirmed_at` | str \| null | lần xác nhận quyền dùng gần nhất (FR-006); null = chưa từng xác nhận, không được lên live |

**Kiểm khi tải lên** (theo thứ tự, mã lỗi ở contracts/api.md §6): `too_large` (> 10 MB) → `bad_image` (không mở được) → `bad_format`
(ngoài PNG/WEBP/JPEG/MPO) → `too_big` (cạnh > 4000 px) → `animated` (nhiều khung, trừ MPO) → `empty` (điểm có alpha > 0 dưới 1%).

## 2. `ImageManifest` (`SCENE_DIR/uploads/images.json`)

```json
{
  "schema_version": 1,
  "customer_id": "shop-a",
  "products": {
    "kem-chong-nang-spf50": {
      "active": "3f9a0c1b2d4e",
      "history": ["kit", "a1b2c3d4e5f6"],
      "updated_at": "2026-11-20T09:12:03.120Z",
      "versions": {
        "a1b2c3d4e5f6": {"uploaded_at": "…", "source_name": "kem-cu.png", "width": 820, "height": 1240, "has_alpha": true,
                         "bytes": 412000, "applied_at": "…", "rights_confirmed_at": "…"},
        "3f9a0c1b2d4e": {"uploaded_at": "…", "source_name": "kem moi.jpg", "width": 1280, "height": 960, "has_alpha": false,
                         "bytes": 980000, "applied_at": "…", "rights_confirmed_at": "…"}
      }
    }
  }
}
```

| Trường | Kiểu | Quy tắc |
|--------|------|---------|
| `schema_version` | int | `1`; khác → lỗi `bad_uploads`, bỏ qua cả sổ |
| `customer_id` | str | ghi một lần khi tạo sổ, lấy `CUSTOMER_ID`; khác khách của phiên (cả hai khác rỗng) → `customer_mismatch` (bộ cảnh không dùng được, như 009) |
| `products` | map pid → `ProductImageEntry` | khóa khớp biểu thức pid (research R12); khóa sai → `bad_uploads` cho mục đó, bỏ qua mục |

### `ProductImageEntry`

| Trường | Kiểu | Quy tắc |
|--------|------|---------|
| `active` | `ImageState` | trạng thái đang dùng |
| `history` | list[`ImageState`] | trạng thái trước, cũ trước mới sau, tối đa 20 (bỏ phần tử cũ nhất) |
| `updated_at` | str | lần đổi `active` gần nhất; dùng để so với gán của bộ chuẩn bị (research R7) |
| `versions` | map vid → `UploadedImage` | mọi phiên bản từng tải cho pid này, kể cả chưa áp; không xóa tự động (R9) |

### `ImageState`

| Giá trị | Nghĩa | Bộ nạp cảnh làm gì |
|---------|-------|--------------------|
| `"<vid>"` | dùng phiên bản tải lên | đọc `uploads/<pid>/<vid>.png`; cần `rights_confirmed_at` của phiên bản đó, thiếu → lỗi `missing_confirmation`, không vẽ ảnh; file thiếu/hỏng → lỗi `bad_uploads`, không vẽ ảnh |
| `null` | đã gỡ ảnh | không ảnh, chỉ thẻ; cảnh báo `missing_image` ("đã gỡ ảnh") |
| `"kit"` | ảnh bộ cảnh 009 | luật 009 nguyên vẹn (`products/`, `provenance.json`) |

Sản phẩm không có mục trong sổ = `"kit"`.

### Chuyển trạng thái (một sản phẩm)

```
            áp vid (xác nhận)                  gỡ (xác nhận)
  kit ───────────────────────────► vid ─────────────────────────► null
   ▲   push(kit)                    │  push(vid)                   │
   │                                │ áp vid2: push(vid)           │ áp vid: push(null)
   │                                ▼                              │
   └──────── về ảnh trước: active = pop(history) ◄────────────────┘
```

- **Áp** (`apply`, cả áp lẻ, áp bộ mới): `vid` phải có trong `versions`; `rights_confirmed` bắt buộc → ghi `rights_confirmed_at`,
  `applied_at`; `history.push(active)` (bỏ qua nếu `active` đã bằng `vid`, áp lại chỉ cập nhật thời điểm); `active = vid`.
- **Gỡ** (`remove`): `history.push(active)`; `active = null`. `active` đã là `null` → 409 `already_removed`.
- **Về ảnh trước** (`revert`): `history` rỗng → 409 `nothing_to_revert`; ngược lại `active = history.pop()`; nếu là vid thì cập nhật
  `applied_at` (đã có `rights_confirmed_at` từ lần áp trước).
- Mỗi thao tác đặt `updated_at` và ghi cả sổ một lần (file tạm + `os.replace`).

## 3. Thay đổi ở mô hình cảnh 009 (`scene/models.py`)

- `ProductArt` thêm `source: Literal["kit", "upload"] = "kit"` và `version_id: str | None = None`: trang biết ảnh đang live là ảnh nào.
- Mã lỗi mới (mức `error`, không vào `WARNING_CODES`): `missing_confirmation`, `bad_uploads`.
- `customer_mismatch` nay cũng có thể đến từ `images.json`.

## 4. `ProductImageStatus` (trả ở `GET /api/scene/images`, một mục mỗi sản phẩm)

| Trường | Kiểu | Ghi chú |
|--------|------|---------|
| `product_id`, `name`, `is_primary` | | theo thứ tự catalog live (FR-001) |
| `state` | `"upload"` \| `"kit"` \| `"removed"` \| `"none"` | `none` = không có ảnh nào dùng được |
| `version_id` | str \| null | khi `state = upload` |
| `thumb_url` | str \| null | `/api/scene/images/<pid>/versions/<vid>.png` hoặc `/api/scene/images/<pid>/kit.png` |
| `uploaded_at`, `applied_at`, `rights_confirmed_at` | str \| null | FR-018 |
| `has_alpha` | bool \| null | |
| `can_revert` | bool | `history` khác rỗng |
| `issues` | list[`SceneIssue`] | vấn đề của bộ nạp cho pid này (vd `missing_confirmation`) và của bố cục lần vẽ gần nhất (vd `art_too_wide`, thêm bởi T071) |
| `versions` | list | `{version_id, uploaded_at, source_name, applied_at}`, mới trước; cho phần chi tiết |

## 5. `PreviewRequest` (tham số của `GET /api/scene/preview.png`)

| Trường | Kiểu | Quy tắc |
|--------|------|---------|
| `target` | `"live"` \| `"staging"` | mặc định `live` |
| `product_id` | str | `live`: phải có trong catalog live; `staging`: trong bộ chuẩn bị. Không bắt buộc với `staging` (vẽ cả bộ) |
| `version_id` | str | phiên bản có trong sổ của pid; bỏ trống = xem trước trạng thái hiện tại |

Không lưu gì; ảnh trả về là PNG khung hình đầy đủ (mặt host + lớp base, không phụ đề).

## 6. `StagedSet` (bộ chuẩn bị, trong bộ nhớ, tối đa 1)

| Trường | Kiểu | Quy tắc |
|--------|------|---------|
| `staged_id` | str | uuid4 ngắn; mọi thao tác gửi kèm để không áp nhầm bộ đã bị thay (409 `staging_changed`) |
| `catalog` | `ProductCatalog` | kết quả `store.parse` (không `install`); file lỗi → không tạo bộ, trả lỗi như `PUT /api/content` |
| `source_name` | str | tên file |
| `created_at` | str | |
| `live_catalog_version` | str | `catalog.version` live lúc tạo (12 ký tự hex, hash của file nội dung); khác hiện tại → trang ghi "bộ đang live đã đổi" |
| `assignments` | map pid → `StagedAssignment` | chỉ pid có trong `catalog` |

### `StagedAssignment`

| Trường | Kiểu | Quy tắc |
|--------|------|---------|
| `version_id` | str | có trong sổ của pid |
| `rights_confirmed_at` | str | bắt buộc khi gán (FR-013 dùng xác nhận FR-006) |
| `assigned_at` | str | so với `ProductImageEntry.updated_at` khi áp bộ: mới hơn mới thắng |

### Trạng thái ảnh mỗi món của bộ chuẩn bị (`StagedProduct.image`)

Thứ tự ưu tiên: `staged` (có gán) > `reused_upload` (sổ có `active` là vid, kể cả pid không có trong catalog live, FR-014) >
`reused_kit` (`active` là `kit`/không có mục và có file `products/` dùng được) > `removed` (sổ ghi đã gỡ) > `missing`.
`missing` và `removed` đều tính là "thiếu ảnh" khi áp (FR-015 hỏi lại).

### Vòng đời

```
(không có) ──POST staging──► open ──gán ảnh (0..n)──► open ──apply ok──► (không có)
                               │                         │
                               └──DELETE / POST mới────► (không có, bộ cũ bị thay)
                                                         └──apply lỗi──► open (giữ nguyên, live giữ bộ cũ)
```

Tạo bộ mới khi đã có một bộ: thay bộ cũ (trang hỏi lại trước khi gửi). Tắt app: mất bộ chuẩn bị, ảnh đã tải còn.

## 7. `SpokenSentence` (vòng đệm "AI vừa nói", trong bộ nhớ, tối đa 100)

| Trường | Kiểu | Nguồn |
|--------|------|-------|
| `ts` | str | lúc nhận sự kiện `sentence` |
| `utterance_id`, `segment_id` | str | payload `sentence` |
| `text` | str | payload |
| `product_id` | str \| null | payload |
| `product_name` | str \| null | tra catalog live lúc nhận |
| `topic` | str \| null | payload, khóa mới (`Topic` của 004: `opening`, `intro`, `highlights`, `specs`, `price`, `promotion`, `faq`, `call_to_action`, `closing`); null với bản phát sự kiện cũ |

Chỉ nhận sự kiện có `segment_id`. Xóa khi show chuyển sang `running` từ `idle` hoặc `ended`. Trong `/api/state`: `spoken`, mới nhất trước.

## 8. `ProductDetail` (US4)

Nguyên văn từ `Product` (001): `id`, `name`, `is_primary`, `description`, `intro`, `price` (int \| null), `variants`
(`[{name, price}]`, theo đúng trường của `Variant`), `specs` (`[[khóa, giá trị]]`), `faq` (`[[hỏi, đáp]]`), `promotions`, `forbidden_claims`.
Không có `link`. Thêm `source`: `"live"` hoặc `"staging"` (FR-023 ghi rõ bộ chuẩn bị).

## 9. `ImageChange` (nhật ký, log JSONL, không lưu riêng)

Sự kiện log `scene_image_changed`: `action` (`apply` | `revert` | `remove`), `product_id`, `version_id` (null khi gỡ), `from_state`,
`to_state`, `result` (`ok` | mã lỗi), `to_frame_ms` (null nếu cảnh tắt hay lỗi), `scene_version`.
Sự kiện log `scene_staging_applied`: `staged_id`, `products`, `missing_images`, `images_written`, `result`, `to_frame_ms`.
Sự kiện log `scene_image_uploaded`: `product_id`, `version_id`, `reused` (trùng phiên bản cũ), `has_alpha`, `width`, `height`, `bytes`,
`ms`. Từ chối: `scene_image_rejected` với `code`. Không log tên file người dùng ở mức INFO (chỉ trong sổ).

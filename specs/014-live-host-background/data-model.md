# Mô hình dữ liệu (Phase 1): Nền sau người dẫn giống phòng live của shop

- **Feature ID:** `014-live-host-background` · **Ngày:** 2026-11-24 · **Plan:** [plan.md](./plan.md)
- Thực thể lấy từ "Thực thể chính" của spec: **Cấu hình nền**, **Phần chuẩn bị nền của nhân vật**, **Ảnh shop**; thêm hai thực thể lúc chạy:
  **Trạng thái nền** (app) và **Bộ nền đã nạp** (fork).
- Mọi file dưới đây nằm trong `assets/` (gitignored, dữ liệu khách và hình người mẫu). Không đưa vào git.

---

## 1. Cấu hình nền (`scene.json` → khối `background`)

Thuộc một bộ cảnh (`assets/scenes/<scene_id>/scene.json`), nên thuộc đúng một khách (`customer_id` của bộ cảnh, FR-013). Khối tuỳ chọn;
thiếu khối = `style: "goc"` (bộ cảnh cũ không đổi, FR-001).

| Trường | Kiểu | Mặc định | Ràng buộc | FR |
|---|---|---|---|---|
| `style` | `"goc" \| "ke_hang" \| "bang_shop" \| "anh_shop"` | `"goc"` | giá trị khác → lỗi `bad_scene_json` của 009, dùng `"goc"` | FR-001 |
| `softness_px` | float | `1.5` (ADR-086; trước là 3.0) | 0–8, ngoài khoảng thì kẹp và log `background_clamped`; 0 = tắt làm mềm | FR-006 |
| `brightness` | float | `0.95` | 0,8–1,1, kẹp như trên | FR-006 |
| `as_is` | bool | `false` | chỉ `anh_shop`: `true` = gửi ảnh shop đã cắt phủ khung, không làm mờ (kể cả mức tối thiểu ảnh AI) và không chỉnh sáng/cân bằng trắng; luôn kèm cảnh báo `background_as_is`. Chỉ cho cảnh lớp OBS demo (ADR-102), không cho Shopee. Không phải bool → `bad_scene_json`, dùng `false` | FR-009a |
| `max_items` | int | `12` | 1–24, kẹp như trên: độ dài vòng sản phẩm lặp lại trên kệ (lặp vòng các món đang có ảnh); kệ luôn xếp kín mọi tầng (ADR-086) | FR-007 |

- Thêm `"background"` vào `_SCENE_KEYS` của `src/ai_live/scene/loader.py`. Khoá lạ trong khối → cảnh báo `background_unknown_key`, bỏ qua.
- `"bang_shop"` (US3) đọc được nhưng **chưa có bộ vẽ**: chọn nó thì rơi về `"goc"` với lý do `style_not_available`.
  `"anh_shop"` đã có bộ vẽ (ADR-100, §3).
- Không có trường tên shop ở đây (spec: tên shop đọc từ file dữ liệu, §4).

Ví dụ:
```json
"background": { "style": "ke_hang", "softness_px": 1.5, "brightness": 0.95 }
```

## 2. Phần chuẩn bị nền của nhân vật

Thư mục `assets/avatars/<character_id>/background/` (cạnh `character.json`), do công cụ chuẩn bị ghi (contracts/prepare-cli.md). Gắn với
đúng một nhân vật (nằm trong thư mục của nhân vật đó) và đúng các khung fork sẽ phát (dấu vân từng khung).

```
assets/avatars/<character_id>/background/
├── manifest.json
├── masks/<fingerprint>.png      # ảnh xám 8 bit, cỡ đúng bằng khung; 0 = nền, 255 = người, giữa = viền mềm
├── preview_frame.png            # khung 0 của vòng lặp (khung gốc), cho ảnh xem trước (R13)
└── review.jpg                   # tờ so sánh: khung gốc | mặt nạ | ghép thử trên nền xám, mọi khung, để người duyệt
```

### `manifest.json`

| Trường | Kiểu | Ghi chú |
|---|---|---|
| `schema_version` | int | `1` |
| `character_id` | str | phải bằng `character.json` `character_id` |
| `method` | `"plate" \| "mediapipe"` | R3 |
| `model` | object \| null | `{"file": "selfie_multiclass_256x256.tflite", "sha256": "..."}` khi `method = "mediapipe"` |
| `width`, `height` | int | cỡ khung, ví dụ 480, 832 |
| `desk_top_px` | int | mép bàn đã dùng (R6) |
| `room_areas` | list | thêm 2026-11-25 (ADR-094): các đa giác `[[x, y], ...]` người vận hành khoanh quanh khe phòng cũ (`--room-area`); `[]` khi không có. Fork không đọc trường này; lệnh app dùng lại nó ở lần chuẩn bị sau |
| `frames` | list | mỗi phần tử `{"fingerprint": "8 hex", "mask": "masks/<fp>.png", "sources": ["cycle:demo_host_02__w2l_musetalk:0", ...]}` |
| `light` | object | `{"person_luma", "person_rb", "room_luma", "room_rb"}`: trung bình trên mọi khung (R11) |
| `leak` | object | kết quả đo lọt R12 lúc chuẩn bị: `{"frames_flagged": int, "max_blob_px": int}` |
| `created_at` | str ISO 8601 | |
| `reviewed` | bool | `false` khi vừa tạo; người duyệt xem `review.jpg` rồi đặt `true` bằng `--mark-reviewed` |
| `reviewed_by`, `reviewed_at` | str \| null | |

- `fingerprint` = `zlib.crc32` của bytes khung BGR đã giải mã, viết 8 ký tự hex (R7). Khung giống nhau ở hai thư mục avatar dùng chung
  một mặt nạ (`sources` liệt kê cả hai).

### Trạng thái (fork tính lúc nạp avatar, báo trong `hello.background`)

| Trạng thái | Khi nào | Live hiện |
|---|---|---|
| `valid` | có manifest, mọi khung đang phát có mặt nạ đúng cỡ | nền mới (nếu app bật) |
| `missing` | không có `background/manifest.json` | phòng gốc, lý do `not_prepared` |
| `mismatch` | thiếu mặt nạ cho ≥ 1 khung, sai cỡ, `character_id` khác, file mặt nạ hỏng | phòng gốc, lý do cụ thể (`frame_not_prepared:<n>`, `size_mismatch`, `character_mismatch`, `mask_unreadable:<file>`) |

- `reviewed = false` **không** chặn dùng nền, nhưng readiness báo `warn` "mặt nạ chưa được duyệt bằng mắt" (SC-001/002 cần mắt người).
- Chuyển trạng thái: chạy lại công cụ chuẩn bị ghi đè cả thư mục (ghi vào thư mục tạm rồi đổi tên, để không còn bộ nửa cũ nửa mới); làm lại
  đoạn lặp → dấu vân đổi → `mismatch` cho tới khi chuẩn bị lại.

## 3. Ảnh shop (US3, làm 2026-11-28 theo ADR-100)

`assets/scenes/<scene_id>/background/shop_photo.<png|jpg|webp>` + `shop_photo.json` (module `src/ai_live/scene/shop_photo.py`):

| Trường | Kiểu | Ghi chú |
|---|---|---|
| `sha256` | str | của file ảnh |
| `confirmed_by` | str | người xác nhận quyền dùng (như 012) |
| `confirmed_at` | str ISO 8601 | |
| `source` | `"photo" \| "ai_generated"` | ảnh chụp thật hay ảnh do AI tạo (FR-009a) |
| `original_name` | str | tên file gốc lúc đưa vào, chỉ để tra cứu |

- Không có ảnh → `no_shop_photo`. Không có `shop_photo.json` hợp lệ, thiếu trường, `source` lạ hoặc sha256 không khớp → không dùng,
  lý do `shop_photo_unconfirmed` (US3 kịch bản 4, FR-009). Sửa hay thay file ảnh thì phải xác nhận lại.
- Đưa ảnh vào bằng lệnh `uv run python -m ai_live.scene shop-photo <thư mục cảnh> <ảnh> --confirmed-by "<tên>" [--ai-generated]`.
  Ảnh tối đa 10 MB, mỗi cạnh tối đa 4000 px (như ảnh sản phẩm). Chưa có nút trên trang điều khiển (T064 còn mở).
- Cách vẽ: phủ kín khung bằng cắt giữa giữ tỷ lệ (không kéo méo), làm mềm `softness_px`, khớp ánh sáng như kệ hàng. Ảnh
  `ai_generated` luôn mềm ít nhất `AI_MIN_SOFTNESS_PX = 4.0` px trên khung rộng 480 px để chữ và logo AI vẽ ra chỉ còn mảng màu.
- Không cần ảnh sản phẩm: kiểu này không xếp sản phẩm lên kệ (`items` rỗng).

## 4. Tên shop (US3, P4, chưa làm)

`ProductCatalog.shop_name: str | None`, đọc từ một dòng "Tên shop: …" ở phần đầu file dữ liệu sản phẩm (trước tiêu đề sản phẩm đầu tiên).
Không có → `None`. Chỉ dùng cho kiểu `bang_shop`; LLM và guard không đổi. Trang điều khiển chỉ hiển thị, không sửa (FR-008).

## 5. Trạng thái nền (app, lúc chạy)

Do `BackgroundController` (`src/ai_live/scene/background.py`, contracts/adapters.md §4) giữ, trả qua `GET /api/scene/background` và gộp vào `GET /api/scene`.

| Trường | Kiểu | Ghi chú |
|---|---|---|
| `style` | str | kiểu đã cấu hình |
| `active` | bool | nền mới đang hiện trên khung live |
| `mask_status` | `"valid" \| "missing" \| "mismatch" \| "unknown"` | `unknown` khi fork chưa `hello` hoặc ở chế độ `static` |
| `fallback_reason` | str \| null | lý do hiện phòng gốc (bảng dưới) |
| `reviewed` | bool \| null | từ manifest |
| `items` | list[str] | id các món bày trên kệ (FR-007) |
| `changed_at` | str ISO 8601 | lần trạng thái đổi gần nhất (khởi động, `hello` mới, lỗi từ fork, áp bộ sản phẩm mới) |

`active = style ≠ "goc" ∧ plate_ready ∧ mask_status = "valid" ∧ fork_supports_background`.

Lý do rơi về (`fallback_reason`), theo thứ tự kiểm:

| Mã | Ý nghĩa (tiếng Việt hiện trên trang) | FR |
|---|---|---|
| `style_goc` | bộ cảnh dùng phòng gốc | FR-001 |
| `scene_disabled` | cảnh live đang tắt (`SCENE_ENABLED=false`) | trường hợp biên |
| `style_not_available` | kiểu nền này chưa làm (US3) | FR-001 |
| `no_product_art` | "kệ hàng" nhưng shop chưa có ảnh sản phẩm đã bỏ nền | FR-011 |
| `no_shop_photo` / `shop_photo_unconfirmed` | "ảnh shop" nhưng chưa có ảnh, hoặc chưa xác nhận quyền dùng / sha256 không khớp (US3, ADR-100) | FR-011, FR-009 |
| `plate_failed` | vẽ ảnh nền lỗi | FR-011 |
| `avatar_static` | chế độ ảnh tĩnh, không có khung fork | R14 |
| `fork_unsupported` | fork không báo `background` trong `hello` | FR-010 |
| `not_prepared` / `mismatch:<chi tiết>` | phần chuẩn bị nền thiếu hoặc không khớp | FR-010 |
| `rejected:<chi tiết>` | fork từ chối ảnh nền (sai cỡ, quá lớn) | FR-010 |
| `failed:<chi tiết>` | fork ghép lỗi lúc phát và đã tự về phòng gốc | FR-010 |

## 6. Bộ nền đã nạp (fork, lúc chạy)

`ailive_ext/background.py`, một đối tượng cho mỗi phiên avatar:

| Trường | Ghi chú |
|---|---|
| `status`, `reason` | §2 |
| `masks` | ánh xạ `(nguồn, idx)` → mặt nạ đã tách sẵn: `bg_mask` (uint8 0/1, dùng cho `cv2.copyTo`), `edge_idx` (chỉ số phẳng), `edge_alpha` (uint16) (R8) |
| `plate` | ảnh nền BGR đúng cỡ khung, hoặc `None` |
| `failed` | bool, đặt khi ghép lỗi; xoá khi nhận ảnh nền mới |
| thống kê | thời gian ghép trung bình từ lần đọc trước → `stats.background_ms` |

Chuyển trạng thái: `plate=None` → nhận `scene_background` hợp lệ → có `plate`; nhận ảnh nền mới thay nguyên tử (gán một tham chiếu, như
`SceneState` của 009); `png_b64 = null` → `plate=None` (phòng gốc). Không có công tắc bật/tắt khi live (spec, làm rõ 2026-11-24). Ghép lỗi
ở một khung → log một lần, đặt `failed=true` (từ đó trả khung gốc), báo `background_failed` cho app, khung vẫn được đẩy ra (live không
dừng).

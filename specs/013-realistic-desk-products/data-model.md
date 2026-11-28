# Mô hình dữ liệu: Sản phẩm đứng trên bàn như đồ thật

- **Feature:** `013-realistic-desk-products` · **Ngày:** 2026-11-22 · **Plan:** [plan.md](./plan.md)
- Kiểu ghi theo Python. Tỷ lệ khung là số thực 0–1 theo chiều rộng (x) hoặc chiều cao (y) của khung gửi đi. `Box` = `(x1, y1, x2, y2)`
  điểm ảnh, như 009.

## 1. `LayoutParams` (mở rộng 009, `scene/models.py`)

| Trường | Kiểu | Mặc định | Giới hạn | Ghi chú |
|--------|------|----------|----------|---------|
| `desk_top` | float | 0,76 | 0,55–0,92 | 009, không đổi. Nhân vật có `desk_in_image` thì dùng `desk_top` của nhân vật (011) |
| `max_slots` | int | 5 (`showcase`: 4) | 1–7 (`rows`), 1–5 (`realistic`), 1–4 (`showcase`) | Vượt giới hạn của mode → dùng giới hạn + cảnh báo `layout_clamped` (mới) |
| `highlight_scale` | float | 1,3 (`rows`), 1,08 (`realistic`, `showcase`) | 1,0–1,6 (`rows`), 1,00–1,10 (`realistic`, `showcase`) | Mặc định theo `mode` khi file không ghi; ngoài giới hạn → kẹp + `layout_clamped` |
| `show_promotion` | bool | true | | 009, không đổi |
| `mode` | `Literal["rows", "realistic", "showcase"]` | `"rows"` | | MỚI. Giá trị lạ → `"rows"` + lỗi `bad_layout` (cảnh vẫn vẽ kiểu hàng). `showcase`: FR-025, ADR-079 |
| `cards` | `Literal["none", "one", "all"]` | `"none"` (`realistic`, `showcase`), `"all"` (`rows`) | | MỚI. `rows` + khác `"all"` → `"all"` + `cards_ignored` |
| `brightness` | float | 1,0 | 0,85–1,10 | MỚI. Nhân đều R, G, B của ảnh sản phẩm; ngoài giới hạn → kẹp + `layout_clamped` |
| `riser` | bool | false | | MỚI (FR-026). Bục tròn trắng dưới món chính; chỉ `showcase` đọc, mode khác bỏ qua |
| `sticker` | bool | false | | MỚI (FR-027). Sticker giá tròn ở góc trên món chính; chỉ `showcase` đọc |
| `avoid_app_overlay` | bool | false | | Thêm bởi 014 FR-019, ADR-087. Cả cụm `showcase` co chiều sâu để ảnh sản phẩm đứng trên vùng bình luận và ô chat của app Shopee; chỉ `showcase` đọc |

Luật nạp: khóa tùy chọn; bộ cảnh không có `mode` chạy y như 009 (FR-001, US1 #6). `bad_layout` là lỗi mức `error` theo luật 009 (mã không nằm
trong `WARNING_CODES`), nhưng không chặn vẽ: cảnh lùi về `rows`. Đã chốt (T013): giữ luật 009, `scene check` thoát mã 1 khi có `bad_layout`, để người vận hành sửa `scene.json` trước demo.

## 2. `CharacterScene` (mở rộng 011, `avatar/character.py`)

`Character` hiện có `desk_in_image: bool`, `desk_top: float | None`. Thêm:

| Trường | Kiểu | Mặc định | Kiểm |
|--------|------|----------|------|
| `hands_zone` | `tuple[float, float, float, float] \| None` | `None` | 4 số 0–1, `x1 < x2`, `y1 < y2`; sai → `PrepareError("bad_character", "scene.hands_zone …")` như `desk_top` |

`None` khi dùng cách bày `realistic` → vùng mặc định `[0.30, desk_top − 0.10, 0.70, 1.0]` (kẹp về 0–1) + cảnh báo `hands_zone_missing`.
`desk_top` của nhân vật dùng `desk_top` của `scene.json` khi nhân vật không khai.

## 3. `FrameGeometry` (mở rộng 009)

| Trường | Kiểu | Ghi chú |
|--------|------|---------|
| `hands_zone` | `Box \| None` | MỚI, điểm ảnh, tính từ tỷ lệ × (W, H) của khung (ước lượng hoặc từ fork). Không vào `keep_out_boxes()` và không bị `punch` (research R2); chỉ bố cục `realistic` đọc |

`same_frame()` thêm `hands_zone` vào phép so (đổi vùng tay → vẽ lại).

## 4. `DeskStation` (hằng số trong `scene/layout.py`)

| Trường | Kiểu | Ghi chú |
|--------|------|---------|
| `name` | `str` | `P`, `S1`…`S4` |
| `side` | `Literal["left", "right"]` | theo người xem |
| `x_frac` | float | vị trí tâm ngang trong khoảng đặt của bên đó (0 = sát mép ngoài… theo hướng trái → phải của khung) |
| `depth` | float | đáy = `desk_y + depth × (H − desk_y)`; nhỏ hơn = xa hơn |
| `height_frac` | float | chiều cao mục tiêu theo H |

Bảng giá trị: research R1. Món thứ i theo `slot_order` (009) vào chỗ thứ i. Luật bất biến (test): với i < j, `height_frac[i] > height_frac[j]`
và `depth[i] > depth[j]` (món sau nhỏ hơn và xa hơn, FR-004). Sau khi đặt (test): món sau thấp hơn hoặc nhỏ diện tích hơn mọi món đứng
trước nó; có thể lật cả bảng sang trái (soi gương) khi món chính ở đó được vẽ to rõ hơn (research R1).

## 5. `SceneLayout` / `Slot` (009, thêm trường)

| Trường | Kiểu | Ghi chú |
|--------|------|---------|
| `Slot.station` | `str \| None` | MỚI: tên chỗ đứng (`realistic`), `None` ở `rows` |
| `Slot.card_box` | `Box \| None` | ĐỔI (009 là `Box`): `None` = không vẽ thẻ món này (`cards = none/one`, `card_no_room`) |
| `Slot.shadow_box` | `Box \| None` | MỚI: hộp bóng hai lớp (để kiểm vùng cấm, research R3); `None` ở `rows` (không vẽ bóng) |
| `SceneLayout.mode` | `str` | MỚI: `rows` \| `realistic` \| `showcase` |
| `SceneLayout.riser_box` | `Box \| None` | MỚI (FR-026): hộp bục (mặt trên elip, thân và bóng của bục), `None` khi tắt hoặc không phải `showcase` |
| `SceneLayout.sticker` | `Sticker \| None` | MỚI (FR-027): `Sticker(box, text, product_id)`, `text` = `price_text(món chính)` |
| `SceneLayout.draw_order` | `tuple[str, ...]` | MỚI: `product_id` theo thứ tự vẽ (xa → gần ở `realistic`; 009: món nổi cuối) |

Bất biến (test, mọi món có ảnh, mọi trạng thái nổi): hộp món ∪ bóng ∪ ánh sáng ∪ thẻ không giao `face_zone`, `keep_out_boxes()`, `hands_zone`;
đáy món ∈ `[desk_y, H]`; ở `realistic` không món nào có tâm ngang trong `[hands_x1, hands_x2]`. Ở `showcase` bỏ `hands_zone` khỏi phép
kiểm (FR-025) nhưng thêm bục và sticker vào phép hợp; món chính cao ≤ 0,40 H và đứng trước (đáy thấp nhất, vẽ cuối).

## 6. `CutResult` (`scene/matting.py`)

| Trường | Kiểu | Ghi chú |
|--------|------|---------|
| `image` | `PIL.Image` RGBA \| `None` | ảnh đã bỏ nền và cắt theo hộp alpha; `None` khi `failed` |
| `method` | `Literal["already_transparent", "flat", "model"]` | cách cuối cùng đã dùng |
| `result` | `Literal["removed", "failed", "kept"]` | `kept` = ảnh đã trong suốt, không làm gì |
| `reason` | `str \| None` | câu tiếng Việt khi `failed` (vd "nền quá phức tạp, model không chắc", "chưa cài model tách nền", "đang live, bỏ nền phức tạp sau khi dừng show", "tách nền quá lâu") |
| `metrics` | `dict[str, float]` | `fg_ratio`, `border_fg_ratio`, `uncertain_ratio`, `largest_component_ratio` (R8), để log và chỉnh ngưỡng |
| `ms` | float | tổng thời gian |
| `model` | `str \| None` | tên file model nếu đã chạy model |

## 7. `BgRemoval` (lưu trong `uploads/images.json`)

```json
{"method": "flat", "result": "removed", "reason": null, "ms": 182.4, "model": null, "at": "2026-11-22T10:15:03+07:00"}
```

Giống `CutResult` trừ ảnh và chỉ số chi tiết.

## 8. Phần thêm vào `UploadedImage` (012 data-model, `uploads/images.json` → `products.<pid>.versions.<vid>`)

| Trường | Kiểu | Có ở | Ghi chú |
|--------|------|------|---------|
| `bg_removal` | `BgRemoval \| null` | ảnh tải lên và bản bỏ nền | ảnh tải lên: kết quả lần bỏ nền; bản bỏ nền: chép lại kết quả đó |
| `cutout_version` | `str \| null` | ảnh tải lên | `vid` bản bỏ nền; `null` khi `failed`/`kept` |
| `derived_from` | `str \| null` | bản bỏ nền | `vid` ảnh tải lên gốc. Phiên bản có `derived_from` không bao giờ bị bỏ nền lại |

Phiên bản cũ (012) không có ba trường này = `null`. `source_name` của bản bỏ nền = `source_name` gốc + " (đã bỏ nền)". `rights_confirmed_at`
xử lý y như 012: mỗi phiên bản xác nhận lúc áp, bản bỏ nền không thừa hưởng (cùng một ô xác nhận của 012).

## 9. Chuyển trạng thái bỏ nền (một lần tải lên)

```
tải lên ─► chuẩn hóa (012) ─┬─ has_alpha ───────────────────────────────► kept (already_transparent)
                            └─ không alpha ─► nền phẳng? ─┬─ có ─► loang ─► assess_cut ─┬─ chắc ─► removed (flat)
                                                          │                              └─ không ─┐
                                                          └─ không ────────────────────────────────┤
                                                                                                   ▼
                                       model có? ─ không ─► failed "chưa cài model tách nền"
                                         │ có
                                       đang show và MATTING_DURING_SHOW=false? ─ có ─► failed "đang live…"
                                         │ không
                                       tiến trình con (≤ 60 s) ─┬─ lỗi/hết giờ ─► failed
                                                                 └─ mặt nạ ─► assess_cut ─┬─ chắc ─► removed (model)
                                                                                          └─ không ─► failed "model không chắc"
```

`removed` → ghi bản bỏ nền thành phiên bản mới, `cutout_version` trỏ tới nó, `recommended_version` = bản bỏ nền. `failed`/`kept` →
`recommended_version` = ảnh tải lên. Không trạng thái nào tự áp lên live (012: tải lên không áp).

Tải lại ảnh y hệt (012 `reused`) và phiên bản đã có `bg_removal` → trả lại kết quả cũ, không chạy lại. Ngoại lệ: kết quả cũ là `failed` với
lý do "chưa cài model…" hoặc "đang live…" thì chạy lại (điều kiện có thể đã đổi).

## 10. Mã cảnh báo mới (`SceneIssue`, mức `warning`, thêm vào `WARNING_CODES`)

| Mã | Khi nào | Câu gợi ý (tiếng Việt) |
|----|---------|------------------------|
| `hands_zone_missing` | `realistic` và nhân vật không khai `hands_zone` | "Nhân vật chưa khai vùng tay; đang dùng vùng mặc định, kiểm lại bằng xem trước gỡ lỗi" |
| `art_has_background` | `realistic` và ảnh đang dùng của món còn nền (R10) | "Ảnh của {món} còn nền, sẽ trông như dán lên; hãy bỏ nền hoặc tải ảnh nền trong suốt" |
| `matting_model_missing` | `MATTING_MODEL_PATH` rỗng hoặc file không có | "Chưa cài model tách nền: ảnh nền phức tạp sẽ không bỏ nền được" |
| `card_no_room` | thẻ của món không có chỗ (R4) | "Không đủ chỗ cho thẻ của {món}; thẻ bị ẩn" |
| `cards_ignored` | `rows` + `cards` khác `"all"` | "Cách bày hàng luôn có thẻ; bỏ qua layout.cards" |
| `layout_clamped` | giá trị `layout` ngoài giới hạn, đã kẹp | "layout.{khóa} ngoài giới hạn, đã dùng {giá trị}" |
| `no_room` | món không còn chỗ trống bên của nó trên bàn (research R1; thêm lúc implement T012) | "Không đủ chỗ trên bàn cho {món}; món bị ẩn" |
| `bad_derived_from` | phiên bản tải lên có `derived_from` không trỏ tới phiên bản nào (contracts/scene-set.md §3; thêm lúc implement T012) | "Phiên bản ảnh {id}: derived_from không trỏ tới phiên bản nào" |
| `art_low_resolution` | ảnh nguồn thấp hơn 1,5 × chiều cao vẽ lúc món nổi (`LOW_RES_FACTOR`, FR-028), mọi cách bày; không báo khi cạnh dài ảnh đã đạt `ART_MAX_SIDE` (960 px) | "Ảnh của {món} nhỏ ({cao} px) so với cỡ vẽ ({vẽ} px), sẽ mờ trên hình; hãy tải ảnh to hơn" |
| `sticker_no_price` | `showcase` + `sticker` + món chính không có giá (giá 0) | "Món chính {món} không có giá trong file dữ liệu; không vẽ sticker giá" |
| `sticker_no_room` | sticker không có chỗ ngoài vùng cấm | "Không có chỗ cho sticker giá của {món} ngoài vùng cấm; không vẽ sticker" |

Mã có sẵn dùng lại: `art_too_wide` (ảnh quá rộng, không đủ chỗ ≥ `MIN_ART_HEIGHT`), `overflow` (nhiều món hơn chỗ). Mã lỗi mới: `bad_layout`.

## 11. Log (JSONL, logger cảnh 009)

- `scene_bg_removed`: `product_id`, `version_id`, `cutout_version`, `method`, `result`, `reason`, `ms`, `model`, `width`, `height`, và
  `fg_ratio`, `border_fg_ratio`, `uncertain_ratio` (để chỉnh ngưỡng R8).
- `scene_rendered` (009) thêm `layout_mode`, `cards`, và mỗi món `station`.

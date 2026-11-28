# Hợp đồng: phần thêm vào bộ cảnh, nhân vật và kho ảnh (013)

> Bổ sung cho [009 contracts/scene-set.md](../../009-live-scene-layout/contracts/scene-set.md) và
> [012 contracts/scene-set.md](../../012-product-image-upload/contracts/scene-set.md). Mọi khóa mới là **tùy chọn**: bộ cảnh, nhân vật và
> `images.json` cũ đọc và vẽ y như trước (FR-001, US1 #6). Không đổi `schema_version`.

## 1. `scene.json` → `layout`

```json
"layout": {
  "mode": "realistic",
  "cards": "none",
  "brightness": 1.0,
  "highlight_scale": 1.08,
  "max_slots": 5,
  "desk_top": 0.76,
  "show_promotion": true
}
```

| Khóa | Giá trị | Mặc định | Ghi chú |
|------|---------|----------|---------|
| `mode` | `"rows"` \| `"realistic"` \| `"showcase"` | `"rows"` | Giá trị lạ → issue `error` `bad_layout`, cảnh vẽ kiểu `rows` |
| `cards` | `"none"` \| `"one"` \| `"all"` | `realistic`, `showcase`: `"none"`; `rows`: `"all"` | `rows` + khác `"all"` → `warning` `cards_ignored` |
| `brightness` | số 0,85–1,10 | 1,0 | Nhân đều R, G, B; ngoài giới hạn → kẹp + `warning` `layout_clamped` |
| `highlight_scale` | `rows`: 1,0–1,6; `realistic`, `showcase`: 1,00–1,10 | `rows`: 1,3; `realistic`, `showcase`: 1,08 | Ngoài giới hạn của mode → kẹp + `layout_clamped` |
| `max_slots` | `rows`: 1–7; `realistic`: 1–5; `showcase`: 1–4 | 5 (`showcase`: 4) | |
| `riser` | bool | false | `showcase`: bục tròn trắng dưới món chính (FR-026); mode khác bỏ qua. Không phải bool → `layout_clamped` |
| `sticker` | bool | false | `showcase`: sticker giá tròn, chữ = giá từ file (FR-027). Không phải bool → `layout_clamped` |

Đổi `mode`/`cards`/`brightness` có hiệu lực khi nạp lại bộ cảnh (mở lại phiên hoặc nạp lại như 009). Không có nút đổi trên trang điều khiển
(spec: chọn theo phiên).

## 2. `character.json` → `scene`

```json
"scene": {"desk_in_image": true, "desk_top": 0.868, "hands_zone": [0.27, 0.74, 0.73, 1.0]}
```

- `hands_zone`: 4 số 0–1 theo khung (`x1, y1, x2, y2`), `x1 < x2`, `y1 < y2`. Sai → lỗi chuẩn bị `bad_character` (như `desk_top`, 011).
  Thiếu + cách bày `realistic` → vùng mặc định `[0.30, desk_top − 0.10, 0.70, 1.0]` + `warning` `hands_zone_missing`.
- Đo bằng xem trước gỡ lỗi (quickstart §2). Số trong ví dụ là minh họa; số của `demo_host_02` chốt ở task đo.

## 3. `uploads/images.json` → `products.<pid>.versions.<vid>`

```json
"3f9a0c1b2d4e": {
  "uploaded_at": "…", "source_name": "thung coca.jpg", "width": 1280, "height": 960, "has_alpha": false, "bytes": 412000,
  "applied_at": null, "rights_confirmed_at": null,
  "bg_removal": {"method": "flat", "result": "removed", "reason": null, "ms": 182.4, "model": null, "at": "…"},
  "cutout_version": "a81c55d09e2f"
},
"a81c55d09e2f": {
  "uploaded_at": "…", "source_name": "thung coca.jpg (đã bỏ nền)", "width": 1104, "height": 902, "has_alpha": true, "bytes": 388000,
  "applied_at": null, "rights_confirmed_at": null,
  "bg_removal": {"method": "flat", "result": "removed", "reason": null, "ms": 182.4, "model": null, "at": "…"},
  "derived_from": "3f9a0c1b2d4e"
}
```

- File bản bỏ nền: `uploads/<pid>/<vid_cut>.png`, `vid_cut` = 12 ký tự đầu sha256 của PNG (luật 012).
- `derived_from` phải trỏ tới một phiên bản có trong cùng sản phẩm; sai → `warning` (không phải lỗi: ảnh vẫn hiện được).
- Phiên bản thiếu `bg_removal`/`cutout_version`/`derived_from` = `null` (phiên bản 012 cũ).
- Áp dụng, về ảnh trước, gỡ, bộ chuẩn bị, xác nhận quyền dùng: luật 012 không đổi; bản bỏ nền là một `version_id` như mọi phiên bản.
- Bộ đọc phải bỏ qua khóa lạ trong phiên bản. Đã kiểm (T015): bộ đọc 012 không từ chối khóa lạ và giữ nguyên chúng khi ghi lại; vẫn
  `schema_version: 1`. `derived_from` sai → cảnh báo `bad_derived_from`.

## 4. Lệnh `python -m ai_live.scene`

- `preview [SCENE_DIR] --out PNG [--highlight PID] [--debug-zones] [--host-frame IMAGE]` (009, đã có): nhân vật lấy theo `AVATAR_DIR` như hiện nay, nay đọc
  thêm `desk_in_image`, `desk_top`, `hands_zone` của nhân vật đó để bố cục giống lúc live. `--debug-zones` (đã có, vẽ vùng cấm 009) vẽ thêm
  vạch mép bàn (xanh lá) và vùng tay (tím). `--host-frame` (thêm 2026-11-23) vẽ lên ảnh cho trước thay cho ảnh mặt của nhân vật, ví dụ
  khung đầu `full_imgs/00000000.png` của avatar fork, để xem đúng như lúc live; file không có → in `LỖI host_frame` và trả 1. Chỉ ghi ra
  file, không gửi fork.
- `check`: in thêm `layout_mode`, chế độ thẻ và các cảnh báo mới (data-model §10).

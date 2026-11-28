# Hợp đồng: HTTP cho trang điều khiển (014)

Thêm vào `src/ai_live/app/routes.py` (hoặc `image_routes.py` cạnh các route cảnh). Thông báo lỗi bằng tiếng Việt. Khi `SCENE_ENABLED=false`
mọi route trả trạng thái `scene_disabled`, không lỗi 500.

## `GET /api/scene/background`

```json
{
  "style": "ke_hang",
  "active": true,
  "mask_status": "valid",
  "fallback_reason": null,
  "fallback_message": null,
  "reviewed": false,
  "items": ["coca-cola-chai-500ml", "loc-6-chai-coca-cola-355ml"],
  "changed_at": "2026-11-24T09:00:00+07:00"
}
```

Trường theo data-model §5; `fallback_message` là câu tiếng Việt cho người vận hành, kèm cách khắc phục (ví dụ "Nhân vật chưa có nền: chạy
`uv run python -m ai_live.avatar background-prepare demo_host_02`").

`GET /api/scene` (đã có) thêm khối `"background"` với cùng nội dung.

Không có route đổi nền hay bật/tắt nền khi live (spec, làm rõ 2026-11-24): đổi kiểu nền (kể cả về `goc`) thì sửa `scene.json` trước
giờ live rồi khởi động lại.

## `GET /api/scene/background/preview.png`

Ảnh xem trước khung live với nền (research R13): `preview_frame.png` + ảnh nền theo mặt nạ + lớp `base` 009/013 + nhãn AI. 404 kèm lý do khi
không dựng được (chưa chuẩn bị nền, không có ảnh nền). `Cache-Control: no-store`.

## Trang điều khiển (`control.html` / `control.js`)

Trong khối cảnh live đã có, thêm một dòng "Nền sau host":
- kiểu nền đang dùng, trạng thái phần chuẩn bị (hợp lệ / chưa chuẩn bị / không khớp / chưa duyệt), lý do rơi về nếu có (FR-012);
- ảnh xem trước nhỏ, bấm để xem cỡ thật.

## Kiểm tra sẵn sàng (`src/ai_live/ops/readiness.py`)

`check_background(...)`, cạnh `check_scene`:

| Trường hợp | Mức | Thông báo |
|---|---|---|
| `style = goc` hoặc cảnh tắt | `ok` | "Nền: phòng gốc" |
| fork lip-sync, `missing` | `warn` | "Nhân vật chưa có nền, live sẽ hiện phòng gốc" + lệnh khắc phục |
| `mismatch` | `warn` | lý do cụ thể + lệnh chuẩn bị lại |
| `no_product_art` | `warn` | "Chưa có ảnh sản phẩm đã bỏ nền cho kệ hàng" |
| `valid` nhưng `reviewed = false` | `warn` | "Mặt nạ nền chưa được duyệt bằng mắt" + đường dẫn `review.jpg` |
| hợp lệ, đã duyệt | `ok` | "Nền: kệ hàng, đã chuẩn bị 81 khung" |

Không có trường hợp `fail`: thiếu nền không chặn buổi live (rơi về phòng gốc, FR-010). Đọc manifest từ đĩa, không cần fork chạy; khi fork
đang chạy thì lấy thêm `hello.background`.

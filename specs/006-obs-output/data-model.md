# Mô hình dữ liệu: Đưa AI host vào OBS

- **Feature ID:** `006-obs-output` · **Ngày:** 2026-11-13 · **Plan:** [plan.md](./plan.md)

Feature này không thêm file lưu trữ nào. Chỉ thêm một cài đặt, một vai cho kết nối phát và vài trường trong sự kiện có sẵn.

## 1. `OutputMode` (cài đặt, `core/config.py`)

| Giá trị | Ý nghĩa | Kiểm tra trước demo, canh show đòi |
|---------|---------|------------------------------------|
| `meet` (mặc định) | Chia sẻ tab `/host` vào Google Meet | Trang host (vai `host`) đang phát |
| `obs` | OBS Browser Source mở `/obs` | Nguồn OBS (vai `obs`) đang phát |

- Biến môi trường `OUTPUT_MODE`. Không phân biệt hoa thường, bỏ khoảng trắng.
- `webrtc` (giá trị cũ của `.env.example`) → `meet`, log `output_mode_legacy` (WARNING) một lần lúc khởi động.
- Giá trị khác (`virtualcam`, `rtmp`, ...) → lỗi cấu hình lúc khởi động: "OUTPUT_MODE chỉ nhận meet hoặc obs".
- Cài đặt chỉ đọc lúc khởi động; đổi chế độ phải khởi động lại app (FR-014).

## 2. `HostRole` (vai của kết nối `/ws/host`)

| Vai | Trang | Ưu tiên |
|-----|-------|---------|
| `obs` | `/obs` (OBS Browser Source) | 2 |
| `host` | `/host` (Chrome, chia sẻ vào Meet) | 1 |

- Lấy từ query `role` của `/ws/host`; thiếu hoặc lạ → `host`.
- Chỉ một kết nối giữ quyền phát. Chuyển trạng thái khi có kết nối mới `new` lúc đang có `cur`:

| `cur` | `new` | Kết quả | Mã đóng gửi cho bên thua |
|-------|-------|---------|--------------------------|
| (không có) | bất kỳ | `new` phát | — |
| `host` | `host` | `new` phát | `cur`: 4000 `CLOSE_REPLACED` |
| `obs` | `obs` | `new` phát | `cur`: 4000 `CLOSE_REPLACED` |
| `host` | `obs` | `new` phát | `cur`: 4001 `CLOSE_YIELDED` |
| `obs` | `host` | `cur` giữ | `new`: 4001 `CLOSE_YIELDED` |

- Kết nối bị từ chối (dòng cuối) không bao giờ thành kết nối phát: tin của nó bị bỏ qua, không phát `HOST_CONNECTION`.
- Kết nối phát đóng → không còn ai phát (trang host bị nhường trước đó **không** tự lấy lại; người vận hành tải lại trang).

## 3. Thay đổi trong mô hình có sẵn

- `StaticRenderer.host_role: HostRole | None`: vai của kết nối đang phát; None khi không có.
- Sự kiện `HOST_CONNECTION` (bus): payload `{"connected": bool, "role": "obs" | "host" | null}` (thêm `role`; `null` khi `connected`
  là false).
- `HostStatus`: không đổi trường. Vai lấy từ renderer, không lấy từ tin của trang (trang không tự khai vai trong nhịp).
- `/api/host-config`: thêm `"output_mode": "meet" | "obs"` (để trang host hiện thông báo đúng; không đổi hành vi phát).
- `/api/state`: thêm `"output_mode"` và `"host_role"` cạnh `host_connected` (trang điều khiển hiện "Đầu ra: OBS/Meet").

## 4. Trạng thái trang `/obs` (client, `host.js` với `body.obs`)

```
loading ──(tải cấu hình, tạo AudioContext, /offer nếu nhép miệng)──▶ connecting
connecting ──(ws open, gửi ready)──▶ playing
playing ──(ws đóng mã khác 4000/4001)──▶ reconnecting ──(ws mở lại)──▶ location.reload()
playing ──(ws đóng 4000)──▶ replaced (đóng peer, im lặng, ảnh tĩnh + nhãn)
```

Trang `/host` giữ máy trạng thái cũ, thêm: `playing ──(ws đóng 4001)──▶ yielded` (đóng peer, im lặng, hiện "Đang phát qua OBS, xem
trong cửa sổ OBS", không nối lại). Cả hai trang ở `replaced`/`yielded` đều đóng `RTCPeerConnection` và hủy hẹn giờ `/offer` lại (R5).

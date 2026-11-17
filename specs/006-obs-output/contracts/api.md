# Hợp đồng API: Đưa AI host vào OBS

- **Feature ID:** `006-obs-output` · **Ngày:** 2026-11-13 · **Plan:** [../plan.md](../plan.md)
- Mở rộng: 001 contracts/api.md §3–§4 (`/ws/control`, `/ws/host`), 005 contracts/api.md §3–§4 (`/api/host-config`, trang host),
  007 contracts/api.md (kiểm tra trước demo, cảnh báo). Phần không nhắc ở đây giữ nguyên.

## 1. `GET /obs` (mới)

- Trả trang HTML giống `/host` (cùng `host.html`, cùng thay `{{AI_LABEL_TEXT}}`, `{{AI_LABEL_POSITION}}`, `{{AVATAR_SRC}}`, cùng chờ cảnh
  vẽ xong tối đa `HOST_SCENE_WAIT_S`), khác hai điểm:
  - `<body class="host obs">` thay vì `<body class="host">`.
  - Header `Cache-Control: no-store` như `/host`.
- **Không đọc query string** (Điều I: không có cách tắt nhãn qua URL). Không có nút, lớp phủ, chữ trạng thái hay phụ đề web hiển thị
  (CSS `body.obs` ẩn `#start-overlay`, `#host-status`, `#subtitle`).
- Trang tự chạy khi tải: tạo `AudioContext`, gọi `/offer` nếu `mode` là `livetalking`, rồi mở `/ws/host?role=obs`.

## 2. `WS /ws/host` (đổi)

- Query mới `role`: `obs` | `host`. Thiếu hoặc giá trị khác → `host` (trang `/host` bản cũ vẫn chạy).
- Luật giữ quyền phát (data-model §2):

| Đang phát | Kết nối mới | Kết quả | Mã đóng |
|-----------|-------------|---------|---------|
| không có | bất kỳ | mới phát | — |
| cùng vai | cùng vai | mới phát, cũ bị đóng | 4000 `CLOSE_REPLACED` cho cũ |
| `host` | `obs` | `obs` phát, `host` bị đóng | 4001 `CLOSE_YIELDED` cho `host` |
| `obs` | `host` | `obs` giữ, `host` bị đóng ngay sau `accept` | 4001 `CLOSE_YIELDED` cho `host` |

- Mã 4001 có `reason` `"obs_active"`. Trang nhận 4000 hoặc 4001 PHẢI: dừng Web Audio, dừng và tắt tiếng `<video>`, đóng
  `RTCPeerConnection`, hủy hẹn giờ `/offer` lại, ngừng nhịp `host_status`, không nối lại.
- Tin trang → server và server → trang: không đổi (`ready`, `lipsync_session`, `host_status`, `playback_started`, `sentence_played`;
  `sentence_start`, PCM, `sentence_end`, `subtitle`, `subtitle_clear`, `mode`, `scene`, `stop`). Tin từ kết nối không giữ quyền phát bị bỏ
  qua như hiện nay.

## 3. Hành vi trang khi mất kết nối

| Trang | Mã đóng | Làm gì |
|-------|---------|--------|
| `/host` | 4000 | Như cũ: "Đã có màn hình host khác. Tải lại trang nếu muốn phát ở đây." (thêm: đóng peer) |
| `/host` | 4001 | "Đang phát qua OBS, xem trong cửa sổ OBS. Tải lại trang nếu muốn phát ở đây." Không nối lại |
| `/host` | khác | Như cũ: "Mất kết nối server, đang thử nối lại…", thử lại mỗi 1 s |
| `/obs` | 4000 | Im lặng, giữ ảnh tĩnh + nhãn, không chữ, không nối lại |
| `/obs` | khác | Không chữ; thử nối lại mỗi 1 s; nối được thì `location.reload()` (research R6) |

## 4. `GET /api/host-config` (đổi)

Thêm trường: `"output_mode": "meet" | "obs"`. Các trường cũ giữ nguyên.

## 5. `GET /api/state` và snapshot `/ws/control` (đổi)

Thêm cạnh `host_connected`: `"output_mode": "meet" | "obs"`, `"host_role": "obs" | "host" | null`. Trang điều khiển hiện dòng "Đầu ra:
OBS (đã nối)" / "Đầu ra: Meet — trang host (đã nối)" / "... (chưa nối)".

## 6. Sự kiện bus `HOST_CONNECTION` (đổi)

Payload `{"connected": bool, "role": "obs" | "host" | null}`. Phát khi kết nối giữ quyền phát gửi `ready` lần đầu (`connected: true`) và
khi nó đóng (`connected: false`, `role: null`). Kết nối bị từ chối không phát sự kiện. `/ws/control` chuyển sự kiện này như cũ.

## 7. Kiểm tra trước demo, mục `host` (007, đổi theo `OUTPUT_MODE`)

| Chế độ | Tình trạng | Mức | Lời nhắn | Việc cần làm |
|--------|-----------|-----|----------|--------------|
| `meet` | (mọi trường hợp) | như 007 | như 007 | như 007 |
| `obs` | app tắt | LỖI | như 007 | như 007 |
| `obs` | không có kết nối phát | LỖI | Nguồn OBS chưa nối | Trong OBS thêm Browser Source, URL `http://127.0.0.1:<APP_PORT>/obs`, 720×1248, bật "Control audio via OBS" (runbook §8) |
| `obs` | kết nối phát là `host` | LỖI | Đang phát ở trang host trên Chrome, chưa phải OBS | Thêm nguồn `/obs` trong OBS (nguồn OBS sẽ nhận quyền phát), rồi đóng tab `/host` |
| `obs` | `obs`, chưa có nhịp | CẢNH BÁO | Nguồn OBS đã nối nhưng chưa gửi nhịp trạng thái | Chuột phải nguồn trong OBS → Refresh |
| `obs` | `obs`, nhép miệng, `<video>` tắt tiếng/dừng | LỖI | Hình nhép miệng trong nguồn OBS đang tắt tiếng hoặc dừng | Chuột phải nguồn → Refresh |
| `obs` | `obs`, ảnh tĩnh, `audio` ≠ `running` | LỖI | Âm thanh trong nguồn OBS chưa chạy (trạng thái …) | Chuột phải nguồn → Refresh; nếu mở `/obs` trên Chrome thường thì dùng OBS thay vì Chrome |
| `obs` | `obs`, ổn | ĐẠT | Nguồn OBS đã nối, âm thanh sẵn sàng | — |

Thêm một mục ĐẠT/thông tin trong kết quả: `output_mode` (đã có trong `/api/state`, không phải mục kiểm).

## 8. Canh show (007, đổi theo `OUTPUT_MODE`)

- `obs`: "đầu ra đang nối" = có kết nối phát vai `obs`. Kết nối vai `host` nhận quyền phát ở chế độ `obs` vẫn tính là đầu ra mất (mở
  cảnh báo `host_closed`).
- `obs`: kết nối phát vai `obs` còn mở nhưng không gửi nhịp `host_status` quá `WATCHDOG_HOST_STALE_S` (mặc định 10 s, FR-010) cũng tính
  là đầu ra mất (`host_closed`, chi tiết `stale`); nhịp tới lại thì tự tắt. Chế độ `meet` không có luật này vì Chrome điều tiết timer tab
  nền (Q27) sẽ báo sai.
- Lời nhắn và việc cần làm theo chế độ:

| Loại | `meet` (giữ 007) | `obs` |
|------|------------------|-------|
| `host_closed` | Màn hình host đã đóng · Mở lại /host, bấm "Bắt đầu" rồi chia sẻ lại tab vào Meet | Nguồn OBS đã ngắt · Kiểm OBS còn chạy; chuột phải nguồn AI host → Refresh; đừng để trang /host trên Chrome phát thay |
| `frozen` | Hình trên tab host đứng N giây · … tải lại /host … Meet | Hình trong nguồn OBS đứng N giây · Xem terminal fork; fork còn chạy thì chuột phải nguồn → Refresh |
| `audio_missing` | Có thể mất tiếng ở tab host … · Bấm "Bắt đầu" trên /host … Meet | Có thể mất tiếng ở nguồn OBS … · Kiểm "Control audio via OBS" và thanh âm lượng nguồn trong mixer OBS |

Các loại khác (`silence`, `fork_lost`, `static_mode`, `fallback_mode`) giữ nguyên chữ.

## 9. Không đổi

- `OutputSink` Protocol (ARCHITECTURE §3) vẫn chưa làm: 006 không có sink Python, đầu ra là trang `/obs`. Ghi chú vào ARCHITECTURE
  rằng `OUTPUT_MODE` giờ là `meet | obs` và RTMP/virtualcam trực tiếp để sau.
- Không route nào phát file video (007 FR-021).

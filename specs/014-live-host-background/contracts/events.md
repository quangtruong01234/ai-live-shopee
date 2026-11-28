# Hợp đồng: log và sự kiện (014)

Log JSON qua `log_event` như các feature trước (Điều VIII, FR-015). Không ghi bytes ảnh, chỉ số byte.

| Sự kiện | Khi nào | Trường |
|---|---|---|
| `scene_background_started` | mỗi lần khởi động app có cảnh live, và mỗi `hello` mới của fork | `style`, `active`, `mask_status`, `fallback_reason`, `method`, `reviewed`, `items`, `plate_bytes`, `plate_ms` |
| `scene_background_sent` | gửi `scene_background` tới fork | `plate_bytes` (0 khi gửi `null`) |
| `scene_background_rejected` | fork trả `background_rejected` | `message` |
| `scene_background_failed` | fork trả `background_failed` | `message` |
| `background_clamped` | `softness_px` / `brightness` / `max_items` ngoài khoảng | `field`, `value`, `clamped_to` |
| `background_unknown_key` | khoá lạ trong khối `background` | `key` |
| `background_as_is` | nạp cảnh có `background.as_is: true` (ảnh nền không làm mờ, không chỉnh sáng; FR-009a ngoại lệ ADR-102) | `style` |

- `EventBus`: phát `Event(EventType.SCENE, {"kind": "background", ...status})` khi trạng thái đổi, để trang điều khiển và watchdog 007 cập
  nhật mà không phải hỏi liên tục.
- Watchdog 007: không thêm luật mới; `scene_background_failed` hiện thành banner cảnh báo trên trang điều khiển như các lỗi cảnh khác.
- Fork: `logger.warning("ailive background ...")` một lần cho mỗi lỗi (không lặp mỗi khung); `stats.background_ms` (fork-protocol §5) được
  app ghi vào số đo lượt cạnh `scene_ms`.

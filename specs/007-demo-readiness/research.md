# Research: 007 Sẵn sàng cho buổi demo

> Mỗi mục: Quyết định · Lý do · Phương án đã loại. Không gọi LLM free trong lúc nghiên cứu hay đo (SC-007).

## R1. Tín hiệu "hình đứng" và "mất tiếng"

- **Quyết định:** tab host gửi `host_status` mỗi giây trên WebSocket có sẵn:
  - `frames`: tổng khung video đã giải mã, lấy từ `RTCPeerConnection.getStats()` (`inbound-rtp`, `kind=video`, `framesDecoded`); chế độ
    ảnh tĩnh gửi `null`.
  - `audio`: `"running"` / `"suspended"` / `"closed"` của `AudioContext` (đường tiếng ảnh tĩnh).
  - `video_muted`, `video_paused`: trạng thái thẻ `<video>` (đường tiếng nhép miệng đi qua WebRTC).
  - `visible`: `document.visibilityState` (chỉ để log, không dùng để cảnh báo).

  Hình đứng = đang dùng nhép miệng và `frames` không tăng trong các nhịp nhận được suốt quá `WATCHDOG_FROZEN_S`. Mất tiếng = (a) nhịp báo
  không phát được tiếng theo đường đang dùng, hoặc (b) một câu đã gửi (`SENTENCE`) mà không có xác nhận bắt đầu phát trong
  `WATCHDOG_AUDIO_ACK_S` (ảnh tĩnh, 3 s) hoặc `WATCHDOG_AUDIO_ACK_LIPSYNC_S` (đang nhép miệng, 6 s). Ngưỡng riêng cho nhép miệng thêm
  sau T054 (2026-11-13): fork vốn bắt đầu câu sau khoảng 3 s (khoảng lặng p95 2,98 s ở 005, tối đa 3,16 s ở T054), nên ngưỡng 3 s báo
  sai 2 lần trong 30 phút. Fork chuyển sang ảnh tĩnh thì quay về ngưỡng ảnh tĩnh.
- **Lý do:** `framesDecoded` tăng khi fork còn gửi khung, đúng thứ khách thấy qua Meet, và `getStats` chạy cả khi tab ở nền (khác
  `requestVideoFrameCallback` dừng khi tab không vẽ). Không cần phân tích hình (spec giả định).
- **Đã loại:** phân tích ảnh trên app (tốn CPU, ngoài phạm vi); `requestVideoFrameCallback` (không chạy ở tab nền → báo sai khi người vận
  hành đang ở tab điều khiển); dựa vào khung fork tự báo (fork vẫn render khi đường WebRTC tới tab đã đứng).

## R2. Quy tắc canh và cảnh báo gốc

- **Quyết định:** chỉ canh khi show `running` hoặc `closing` và không `paused`. Loại và gốc:

  | Loại | Điều kiện mở | Điều kiện đóng | Bị che bởi |
  |---|---|---|---|
  | `host_closed` | `HOST_CONNECTION.connected=false` | kết nối lại | — |
  | `fork_lost` | cấu hình `livetalking`, `LIPSYNC_HEALTH.connected=false` | nối lại | `host_closed` |
  | `static_mode` | cấu hình `livetalking`, `AVATAR_MODE.active=static` | về `livetalking` | `host_closed` |
  | `fallback_mode` | `SHOW_STATE.mode=fallback` (không tính `verbatim`) | `mode=normal` | — |
  | `frozen` | R1 | `frames` tăng lại | `host_closed`, `fork_lost`, `static_mode` |
  | `audio_missing` | R1 | nhịp báo tiếng chạy lại / có xác nhận phát | `host_closed` |
  | `silence` | không câu nào đang phát và lần cuối có câu kết thúc (hoặc show bắt đầu) đã quá `WATCHDOG_SILENCE_S` | một câu bắt đầu phát | `host_closed`, `fork_lost`, `frozen`, `audio_missing` |

  Khi một cảnh báo gốc mở, cảnh báo con đang mở được đóng với `reason="covered"` và không mở lại cho tới khi gốc đóng (spec biên "một
  cảnh báo gốc"). Tạm dừng: đóng `silence`/`frozen`/`audio_missing` với `reason="paused"`, đặt lại mốc im lặng khi tiếp tục. Show kết thúc:
  đóng mọi cảnh báo với `reason="show_ended"`.
- **Lý do:** đúng sáu dấu hiệu FR-007; bảng gốc tránh ba banner cho một lần fork chết.
- **Đã loại:** canh cả lúc không có show (spec kịch bản 7 cấm cảnh báo im lặng khi chờ; trạng thái fork/host lúc chờ đã có trên trang
  điều khiển).

## R3. Tự bỏ câu kẹt

- **Quyết định:** `silence` mở ở 5 s (mức `warning`). Tới `WATCHDOG_AUTOSKIP_S` (15 s) gọi `director.skip_current()` đúng một lần cho khoảng
  im lặng đó, ghi `auto_action="skip"` và log `watchdog_auto_skip`. Nếu sau đó thêm `WATCHDOG_SILENCE_S` vẫn chưa có câu nào phát thì nâng
  mức `operator` ("cần người vận hành", gợi ý video dự phòng theo runbook §4). Không lặp lại skip trong cùng khoảng im lặng.
- **Lý do:** Làm rõ 2026-11-13; `skip_current` là đúng nút "Bỏ qua câu đang nói" (runner hủy câu, đánh dấu đoạn SKIPPED, gọi
  `renderer.interrupt()`), đã có test 004. SC-003: im lặng ≤ 15 + 2 s.
- **Đã loại:** khởi động lại TTS/fork (M2); bỏ câu nhiều lần (có thể xóa hết đoạn mà không gỡ được nguyên nhân).

## R4. File log để báo cáo đọc được sau khi app sập

- **Quyết định:** thêm vào thư mục phiên:
  - `gaps.jsonl`: mỗi khoảng lặng `ScriptRunner._record_gap` ghi một dòng (`show_id`, `kind`, `seconds`, `from_id`, `to_id`, `at`).
  - `alerts.jsonl`: mỗi lần cảnh báo mở / nâng mức / tự gỡ / đóng.
  - `readiness.jsonl`: mỗi lần kiểm tra trước demo.
  - `session.json`: điều kiện chạy lúc mở phiên (`app_env`, `reply_engine`, `tts_provider`, `avatar_mode`, `scene_enabled`, nguồn điện,
    `customer_id`, `avatar_id`, `catalog_version`).

  Mọi ghi đi qua worker thread sẵn có của `SessionLog` (mỗi dòng flush ngay), nên app sập vẫn còn tới dòng cuối.
- **Lý do:** `show_summary_<show>.json` chỉ có khi show kết thúc; khoảng lặng hiện chỉ ở stdout. Báo cáo cần nguồn ổn định trên đĩa.
- **Đã loại:** đọc stdout (không có file, định dạng log đổi được); ghi báo cáo định kỳ trong lúc chạy (thêm việc trên đường show).

## R5. Nguồn điện và ổ đĩa

- **Quyết định:** `shutil.disk_usage(session_data_dir)`, ngưỡng `READINESS_MIN_FREE_GB` (5). Nguồn điện: Windows gọi
  `kernel32.GetSystemPowerStatus` qua `ctypes` (`ACLineStatus` 1 = cắm sạc, 0 = pin, 255 = không rõ); hệ khác trả `None` → "Không kiểm
  được".
- **Lý do:** không thêm thư viện (CLAUDE.md: thêm phụ thuộc cần ADR); máy demo là Windows.
- **Đã loại:** `psutil` (phụ thuộc mới chỉ cho một mục Cảnh báo).

## R6. Nội dung `verbatim` cho video dự phòng

- **Quyết định:** `POST /api/show/start` nhận thân tùy chọn `{"content": "script" | "verbatim"}` (mặc định `script`, không đổi hành vi cũ).
  `verbatim` đặt `ShowSession.content_source="verbatim"`; `ScriptRunner._prepare` khi đó đi thẳng vào `_prepare_fallback` (nguyên văn
  `intro` rồi `description`, con trỏ riêng mỗi sản phẩm, qua làm sạch + guard + TTS + renderer realtime) và đoạn kết dùng
  `CLOSING_FALLBACK_SENTENCE`; không gọi engine lần nào. Chế độ show vẫn `normal` (không phải lỗi) nên không sinh cảnh báo
  `fallback_mode`. Không có nút trên trang điều khiển; chỉ lệnh làm video dự phòng dùng.
- **Lý do:** Làm rõ 2026-11-13; dùng lại đường dự phòng R10 đã có test của 004, chỉ thêm cách vào thẳng.
- **Đã loại:** `REPLY_ENGINE=fake` (câu vô nghĩa); chế độ `fallback` từ đầu (vẫn thử gọi LLM lại mỗi đoạn và bật banner lỗi).

## R7. Ghi và kiểm video dự phòng

- **Quyết định:** dùng recorder của fork (`/ailive/record/start|stop`, 005): ghi đúng khung sau khi ghép nhãn "AI", cảnh, watermark, và
  tiếng fork phát (mp4 h264 + aac). Lệnh: kiểm app (`/health`: nhép miệng đang chạy, host sẵn sàng, không có show), kiểm fork bật ghi →
  bắt đầu ghi → `POST /api/show/start {"content":"verbatim"}` → chờ `seconds - 8` → `POST /api/show/end` → chờ show `ended` (≤ 30 s)
  → chờ 1 s đuôi → dừng ghi → `ailive_ext.analyze` bằng python của fork → đọc `report.json`:
  - độ dài = `checks.stream.seconds` trong 120–180;
  - có tiếng = `checks.audio.peak > 0` và `speaking_frames > 0`;
  - nhãn = `checks.label.ok` (mọi khung, không chỉ khung mẫu).

  Chép `<prefix>.mp4` sang `BACKUP_VIDEO_DIR/<tên>.mp4`, viết `<tên>.sheet.json` + `.sheet.md`. Không cắt, không ghép (Điều I). Chế độ
  ảnh tĩnh: từ chối (không có recorder).
- **Lý do:** recorder và analyze đã kiểm ở 005/010; một lệnh lặp lại được mỗi khi nhân vật/sản phẩm/cảnh đổi.
- **Đã loại:** quay màn hình tab `/host` (cần công cụ ngoài, không kiểm tự động được); dựng video từ ảnh + tiếng (vi phạm "không dựng
  hậu kỳ" của spec).

## R8. Kiểm tra trước demo: API và CLI cùng kết quả

- **Quyết định:** một module `ops/readiness.py` gồm các hàm `check_*` thuần (nhận giá trị, trả `ReadinessItem`). `run_readiness(ctx)` gom
  trạng thái từ `AppContext` (+ gọi `GET {LIVETALKING_URL}/ailive/health` timeout 2 s); `GET /api/readiness` trả JSON. CLI gọi API của app
  (`APP_HOST:APP_PORT`); không nối được thì `run_offline(settings)` kiểm phần không cần app (cấu hình, file sản phẩm, bộ cảnh, video dự
  phòng, fork trực tiếp, nguồn điện, ổ đĩa) và đánh mục `app`/`host`/`llm_chain` là Lỗi "app chưa bật". Mã thoát 0 khi "Sẵn sàng".
- **Lý do:** FR-001 "cùng kết quả": CLI dùng đúng kết quả API khi app chạy.
- **Đã loại:** CLI tự kiểm song song với app (hai nguồn sự thật, dễ lệch).

## R9. Timer ở tab nền

- **Quyết định:** nhịp `host_status` dùng `setInterval(1000)`. Chrome giới hạn timer tab nền tối thiểu 1 s (không ảnh hưởng); điều tiết
  mạnh (1 lần/phút) chỉ áp cho tab ẩn > 5 phút, im lặng, timer lồng nhau, nên lúc show đang phát tiếng hoặc tab đang được chia sẻ thì
  không bị. Watchdog chỉ kết luận hình đứng từ hai nhịp có `frames` bằng nhau cách nhau quá ngưỡng; không có nhịp thì không cảnh báo
  (mất kết nối host đã có `host_closed`).
- **Đã loại:** Web Worker giữ nhịp (phức tạp thêm, chưa thấy cần).

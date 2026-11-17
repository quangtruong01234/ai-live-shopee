# Kế hoạch triển khai: Sẵn sàng cho buổi demo

- **Feature ID:** `007-demo-readiness` · **Spec:** [spec.md](./spec.md) · **Ngày:** 2026-11-13
- **Trạng thái:** Planned
- **Ghi chú quy trình:** làm liên tục theo ủy quyền 2026-11-13, không gọi LLM free (SC-007): mọi lần chạy app trong feature này dùng
  `REPLY_ENGINE=fake`; video dự phòng đọc nguyên văn file sản phẩm nên không cần LLM.

## Tóm tắt

Thêm gói `src/ai_live/ops/` với bốn phần, mỗi phần một user story:

1. **Kiểm tra trước demo (US1):** hàm kiểm thuần đọc cấu hình và trạng thái app (fork, host, nội dung, cảnh, chuỗi model đã biết,
   video dự phòng, nguồn điện, ổ đĩa), trả về `ReadinessResult`. Gọi qua `GET /api/readiness` (nút trên trang điều khiển) và lệnh
   `python -m ai_live.ops readiness` (gọi API của app đang chạy; app tắt thì kiểm phần không cần app). Ghi `readiness.jsonl`.
2. **Canh show (US2):** `ShowWatchdog` chỉ quan sát: nghe bus sự kiện, sự kiện phát tiếng (`PlaybackNotifier`) và nhịp `host_status`
   mới do tab host gửi mỗi giây; tick 0,25 s. Mở/đóng cảnh báo (`ALERT` lên trang điều khiển, `alerts.jsonl`), tự bỏ câu kẹt một lần
   qua `director.skip_current()` rồi nâng mức "cần người vận hành".
3. **Báo cáo tổng duyệt (US3):** `python -m ai_live.ops report <phiên> [--show <id>]` đọc file log phiên (thêm `gaps.jsonl` và
   `session.json` để đủ dữ liệu khi app sập), xuất `rehearsal_<show_id>.md/.json` cạnh log.
4. **Video dự phòng (US4):** `python -m ai_live.ops backup-video` chạy show thật ở chế độ nội dung mới `verbatim` (đọc nguyên văn giới
   thiệu + mô tả, không gọi LLM), ghi bằng recorder của fork (005), kiểm bằng `ailive_ext.analyze`, chép video và tờ mô tả vào
   `out/backup_video/`. App không có đường phát file (FR-021).

## Bối cảnh kỹ thuật

- **Ngôn ngữ/runtime:** Python 3.12, FastAPI, asyncio; JS thuần cho trang host/điều khiển. Không thêm thư viện (nguồn điện qua
  `ctypes` của stdlib trên Windows, ổ đĩa qua `shutil.disk_usage`).
- **Thành phần đụng tới:** `core/config.py`, `core/events.py`, `core/models.py` (`ShowSession.content_source`), `director/script_runner.py`
  (`verbatim`, ghi khoảng lặng), `director/session_log.py` (`gaps.jsonl`, `alerts.jsonl`, `readiness.jsonl`, `session.json`),
  `director/show_director.py` (`start_show(content=...)`), `avatar/static_renderer.py` (nhận `host_status`), `app/main.py`, `app/routes.py`,
  `app/context.py`, `app/static/{host.js,control.html,control.js,style.css}`, fork `ailive_ext/ingest.py` (`record_enabled` trong health).
- **Thành phần mới:** `src/ai_live/ops/{__init__,__main__,readiness,watchdog,rehearsal,backup_video,system}.py`.
- **Adapter:** không có adapter mới; watchdog và readiness đọc qua các interface có sẵn (`HostRenderer`, `LipsyncHealth`,
  `ChainReplyEngine.snapshot`, `SceneController`).
- **Ràng buộc phần cứng:** test chạy không GPU (renderer tĩnh, TTS giả, fork giả `tests/fixtures/fake_fork.py`). Đo show 30 phút và làm
  video dự phòng chạy trên GPU laptop (ADR-023), không RunPod.

## Kiểm tra Constitution

| Điều | Nội dung | Đạt? | Ghi chú |
|---|---|---|---|
| I | Realtime / nhãn AI / một host một tài khoản | ✓ | Video dự phòng ghi lại từ chính đường realtime, không dựng hậu kỳ, không cắt ghép; app không có route phát file (FR-021, test kiểm không route nào trả `video/*`). Readiness báo Lỗi khi nhãn tắt; analyze kiểm nhãn ở mọi khung của video. Nhân vật khác khách bị app từ chối lúc khởi động như cũ. |
| II | Đồng ý / bảo mật | ✓ | Video, log, báo cáo nằm trong `out/` và `data/sessions/` (ngoài git). Readiness chỉ ghi biến có giá trị hay không, không ghi khóa. "Việc tự xác nhận" nhắc văn bản đồng ý. |
| III | Trả lời có căn cứ | ✓ | Không đổi prompt hay guard. `verbatim` dùng đúng câu của khách qua cùng bước làm sạch + guard như chế độ dự phòng R10 của 004. |
| IV | Adapter | ✓ | Không đổi interface adapter; thêm một loại tin `host_status` từ tab host (renderer tĩnh nhận và phát lên bus). Cấu hình mới (`WATCHDOG_*`, `READINESS_MIN_FREE_GB`, `BACKUP_VIDEO_DIR`) qua `Settings` và `.env.example`. |
| V | Test trước | ✓ | Logic watchdog/report/readiness là hàm thuần với đồng hồ giả, test viết trước; route test với fork giả, không GPU/mạng/khóa. Phần GPU kiểm bằng quickstart §5–§6 trên GPU laptop. |
| VI | Ngân sách độ trễ | ✓ | Watchdog không nằm trên đường sinh câu: đăng ký bus (publish không chờ) và listener phát tiếng có guard; tick riêng. SC-004 đo lại 30 phút. |
| VII | Đơn giản | ✓ | Không thêm phụ thuộc hay hạ tầng; cảnh báo chỉ hiện trên trang điều khiển (không gửi tin nhắn, không tự khởi động lại, M2). |
| VIII | Quan sát được | ✓ | `readiness.jsonl`, `alerts.jsonl`, `gaps.jsonl`, `session.json`; mỗi lần tự bỏ câu có log `watchdog_auto_skip`. |
| IX | Ngôn ngữ | ✓ | Code, comment tiếng Anh; lời nhắn readiness/cảnh báo/báo cáo/tờ mô tả tiếng Việt có dấu. |

## Ảnh hưởng ngân sách độ trễ

- Không thêm bước nào vào đường câu → tiếng → hình. Watchdog tốn một coroutine tick 0,25 s và một subscriber bus.
- Nhịp `host_status` mỗi giây từ tab host: một tin JSON nhỏ trên WebSocket có sẵn, renderer chỉ phát lại lên bus.
- Tự bỏ câu kẹt ở 15 s giảm khoảng im lặng xấu nhất khi bước tạo tiếng treo (SC-003), không đổi trường hợp bình thường.
- SC-004: show 30 phút `REPLY_ENGINE=fake` trên GPU laptop với watchdog bật; so lặng p95 và câu đầu với 005 T073 (2,98 s; khung đầu
  theo `latency_summary.json` của lần đó). Ghi chú: show giả không đạt PRD tiêu chí 3 (p95 ≤ 1,5 s) từ 005; báo cáo sẽ ghi "Không đạt"
  đúng như số đo, không phải lỗi của feature này.

## Cấu trúc mã nguồn

```
src/ai_live/ops/
  __init__.py
  __main__.py        # python -m ai_live.ops {readiness|report|backup-video}
  readiness.py       # ReadinessItem/Result, check_* thuần, run_readiness(app ctx) và run_offline(settings)
  system.py          # power_status() (Windows ctypes, nơi khác None), free_disk_gb()
  watchdog.py        # ShowWatchdog (logic thuần + đồng hồ tiêm vào), run_watchdog(bus sub, tick)
  rehearsal.py       # load_show_logs, build_report, render_markdown, write_report
  backup_video.py    # BackupVideoMaker: app/fork client, chạy show verbatim, ghi, analyze, tờ mô tả
src/ai_live/director/session_log.py   # + write_gap, write_alert, write_readiness, write_session_info
src/ai_live/director/script_runner.py # + content_source verbatim, ghi gap vào session log
src/ai_live/director/show_director.py # + start_show(content=...)
src/ai_live/avatar/static_renderer.py # + host_status → HOST_STATUS
src/ai_live/app/{main,routes,context,ws}.py, static/{host.js,control.html,control.js,style.css}
vendor/livetalking/ailive_ext/ingest.py  # + record_enabled trong /ailive/health
tests/unit/test_readiness.py, test_watchdog.py, test_rehearsal.py, test_backup_video.py, test_system.py, test_ops_cli.py,
  test_session_log_ops.py
tests/integration/test_readiness_api.py, test_watchdog_show.py, test_show_verbatim.py
vendor/livetalking/ailive_ext/tests/test_ingest.py  # + record_enabled
```

## Phase 0: Nghiên cứu → [research.md](./research.md)

R1 tín hiệu hình đứng/mất tiếng (nhịp tab host, `getStats` WebRTC thay vì phân tích hình); R2 quy tắc canh và gốc cảnh báo; R3 tự bỏ câu
kẹt; R4 file log mới để báo cáo đọc được sau khi sập; R5 nguồn điện/ổ đĩa không thêm thư viện; R6 nội dung `verbatim`; R7 ghi video
dự phòng bằng recorder + analyze; R8 readiness CLI dùng chung kết quả với API; R9 chống điều tiết timer ở tab nền.

## Phase 1: Thiết kế

- [data-model.md](./data-model.md): `ReadinessItem`, `ReadinessResult`, `Alert`, `AlertKind`, `HostStatus`, `GapRecord`, `SessionInfo`,
  `RehearsalReport`, `BackupVideoSheet`.
- [contracts/api.md](./contracts/api.md): `GET /api/readiness`, `POST /api/show/start` thêm `content`, sự kiện `alert`, `state.alerts`,
  `/health` thêm `customer_id`/`avatar_id`, tin `host_status` của tab host, fork `/ailive/health.record_enabled`.
- [contracts/files.md](./contracts/files.md): `readiness.jsonl`, `alerts.jsonl`, `gaps.jsonl`, `session.json`, `rehearsal_<show>.{md,json}`,
  `out/backup_video/<tên>.{mp4,sheet.json,sheet.md}`.
- [contracts/cli.md](./contracts/cli.md): ba lệnh `python -m ai_live.ops ...`, mã thoát.
- [quickstart.md](./quickstart.md): chạy kiểm tra, giả lập lỗi để thấy cảnh báo, xuất báo cáo, làm video dự phòng, đo 30 phút.

## ADR cần ghi

- **ADR-057:** Sẵn sàng demo: (a) canh show tự bỏ câu kẹt một lần ở 15 s rồi chỉ cảnh báo; (b) hình đứng/mất tiếng dựa vào tín hiệu tab
  host (`getStats` WebRTC, trạng thái âm thanh), không phân tích hình; (c) video dự phòng làm bằng show `verbatim` + recorder của fork,
  không dựng hậu kỳ, app không có đường phát; (d) nguồn điện qua `ctypes` của stdlib, không thêm thư viện.

## Rủi ro mới

- **Tab host chạy nền bị Chrome điều tiết timer** → nhịp `host_status` thưa, báo hình đứng sai. Giảm: hình đứng chỉ xét trên các nhịp đã
  nhận (số khung giải mã không đổi giữa hai nhịp cách nhau > ngưỡng), thiếu nhịp không tự sinh cảnh báo; tab đang được chia sẻ qua Meet
  hoặc đang phát tiếng thì Chrome không điều tiết mạnh (research R9).
- **Tự bỏ câu ở lúc không đúng** (câu dài bình thường) → chỉ tính im lặng giữa hai câu, không tính lúc câu đang phát (spec biên).
- **Video dự phòng có mặt/giọng người mẫu** → chỉ trong `out/` (gitignore), RISKS cập nhật.
- **Ghi luồng để làm video quên tắt trước buổi demo** → readiness báo Lỗi khi fork đang bật ghi.

## Theo dõi độ phức tạp

| Vi phạm | Vì sao cần | Phương án đơn giản hơn đã loại vì |
|---|---|---|
| Không có | | |

# Kế hoạch triển khai: Đưa AI host vào OBS

- **Feature ID:** `006-obs-output` · **Ngày:** 2026-11-13 · **Spec:** [spec.md](./spec.md)
- **Đầu vào:** spec đã làm rõ ở `specs/006-obs-output/spec.md`
- **Ghi chú quy trình:** người dùng giao chạy liên tục (2026-11-13, "làm các task còn sót chạy song song với 006 gộp với output OBS").
  Quyết định dưới đây do mình tự chốt theo hướng khuyến nghị; phần cần mắt người (xem nguồn trong OBS, nghe tiếng) gom vào gói duyệt
  cuối (quickstart §5).

## Tóm tắt

OBS nhận AI host qua một **Browser Source** mở trang mới `/obs` của app. Trang này là `host.html` với lớp `obs` trên `<body>`, dùng lại
`host.js`: tự chạy khi tải (CEF của OBS cho phát tiếng không cần bấm), không lớp phủ, không chữ trạng thái, không phụ đề web; hình nhép
miệng từ fork qua WebRTC hoặc ảnh tĩnh + Web Audio như trang host, ack phát tiếng giữ nhịp show như cũ. Kết nối `/ws/host` thêm vai
`obs`/`host` với ưu tiên cố định obs > host (trang host bị nhường nhận mã đóng 4001), và trang mất quyền phát nhả hẳn phiên WebRTC của fork
(sửa lỗi tiềm ẩn nói đôi). Cài đặt `OUTPUT_MODE=meet|obs` (mặc định `meet`, `webrtc` cũ hiểu là `meet`) chỉ đổi điều kiện của kiểm tra
trước demo và canh show (007). Không thêm thư viện Python, không đổi fork. Feature 006 cũ (YouTube) bỏ theo yêu cầu người dùng.

## Bối cảnh kỹ thuật

- **Ngôn ngữ / phiên bản:** Python 3.12 (uv, ADR-020); JavaScript thuần trong `app/static/` như hiện nay.
- **Phụ thuộc chính:** FastAPI, pydantic-settings (có sẵn) · **Phụ thuộc MỚI cần duyệt:** không có. OBS Studio portable chỉ là công cụ
  kiểm trên máy dev, ngoài repo, không phải phụ thuộc của app (ADR-059).
- **Lưu trữ:** không có file mới. Log phiên 007 (`alerts.jsonl`, `readiness.jsonl`) ghi thêm `output_mode`.
- **Kiểm thử:** pytest không GPU: luật vai trên `StaticRenderer` với kết nối giả (`tests/unit/test_host_roles.py`), route `/obs`, ws
  `?role=`, host-config, `/api/state` (`tests/integration/test_obs_page.py`), cấu hình `OUTPUT_MODE` (`test_config.py`), kiểm tra trước
  demo và canh show theo chế độ (test 007 hiện có, thêm ca `obs`). Hành vi trang (`host.js`) kiểm bằng Chrome DevTools MCP với Chrome chạy
  `--autoplay-policy=no-user-gesture-required` (mô phỏng CEF), rồi OBS portable ghi hình để chấm bằng `scripts/selfcheck/lipsync_check.py`.
- **Nơi chạy:** laptop. `AVATAR_MODE=static` cho logic và kiểm trang; GPU laptop (ADR-023) cho nhép miệng trong OBS. Không RunPod.
- **Adapter liên quan:** `AvatarRenderer` (chỉ `StaticRenderer` đổi: vai kết nối; `SwitchingRenderer` và `LiveTalkingRenderer` chuyển
  tiếp như cũ). `OutputSink` vẫn chưa làm (contracts §9).
- **Mục tiêu hiệu năng:** không thêm khâu trên đường câu → tiếng. Lặng giữa câu p95 qua OBS ≤ p95 qua `/host` + 0,2 s (SC-005). Hình nhép
  miệng có lại ≤ 10 s sau khi fork sẵn sàng (SC-004).
- **Ràng buộc khác:** `/obs` không đọc query string (Điều I); không sửa `.env` của người dùng (đang `OUTPUT_MODE=webrtc`, phải chạy tiếp
  như `meet`); không route nào phát file video (007 FR-021).

## Kiểm tra Constitution (cổng)

| Điều | Kết quả | Ghi chú |
|------|---------|---------|
| I. Realtime, nhãn AI, 1 host 1 tài khoản | Đạt | `/obs` là cùng đường realtime với `/host`; nhãn nằm trong khung fork hoặc trên ảnh tĩnh, OBS chụp cả trang; không query string nào tắt nhãn (test route) |
| II. Đồng ý và bảo mật | Đạt | Không thêm hình, giọng hay bí mật nào; OBS portable không lưu stream key trong repo (cấu hình ở `%LOCALAPPDATA%`) |
| III. Trả lời có căn cứ | N/A | Không đổi nội dung |
| IV. Adapter trước | Đạt | Đầu ra là một trang mới + vai kết nối, không đổi lõi show; chọn bằng `OUTPUT_MODE` |
| V. Test trước (GPU: laptop trước) | Đạt | Test luật vai, route, cấu hình, kiểm tra/canh show trước khi sửa code; GPU laptop chỉ cho bước kiểm nhép miệng trong OBS |
| VI. Ngân sách độ trễ | Đạt | Không thêm bước; SC-005 đo so với `/host` |
| VII. Đơn giản trước | Đạt | Không thư viện mới, không transport mới ở fork (đã loại virtualcam/rtmp, research R1); một cờ cấu hình có sẵn được dùng lại |
| VIII. Quan sát được | Đạt | `HOST_CONNECTION` thêm `role`; log `host_role_yielded`, `output_mode_legacy`; `/api/state` có `output_mode`, `host_role`; nhịp `host_status` như cũ |
| IX. Ngôn ngữ và tài liệu | Đạt | Code/comment tiếng Anh; lời trên trang, kiểm tra, banner, runbook tiếng Việt |

Kiểm lại sau Phase 1: vẫn Đạt cả 9 điều.

## Ảnh hưởng ngân sách độ trễ

| Khâu | Ngân sách (ARCHITECTURE §4) | Feature này thay đổi gì | Cách đo |
|------|-----------------------------|-------------------------|---------|
| Câu đầu của show | ≤ 5 s | Không đổi (OBS chỉ thay trang xem) | Bảng độ trễ như cũ |
| Khoảng lặng giữa câu | p95 ≤ 1,5 s | Không thêm bước; cho phép tối đa +0,2 s so với `/host` (SC-005) | `python -m ai_live.ops report` hai show cùng cấu hình |
| Hình nhép miệng sau khi fork bật lại | ≤ 10 s (SC-004) | Thêm bước nhả phiên WebRTC của trang bị thay (R5) | Đếm thời gian trong bản ghi OBS; TODO đo fork xóa phiên |

## Cấu trúc mã nguồn

### Tài liệu của feature
```
specs/006-obs-output/
├── spec.md · plan.md · research.md · data-model.md · quickstart.md · tasks.md
└── contracts/
    └── api.md       # GET /obs, /ws/host?role=, mã 4001, host-config, /api/state, HOST_CONNECTION, kiểm tra và canh show theo chế độ
```

### Mã nguồn
```
src/ai_live/core/config.py              # OUTPUT_MODE: meet|obs, webrtc → meet (cảnh báo), giá trị khác → lỗi
src/ai_live/avatar/static_renderer.py   # attach(conn, role): luật obs > host, CLOSE_YIELDED 4001, host_role, payload HOST_CONNECTION
src/ai_live/avatar/switching_renderer.py · livetalking_renderer.py   # chuyển tiếp attach(role), host_role
src/ai_live/core/protocols.py           # chữ ký attach thêm role (nếu Protocol có attach)
src/ai_live/app/ws.py                   # đọc ?role=
src/ai_live/app/routes.py               # GET /obs; host-config output_mode; /api/state output_mode, host_role
src/ai_live/app/context.py · main.py    # truyền output_mode; log output_mode_legacy lúc khởi động
src/ai_live/app/static/host.html        # giữ một file, lớp body do route thay
src/ai_live/app/static/host.js          # chế độ obs: tự chạy, ws ?role=, 4001, nhả peer khi 4000/4001, tải lại sau khi nối lại
src/ai_live/app/static/style.css        # body.obs ẩn lớp phủ, chữ trạng thái, phụ đề web
src/ai_live/app/static/control.js       # dòng "Đầu ra: …"
src/ai_live/ops/readiness.py            # mục host theo OUTPUT_MODE (contracts §7)
src/ai_live/ops/watchdog.py             # đầu ra đang nối theo vai, lời nhắn theo chế độ (contracts §8)
tests/unit/test_host_roles.py · tests/unit/test_config.py
tests/integration/test_obs_page.py · test cũ của 007 (readiness, watchdog) thêm ca obs
.env.example · docs/RUNBOOK.md (§8 OBS) · docs/ARCHITECTURE.md
```

## Phase 0: Nghiên cứu → [research.md](./research.md)

R1 cách đưa vào OBS (Browser Source) · R2 tự phát tiếng trong CEF · R3 WebRTC trong Browser Source · R4 vai và mã đóng · R5 nhả phiên
WebRTC của fork · R6 tự nối lại và tải lại · R7 khung, nhãn, phụ đề · R8 `OUTPUT_MODE` · R9 kiểm tra và canh show theo chế độ · R10 cách
kiểm chứng · R11 tiếng vọng monitoring và "Shutdown source when not visible" · R12 video dự phòng không đổi.

## Phase 1: Thiết kế

- [data-model.md](./data-model.md): `OutputMode`, `HostRole` và bảng chuyển trạng thái, thay đổi trong mô hình và API có sẵn, máy trạng
  thái trang `/obs` và `/host`.
- [contracts/api.md](./contracts/api.md): §1–§9 như trên.
- [quickstart.md](./quickstart.md): US1–US3 bằng tay, kiểm tự động bằng MCP và OBS portable, gói duyệt.

## ADR cần ghi

- **ADR-058:** bỏ M1c YouTube (người dùng không live trên YouTube); 006 là đầu ra OBS qua Browser Source trang `/obs`, vai `obs` ưu tiên
  hơn `host` trên `/ws/host` (mã 4001), `OUTPUT_MODE=meet|obs` (`webrtc` cũ = `meet`). RTMP/virtualcam trực tiếp từ fork để sau.
- **ADR-059:** OBS Studio portable là công cụ kiểm trên máy dev, giải nén ngoài repo ở `%LOCALAPPDATA%\ai-live\obs`, không phải phụ thuộc
  của app.

Cả hai ghi `Đề xuất (006)`, chờ người dùng xác nhận trong gói duyệt.

## Rủi ro mới

- **Q28** OBS mở trước app: CEF hiện trang lỗi, không tự thử lại (R6).
- **Q29** "Shutdown source when not visible" hoặc đổi cảnh OBS làm trang `/obs` đóng: mất tiếng, canh show báo `host_closed` (R11).
- **Q30** bật "Monitor and Output" trên nguồn khi Meet/loa cùng máy: tiếng vọng hoặc nói đôi (R11).
- **Q31** fork nhả phiên WebRTC chậm khi trang bị thay: OBS kẹt ảnh tĩnh lâu hơn 10 s (R5).
- **Q32** mở `/obs` trên Chrome thường: `AudioContext` ở `suspended`, không tiếng nhưng vẫn giữ quyền phát (R2).

## Theo dõi độ phức tạp

Không có vi phạm.

# Kế hoạch triển khai: AI host chuyển động tự nhiên, nhép miệng realtime trên laptop

- **Feature ID:** `005-lipsync-livetalking` · **Ngày:** 2026-11-06 · **Spec:** [spec.md](./spec.md)
- **Đầu vào:** spec đã làm rõ ở `specs/005-lipsync-livetalking/spec.md`

## Tóm tắt

Thay ảnh tĩnh bằng nhân vật AI chạy trên bộ clip nền có chuyển động, miệng được tạo realtime theo tiếng TTS, trên GPU laptop GTX 1650 Ti
(ADR-023). Lõi tạo hình là **fork LiveTalking** dùng **Wav2Lip** (`wav2lip256`), chạy **process riêng, venv riêng** trong
`vendor/livetalking/` (ngoài git), phần sửa của mình nằm trong `ailive_ext/`. App giữ TTS và lõi pipeline như cũ. Adapter mới
`LiveTalkingRenderer` đẩy PCM16 của từng câu vào fork qua WebSocket `/ailive/ws` và nhận ack `playback_started` / `sentence_played`.
Hình và tiếng tới Chrome bằng WebRTC của LiveTalking, phát trong trang `/host` của app. Nhãn "AI" được vẽ ngay trong khung hình của fork.
Lớp bọc `SwitchingRenderer` tự về ảnh tĩnh sau 2 lượt lỗi tạo hình liền nhau, và người vận hành bật lại được. Nhân vật được mô tả bằng
`character.json`, gắn với đúng một khách (`CUSTOMER_ID`). Lệnh `prepare` chuẩn bị từng clip, và fork xoay vòng clip có chuyển dần.
`ShowDirector` và `ScriptRunner` không đổi cách gọi `speak`/`interrupt`. Chế độ `static` giữ nguyên hành vi 001/004.

## Bối cảnh kỹ thuật

- **Ngôn ngữ / phiên bản:** Python 3.12 (uv, `.python-version`, ADR-020) cho cả app và venv của fork (R11).
- **Phụ thuộc chính:** FastAPI, pydantic-settings, uvicorn[standard] (đã kéo theo `websockets`) · **Phụ thuộc MỚI cần duyệt (ADR-048):**
  - **Repo app:** khai báo trực tiếp `websockets` trong `pyproject.toml`. Gói đã có trong `uv.lock` qua `uvicorn[standard]`, nên không tải
    thêm gì. Lý do: `LiveTalkingRenderer` là client WebSocket và test cần fork giả (R14). Không thêm gói nào khác.
  - **Venv fork (`vendor/livetalking/.venv`, tách khỏi `uv.lock` của app):**
    - torch 2.9.1 + torchvision + torchaudio, bản cu128; nếu không chạy được trên driver 565.90 thì dùng cu126 (R11).
    - Toàn bộ `requirements.txt` của LiveTalking ở SHA đã ghim, gồm aiortc, aiohttp, opencv-python-headless, librosa, resampy, soundfile,
      numpy, scipy, einops, transformers, diffusers, accelerate.
    - Các gói upstream không dùng tới (edge_tts, flask, dashscope, openai, `websockets==12.0`...) vẫn được cài theo requirements, để fork
      giữ gần upstream (RISKS G14).
    - Dung lượng tải: TODO (R11).
  - **Model (tải tay, ngoài git):**
    - `wav2lip256.pth` (thư mục Google Drive / Quark trong README LiveTalking) → `vendor/livetalking/models/wav2lip.pth`.
    - `s3fd.pth` (`https://www.adrianbulat.com/downloads/python-fan/s3fd-619a316812.pth`).
    - Dung lượng và license của checkpoint `wav2lip256`: TODO (R1, RISKS L11).
  - **Mã nguồn ngoài:** clone `lipku/LiveTalking` vào `vendor/livetalking/`, nhánh `ailive`. Nơi giữ fork và SHA upstream ghim: TODO (R2).
- **Lưu trữ:**
  - `AVATAR_DIR/character.json` viết tay, có phần `prepare` do CLI ghi. Thư mục nhân vật đã gitignore.
  - File phiên mới `avatar.jsonl`. `latency.jsonl` có thêm trường.
  - Dữ liệu fork tạo ra (ảnh khung, tọa độ mặt) nằm trong `vendor/livetalking/data/avatars/`, ngoài git.
- **Kiểm thử:**
  - pytest của app dùng **fork giả**: server WebSocket trong test, theo [contracts/fork-protocol.md](./contracts/fork-protocol.md). Test
    phủ `SwitchingRenderer`, `character.json` / hồ sơ nguồn gốc, các route mới, và test tích hợp `ShowDirector` + fork giả.
  - Contract test `AvatarRenderer` chạy thêm cho hai renderer mới.
  - Test `ailive_ext` chạy bằng pytest trong venv fork, không cần GPU.
  - Không thêm marker. Suy luận thật, chất lượng miệng và fps kiểm bằng tay theo [quickstart.md](./quickstart.md).
- **Nơi chạy:**
  - Test và chế độ `static` chạy trên mọi máy.
  - `AVATAR_MODE=livetalking` chạy trên GPU laptop (ADR-023).
  - RunPod chỉ dự phòng khi số đo không đạt; báo chi phí và chờ người dùng đồng ý trước (ADR-019).
- **Adapter liên quan:**
  - `AvatarRenderer`: thêm `LiveTalkingRenderer` và `SwitchingRenderer`. Protocol không đổi chữ ký.
  - Protocol tùy chọn mới: `RenderOutcomeSink`, `RenderStatsSource`, cùng lỗi `RendererError(kind)`.
  - `HostLink` (do `StaticRenderer` thỏa).
  - `OutputSink` **không làm** ở 005 (ADR-043).
- **Mục tiêu hiệu năng:**
  - Đích ARCHITECTURE §4: bước lip-sync đến khung đầu 0,8 s; nhân vật 25 khung/giây.
  - Trên laptop, người dùng chấp nhận chậm (ADR-023). Feature bắt buộc **đo và ghi** (FR-019, FR-020, SC-006), không đặt ngưỡng.
  - Bắt buộc: tiếng không đi trước hình (FR-007, SC-003), và bỏ qua lượt dừng trong ≤ 1 s (SC-004).
- **Ràng buộc khác:**
  - Không phát video quay sẵn: clip nền không có tiếng, miệng được tạo lúc nói (Điều I).
  - Nhãn "AI" không tắt được. Giữ watermark "LiveTalking" (RISKS L1).
  - Nhân vật phải gắn đúng khách và có hồ sơ nguồn gốc "người lớn, hư cấu, tạo bằng AI" (FR-004, FR-005).
  - Fork chỉ nghe `127.0.0.1` (RISKS S9).

## Kiểm tra Constitution (cổng)

**Lần 1 (trước Phase 0):** Đạt, không có vi phạm. Ghi chú: thêm dependency phía fork cần ADR; xem Điều VII. **Lần 2 (sau Phase 1):**
Đạt. Bảng dưới là kết quả sau thiết kế.

| Điều | Kết quả | Ghi chú |
|------|---------|---------|
| I. Realtime, nhãn AI, 1 host 1 tài khoản | Đạt | Miệng do Wav2Lip tạo theo tiếng ngay lúc nói. Clip nền câm, chỉ làm nền (FR-006). Không cache khung đã nhép miệng. Nhãn AI vẽ trong `process_frames` của fork trên mọi khung, không có cờ tắt; nhãn rỗng hoặc không phải ASCII thì fork không khởi động (R5, ADR-044). Khi tự về ảnh tĩnh, nhãn hiện bằng CSS như ADR-016. Nhân vật gắn `customer_id`; app từ chối mở khi khác `CUSTOMER_ID` (R13, ADR-045). |
| II. Đồng ý và bảo mật | Đạt | Gương mặt tạo bằng AI, không phải người thật. `prepare` từ chối nhân vật thiếu `adult_fictional_confirmed` hoặc thiếu nguồn gốc của từng clip (data-model §3). Clip, ảnh, `character.json`, `vendor/`, `*.pth` đều ngoài git. Fork không nhận key nào và chỉ nghe localhost. Tiếng ghi âm của US1 là của người đã đồng ý, không lưu lên đĩa (contracts/api.md §1). |
| III. Trả lời có căn cứ | N/A | Không đổi nội dung câu nói, prompt hay guard. |
| IV. Adapter trước | Đạt | Lip-sync là adapter `AvatarRenderer` mới, chọn bằng `AVATAR_MODE`. Lõi chỉ thêm hai lệnh gọi tùy chọn qua `isinstance` (`record_render_outcome`, `render_stats`) và một nhánh `kind` lỗi. Lõi không biết LiveTalking (ADR-046). Chạy riêng được bằng `POST /api/debug/speak-audio` và CLI `prepare` / `check`. Khoảng lặng giữa câu xử lý trong renderer (R15), không đổi lõi. |
| V. Test trước (GPU: laptop trước, RunPod dự phòng) | Đạt | Mọi logic app test được với fork giả, không GPU. Phần thuần Python của fork (xoay clip, cắt khung tiếng, nhãn) có test riêng trong venv fork. Phần GPU chạy laptop trước (quickstart bước 4–10); chỉ hỏi về RunPod khi số đo không đạt. |
| VI. Ngân sách độ trễ | Đạt | Độ trễ cấu trúc ở `batch_size` 16 ≥ 0,84 s cộng thời gian suy luận, vượt 0,8 s của bước lip-sync (R6). Điều VI cho phép số laptop là số tham khảo (ADR-023); spec chỉ bắt đo. Có nút giảm tải: `batch_size`, `LIP_EVERY_N` (R8), `LIVETALKING_LEAD_S` cho khoảng lặng giữa câu (R15). Đo bằng mốc có sẵn, bảng dưới. Không chặn event loop: suy luận ở process fork, app chỉ I/O WebSocket. |
| VII. Đơn giản trước | Đạt (cần duyệt) | Một process mới (fork LiveTalking) là bản chất của ADR-004, không phải hạ tầng thêm. Dependency mới và việc tải model chờ duyệt ADR-048. `SwitchingRenderer` có 2 renderer thật. Protocol tùy chọn chỉ có một nơi thỏa nhưng là chỗ cắm cần thiết để lõi không biết LiveTalking (xem "Theo dõi độ phức tạp"). Không làm `OutputSink`, không WSL hay Docker. |
| VIII. Quan sát được | Đạt | Mốc `avatar_first_frame` = ack `playback_started` câu đầu (R6, ADR-047). `render_stats` mỗi lượt có `render_fps`, `infer_fps`, `clips_used`. Thêm log `avatar_fallback`, `renderer_restarted`, `lipsync_vram_oom`, `lipsync_connected/disconnected`, file `avatar.jsonl`, `kind` lỗi mới vào `errors.jsonl`. Lỗi render không dừng phiên (FR-021, FR-022). |
| IX. Ngôn ngữ và tài liệu | Đạt | Code, comment và `ailive_ext` bằng tiếng Anh. Thông báo lỗi, trang điều khiển, phụ đề bằng tiếng Việt. File có comment tiếng Việt được dịch khi sửa (ADR-022). Chỗ chưa chắc ghi `TODO:` (danh sách cuối research). Sửa ARCHITECTURE §3 (ghi chú tích hợp, `first_playback_at`, `OutputSink`) khi ADR được chốt. |

## Ảnh hưởng ngân sách độ trễ

| Khâu | Ngân sách (ARCHITECTURE §4) | Feature này thay đổi gì | Cách đo |
|------|-----------------------------|-------------------------|---------|
| Lip-sync đến khung đầu | 0,8 s | Từ gần 0 (ảnh tĩnh) lên ≥ `batch_size × 40 ms + 200 ms` + suy luận một lô (bs 16: ≥ 0,84 s + suy luận). Trên 1650 Ti chưa có số. Giảm `LIVETALKING_BATCH_SIZE` để khung đầu ra sớm hơn (R6, R8). | Bước `tts_first_chunk → avatar_first_frame` trong `GET /api/latency`, ≥ 20 lượt (SC-006). `first_frame_s` của `/api/debug/speak-audio` |
| Encode + mạng (WebRTC) | 0,5 s | Thêm encode của aiortc và jitter buffer của Chrome trên localhost. Không nằm trong mốc vì ack ghi lúc gửi khung (R6). | Đo lệch ack ↔ hiển thị một lần bằng quay màn hình 60 fps (quickstart bước 9) |
| Khoảng lặng giữa câu (kịch bản) | p95 ≤ 1,5 s, không lần nào > 5 s (Điều VI) | Mỗi ranh giới câu thêm chừng một lô suy luận (R15). `LIVETALKING_LEAD_S` (mặc định tắt) bù bằng cách gửi câu sau sớm. | `sentence_gap` trong `ShowStats` / log (004), so sánh `LEAD_S=0` với giá trị đã chỉnh |
| Câu đầu show (kịch bản) | ≤ 5 s (Điều VI) | Cộng thêm độ trễ khung đầu ở trên | `segment_requested → avatar_first_frame` |
| TTS đến chunk đầu | 1,0 s | Không đổi code. VieNeu (CPU) chạy cùng fork (GPU + CPU), có thể chậm hơn (RISKS G7) | `first_sentence_to_tts_first_chunk` |
| Tổng comment → miệng | < 5,0 s | Lần đầu đo tổng với nhân vật thật. Trên laptop chỉ ghi số (ADR-023) | `GET /api/latency`, phiên 30 phút (SC-006) |

## Cấu trúc mã nguồn

### Tài liệu của feature
```
specs/005-lipsync-livetalking/
├── spec.md
├── plan.md               # file này
├── research.md           # R1–R15
├── data-model.md         # cấu hình, character.json, hồ sơ nguồn gốc, AvatarModeState, RenderTurnStats, LipsyncHealth
├── contracts/
│   ├── fork-protocol.md  # /ailive/ws app ↔ fork, hành vi fork, script setup/run/prepare, test fork
│   ├── adapters.md       # Protocol mới, LiveTalkingRenderer, SwitchingRenderer, HostLink, factory, so với ARCHITECTURE §3
│   ├── api.md            # HTTP mới/đổi, /ws/host, trang điều khiển
│   └── events.md         # sự kiện bus, log, errors.jsonl, file phiên, .env.example, CLI
├── quickstart.md         # bước 0–10, đánh dấu [không GPU] / [GPU laptop] / [RunPod]
└── tasks.md              # /sdd.tasks
```

### Mã nguồn app
```
src/ai_live/core/protocols.py            # sửa: RenderOutcomeSink, RenderStatsSource, RendererError
src/ai_live/core/config.py               # sửa: CUSTOMER_ID, AVATAR_DIR, LIVETALKING_* (data-model §1), kiểm khi livetalking
src/ai_live/core/events.py               # sửa: EventType.AVATAR_MODE, LIPSYNC_HEALTH
src/ai_live/core/models.py               # sửa: AvatarModeState, RenderTurnStats, LipsyncHealth; TurnLatency thêm render_fps, infer_fps, clips_used
src/ai_live/avatar/static_renderer.py    # sửa: thỏa HostLink (lipsync_session, send_to_host, on_session_change)
src/ai_live/avatar/livetalking_renderer.py  # mới
src/ai_live/avatar/switching_renderer.py # mới
src/ai_live/avatar/character.py          # mới: load_character, validate_for_session, prepare_character
src/ai_live/avatar/factory.py            # mới: create_renderer
src/ai_live/avatar/__main__.py           # mới: CLI prepare / check
src/ai_live/director/show_director.py    # sửa: record_render_outcome, chép render_stats, _render_error_kind đọc exc.kind
src/ai_live/director/script_runner.py    # sửa: record_render_outcome, chép render_stats
src/ai_live/director/latency.py          # sửa: render_fps p50/p95 trong summary
src/ai_live/director/session_log.py      # sửa: avatar.jsonl, trường mới của latency.jsonl
src/ai_live/app/context.py               # sửa: renderer kiểu HostRenderer
src/ai_live/app/main.py                  # sửa: create_renderer thay chỗ ném AvatarModeError
src/ai_live/app/routes.py                # sửa: /api/avatar, /api/avatar/lipsync, /api/host-config, /api/debug/speak-audio, /avatar-image, /health
src/ai_live/app/static/host.html, host.js   # sửa: <video> + WebRTC /offer, phụ đề, tin mode, nhãn CSS khi về ảnh tĩnh
src/ai_live/app/static/control.html, control.js, style.css  # sửa: dải cảnh báo, nút bật lại, ô trạng thái, thử bằng WAV, cột fps
.env.example                             # sửa: khối Avatar / LiveTalking (contracts/events.md §5)
.gitignore                               # sửa: vendor/
pyproject.toml                           # sửa: websockets (sau khi duyệt ADR-048)
scripts/livetalking/setup.ps1            # mới: clone fork, venv 3.12, torch + requirements; in hướng dẫn tải model
scripts/livetalking/run.ps1              # mới: đọc .env, bật fork 127.0.0.1:8010
tests/fixtures/fake_fork.py              # mới: server WebSocket giả theo fork-protocol.md (cạnh fake_host.py)
tests/unit/test_character.py             # mới
tests/unit/test_switching_renderer.py    # mới
tests/unit/test_livetalking_renderer.py  # mới: ack, hết giờ, error, stop, nối lại, boot_id, LEAD_S
tests/unit/test_avatar_cli.py            # mới
tests/unit/test_config.py, test_latency.py, test_events.py  # sửa
tests/contract/test_renderer_contract.py # sửa: chạy cho LiveTalkingRenderer (fork giả) và SwitchingRenderer
tests/integration/test_avatar_api.py     # mới: các route mới
tests/integration/test_show_director.py  # sửa: fallback sau 2 lượt lỗi, bật lại, FR-015/016 với fork giả
tests/integration/test_script_runner.py  # sửa: record_render_outcome mỗi lượt, chép render_stats vào TurnLatency
tests/integration/test_ws_host.py        # sửa: ready + lipsync_session, tin mode
docs/ARCHITECTURE.md, docs/VENDORS.md, docs/RUNPOD.md  # sửa khi ADR-041–048 được chốt
```

### Mã nguồn fork (`vendor/livetalking/`, ngoài git của repo này, nhánh `ailive`)
```
ailive_ext/ingest.py      # /ailive/ws: PCM16 → khung float32 320 mẫu + datainfo, ack, stats, health
ailive_ext/rotation.py    # pick_next: xoay clip theo loại, không lặp clip vừa dùng; ClipScheduler: giữ clip nói LIVETALKING_HOLD_S
ailive_ext/lipskip.py     # LIVETALKING_LIP_EVERY_N: chọn khung suy luận, dán lại miệng (numpy)
ailive_ext/label.py       # vẽ nhãn AI (ASCII, bắt buộc)
ailive_ext/prepare.py     # genavatar từng clip, đếm mặt S3FD, --json
ailive_ext/tests/         # pytest không GPU
(sửa nhỏ: app.py, avatars/base_avatar.py: gắn route, xoay clip, giữ clip nói, chuyển dần, nhãn trong process_frames)
```

## Phase 0: Nghiên cứu → [`research.md`](./research.md)

- R1 Wav2Lip `wav2lip256` · R2 fork chạy process riêng, venv riêng · R3 WebSocket PCM `/ailive/ws` · R4 WebRTC của LiveTalking trong `/host`
- R5 nhãn AI trong khung, giữ watermark · R6 mốc `avatar_first_frame` · R7 chuẩn bị, xoay vòng, chuyển clip · R8 giảm tải
- R9 tự về ảnh tĩnh và bật lại · R10 thời gian chờ, lỗi · R11 CUDA/driver · R12 thử bằng WAV · R13 nhân vật gắn khách
- R14 test không GPU · R15 khoảng lặng giữa câu

## Phase 1: Thiết kế

- [data-model.md](./data-model.md): cấu hình, `character.json` và trạng thái chuẩn bị, hồ sơ nguồn gốc, `AvatarModeState`, `RenderTurnStats`,
  `LipsyncHealth`.
- [contracts/fork-protocol.md](./contracts/fork-protocol.md): giao thức app ↔ fork và hành vi fork.
- [contracts/adapters.md](./contracts/adapters.md): Protocol, các lớp, factory. Bảng khác biệt so với ARCHITECTURE §3 có 6 điểm, đều qua
  ADR-042/043/044/046.
- [contracts/api.md](./contracts/api.md), [contracts/events.md](./contracts/events.md): HTTP, `/ws/host`, sự kiện, log, `.env.example`, CLI.
- [quickstart.md](./quickstart.md): bước 0, 2 không cần GPU; bước 1, 3 chờ duyệt ADR-048; bước 4–10 trên GPU laptop; RunPod chỉ sau khi hỏi
  chi phí.

## ADR cần ghi (đã thêm vào `docs/DECISIONS.md`, trạng thái Đề xuất)

- **ADR-041:** model nhép miệng giai đoạn laptop là Wav2Lip (`wav2lip256` của LiveTalking); không dùng MuseTalk trên laptop. Chốt phần
  "chọn model" của ADR-004 cho giai đoạn này; ghi số đo SC-006 vào ADR này.
- **ADR-042:** cách tích hợp fork. Clone `lipku/LiveTalking` vào `vendor/livetalking/` (gitignore, nhánh `ailive`), venv riêng Python 3.12,
  process riêng bật bằng `scripts/livetalking/run.ps1`, phần sửa nằm trong `ailive_ext/`. Trả lời TODO của ADR-004.
- **ADR-043:** đường tiếng và hình. App đẩy PCM16 16 kHz vào `/ailive/ws` và nhận ack; WebRTC của LiveTalking phát trong `/host`; không làm
  `OutputSink` ở 005.
- **ADR-044:** nhãn "AI" vẽ trong khung hình của fork (ASCII, không tắt được); giữ watermark "LiveTalking".
- **ADR-045:** hồ sơ nhân vật `character.json` gắn `customer_id` + `CUSTOMER_ID`; chuẩn bị từng clip; xoay vòng clip và chuyển dần ở fork.
- **ADR-046:** `SwitchingRenderer` và Protocol tùy chọn `RenderOutcomeSink`, `RenderStatsSource`, `RendererError(kind)`; tự về ảnh tĩnh sau
  `AVATAR_FALLBACK_AFTER` = 2 lượt lỗi, bật lại bằng `POST /api/avatar/lipsync`.
- **ADR-047:** mốc `avatar_first_frame` ở chế độ nhép miệng = ack `playback_started` của câu đầu; `LIVETALKING_LEAD_S` để giảm khoảng lặng
  giữa câu.
- **ADR-048:** dependency và model cần duyệt: `websockets` khai báo trực tiếp; venv fork (torch 2.9.1 cu128/cu126 + requirements LiveTalking);
  tải tay `wav2lip256.pth`, `s3fd.pth`. **Chặn bước 1, 3 của quickstart và phần implement cần fork.**

## Rủi ro mới (đã thêm vào `docs/RISKS.md`)

- **L1 (cập nhật):** LiveTalking Apache-2.0. README yêu cầu watermark và logo khi đăng video trên các nền tảng Trung Quốc. Chưa rõ với
  YouTube/Shopee.
- **L11:** license và nguồn gốc checkpoint `wav2lip256.pth` (do tác giả LiveTalking huấn luyện lại, phát qua Google Drive / Quark).
- **G9:** bánh xe torch cu128 không chạy trên driver 565.90, hoặc thiếu kernel sm_75.
- **G10:** 1650 Ti dưới 25 khung/giây: độ trễ khung đầu và khoảng lặng giữa câu tăng.
- **G11:** RAM laptop không đủ nạp mọi clip (≈ 145 MB một clip chưa nén).
- **G12:** LiveTalking không chạy trên Windows native, hoặc thiếu bánh xe `aiortc` / `av` cho Windows.
- **G13:** lệch giữa ack `playback_started` và lúc Chrome vẽ khung làm mốc `avatar_first_frame` sớm hơn thực tế.
- **G14:** gánh bảo trì fork: rebase upstream, gói thừa trong requirements.
- **S9:** fork không có xác thực; bind ra ngoài localhost thì người lạ đẩy tiếng vào nhân vật được.

## Theo dõi độ phức tạp

| Vi phạm hoặc phần thêm | Vì sao cần | Phương án đơn giản hơn đã bị loại vì |
|------------------------|------------|--------------------------------------|
| Process thứ hai (fork LiveTalking) với venv riêng | torch/CUDA và requirements của LiveTalking rất nặng, có bản ghim riêng (`websockets==12.0`...); trộn vào `uv.lock` của app sẽ xung đột và làm test app phải cài torch | Import LiveTalking vào process app: xung đột phiên bản, suy luận GPU chung event loop với app |
| Protocol tùy chọn `RenderOutcomeSink` / `RenderStatsSource` (mới có 1 nơi thỏa) | Lõi phải báo kết quả render và đọc fps mà không biết LiveTalking (Điều IV) | Lõi gọi thẳng `SwitchingRenderer`: lõi phụ thuộc lớp avatar cụ thể; renderer tự đoán lỗi từ trong `speak` thì không thấy lỗi giả lập của `check_render` |
| Ngân sách bước lip-sync 0,8 s có thể vượt trên laptop | Phần cứng 4 GB; người dùng chấp nhận chậm (ADR-023) | Thuê RunPod ngay: tốn tiền trước khi khách đồng ý (ADR-019) |

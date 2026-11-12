# Quickstart: 005-lipsync-livetalking

- **Ngày:** 2026-11-06 · **Plan:** [plan.md](./plan.md)
- Ký hiệu: **[không GPU]** chạy được trên mọi máy; **[GPU laptop]** cần GTX 1650 Ti của laptop (ADR-023); **[RunPod]** chỉ khi laptop
  không đủ, **hỏi chi phí và chờ người dùng đồng ý trước khi bật pod** (CLAUDE.md, ADR-019).
- Các bước 1, 3 chỉ làm sau khi người dùng duyệt dependency và việc tải model (ADR-048).

## 0. Test tự động [không GPU]

```powershell
uv run pytest                                   # gồm fork giả, SwitchingRenderer, character.json, các route mới
uv run ruff check . ; uv run ruff format --check .
```

Kỳ vọng: xanh hết; không test nào cần `vendor/livetalking` hay GPU.

## 1. Dựng fork LiveTalking [GPU laptop: kiểm CUDA]

```powershell
powershell scripts/livetalking/setup.ps1        # clone vào vendor/livetalking, venv Python 3.12, torch cu128 + requirements
vendor/livetalking/.venv/Scripts/python -c "import torch; print(torch.__version__, torch.cuda.is_available(), torch.cuda.get_device_name(0), torch.cuda.get_arch_list())"
vendor/livetalking/.venv/Scripts/python -m pytest vendor/livetalking/ailive_ext/tests    # [không GPU]
```

Kỳ vọng: `True`, `GeForce GTX 1650 Ti`, danh sách arch có `sm_75`. Sai thì làm theo research R11 (cu126, rồi mới hỏi về driver). Ghi
dung lượng đã tải vào ADR-048.

## 2. Kiểm hồ sơ nhân vật [không GPU]

1. Viết `assets/avatars/demo_host_01/character.json` theo data-model §2 (`customer_id: "demo_customer_01"`, 2 clip `idle`, 2 clip `talk`,
   bản gốc, không `_pingpong`).
2. Bổ sung `provenance.json`: `adult_fictional_confirmed: true`, mục nguồn gốc cho từng clip (data-model §3).
3. `uv run python -m ai_live.avatar check assets/avatars/demo_host_01` → "Hồ sơ hợp lệ".
4. Thử lỗi (US1 #5, #6): xóa tạm `customer_id` → bị từ chối, nêu thiếu khách; đổi `kind` của mọi clip thành `talk` → báo thiếu clip chờ.

## 3. Tải model [cần duyệt ADR-048; tải tay]

- `wav2lip256.pth` từ thư mục Google Drive / Quark ghi trong README LiveTalking → `vendor/livetalking/models/wav2lip.pth`.
- `s3fd.pth` từ `https://www.adrianbulat.com/downloads/python-fan/s3fd-619a316812.pth` →
  `vendor/livetalking/avatars/wav2lip/face_detection/detection/sfd/s3fd.pth`.
- Ghi sha256 hai file vào ADR-048. Không commit (đã gitignore `*.pth`, `vendor/`).

## 4. Chuẩn bị nhân vật (US1 #5, FR-003) [GPU laptop]

```powershell
uv run python -m ai_live.avatar prepare assets/avatars/demo_host_01
```

Kỳ vọng: bảng 4 clip `ready`, số khung 121, kích thước 480×832 (rộng×cao; bảng in `[832, 480]` theo cao×rộng); `character.json` có `prepare.status: ready`. Ghi thời gian chạy và RAM.
Thử lỗi FR-003: thêm một clip có 2 mặt (hoặc không mặt) → `failed`, nêu tên clip và khung.

Kết quả 2026-11-07 (GTX 1650 Ti 4 GB, T044):

| Lần chạy | Thời gian | RAM đỉnh | VRAM đỉnh | Kết quả |
|---|---|---|---|---|
| `demo_host_01`, S3FD batch 16 (mặc định upstream) | 759 s | ~3,2 GB | 3 895 MiB | `ready`, 4 clip × 121 khung, 832×480 (cao×rộng), 24 fps |
| `demo_host_01`, S3FD batch 4 (`FACE_BATCH`) | 145 s | 1,3 GB | 2 143 MiB | `ready`, như trên |
| Bản sao 2 clip (20 + 40 khung), `talk_01` đen từ khung 25 | ~8 phút (còn batch 16) | | | `failed`: `[face_count] talk_01: Khung 25 không thấy mặt` (khung 25); không tạo thư mục avatar nào |

- Batch 16 ở khung 832×480 cần ~4,8 GB VRAM. Trên card 4 GB, Windows tràn sang bộ nhớ chung thay vì báo OOM, nên cơ chế tự giảm batch
  không chạy; riêng batch đầu mất 466 s. Batch 4 chỉ cần ~2,5 GB và tốn ~0,1 s/khung, nên `prepare.py` dùng batch 4 cho cả bước kiểm
  lẫn genavatar.
- Clip xuất ở 24 fps, còn fork phát 25 fps: vòng clip chạy nhanh hơn ~4%. Người dùng xem ở bước 5 (2026-11-10) không nêu khác biệt,
  T045 đạt; giữ 24 fps.
- `prepare` không hiện tiến độ trong lúc chạy (app giữ stderr của fork, chỉ in dòng cuối khi lỗi).

### 4b. Làm mượt clip nền trước `prepare` (thêm 2026-11-10, T045)

Clip do Wan 2.2 tạo bị rung nhẹ liên tục: hướng chuyển động giữa hai khung liền nhau đảo chiều gần như mỗi khung, ~0,3–0,5 px. Rung có
sẵn trong file mp4 gốc, không do fork hay WebRTC. Làm mượt theo thời gian bằng PyAV + numpy có sẵn trong venv fork (không thêm dependency),
ghi ra `<tên>_smooth.mp4`, giữ file gốc, rồi trỏ `file` trong `character.json` sang bản mượt và chạy lại `prepare`:

```powershell
vendor/livetalking/.venv/Scripts/python scripts/avatar_clips/smooth_clips.py --radius 2 assets/avatars/demo_host_01/clips/idle_01.mp4 assets/avatars/demo_host_01/clips/idle_02.mp4
vendor/livetalking/.venv/Scripts/python scripts/avatar_clips/smooth_clips.py --radius 1 assets/avatars/demo_host_01/clips/talk_02.mp4
```

Số đo (optical flow trên khung xám; "rung" = độ đổi vận tốc giữa hai khung liền nhau, "chuyển động" = dịch chuyển trong 0,5 s):

| Clip | Rung gốc | Mượt 3 khung | Mượt 5 khung | Chuyển động giữ lại (3 khung) | Độ nét còn lại (3 khung) |
|---|---|---|---|---|---|
| idle_01 | 0,380 | 0,112 | 0,078 | 94% | 79% |
| idle_02 | 0,366 | 0,138 | | 97% | 70% |
| talk_01 | 0,641 | 0,214 | | 94% | 52% (nhòe khi cử động nhanh) |
| talk_02 | 0,328 | 0,226 | | 95% | 75% |

Người dùng xem video so sánh và chọn: clip chờ mượt 5 khung; clip nói chỉ dùng `talk_02` mượt 3 khung, đặt lên đầu danh sách (US1 chỉ dùng
clip đầu của mỗi loại); `talk_01` giữ bản gốc, chưa dùng tới US3. `provenance.json` ghi bản mượt vào `files` và `post_process` của từng
clip. `prepare` lại: 134 s, 4 clip `ready`.

## 5. Bật fork và app (US1 #1, #4) [GPU laptop]

Terminal 1:
```powershell
powershell scripts/livetalking/run.ps1          # đọc .env; nghe 127.0.0.1:8010
```
Terminal 2 (`.env`: `AVATAR_MODE=livetalking`, `CUSTOMER_ID=demo_customer_01`, `AVATAR_ID=demo_host_01`):
```powershell
uv run uvicorn ai_live.app.main:app --port 8000
```
Mở Chrome `http://127.0.0.1:8000/host`, bấm "Bắt đầu"; mở `http://127.0.0.1:8000/` (trang điều khiển). Kỳ vọng: video nhân vật chạy clip
chờ, nhãn "AI" trong khung, watermark "LiveTalking" nhỏ ở góc; trang điều khiển "Nhép miệng: đã nối".

Thử FR-004: đổi `CUSTOMER_ID=khach_khac` → app không mở, báo nhân vật thuộc khách khác.

Kết quả 2026-11-07 (GTX 1650 Ti 4 GB, T045, phần máy tự kiểm):

- Fork: `/ailive/health` trả `ok` sau ~6 s, VRAM 2 656 MB khi chờ (nvidia-smi 2 719 MiB). App: `/api/host-config` trả `livetalking`, nhãn
  "AI" góc trên phải.
- FR-004: `CUSTOMER_ID=khach_khac` → app dừng lúc khởi động: `Nhân vật demo_host_01 thuộc khách 'demo_customer_01', không phải khách
  đang cấu hình CUSTOMER_ID='khach_khac'`.
- Thay Chrome bằng một client WebRTC (aiortc, `POST /offer` như `host.js`): khung đầu tới sau 6,5 s; nhận ~25 fps, 480×832. Chờ 12 s
  (~2,5 vòng clip chờ): độ lệch giữa hai khung liền nhau trung vị 1,19, lớn nhất 3,16 (thang 0–255), không có cú nhảy ở chỗ lặp. Miệng
  khép khi chờ. 36/36 khung chụp có ô nhãn "AI" góc trên phải; watermark "LiveTalking" ở góc trên trái.
- Còn cần người dùng xem bằng mắt trên Chrome: clip chờ trông tự nhiên, chỗ lặp, khác biệt 24/25 fps (bước 4). Dòng "Nhép miệng: đã nối"
  trên trang điều khiển thuộc T059 (US2), chưa có ở phase này.

Kết quả 2026-11-10 (T045, người dùng xem trên Chrome):

- Lần 1 với clip gốc: nhân vật "rung đều liên tục". Mở `idle_01.mp4` gốc bằng trình phát cũng rung y như vậy, nên lỗi nằm ở clip, không
  ở fork hay WebRTC. Số đo frame diff của lần 2026-11-07 không bắt được kiểu rung này vì mỗi khung chỉ lệch dưới 1 px.
- Làm mượt clip theo bước 4b, `prepare` lại, bật lại fork và app. Lần 2: hết rung; clip chờ, miệng khép, nhãn "AI" trong khung,
  watermark, chỗ lặp đều đạt. FR-004 chạy lại cùng ngày (app thứ hai ở cổng 8001 với `CUSTOMER_ID=khach_khac`) vẫn dừng lúc khởi động
  với cùng thông báo. T045 đạt.

## 6. US1: nhép miệng theo tiếng có sẵn (SC-001) [GPU laptop]

1. Ghi 10 đoạn tiếng Việt 5–15 s (người vận hành tự đọc, Giả định của spec). Đổi định dạng nếu cần:
   ```powershell
   vendor/livetalking/.venv/Scripts/python -c "import soundfile as sf, resampy, sys; d, sr = sf.read(sys.argv[1]); d = d.mean(axis=1) if d.ndim > 1 else d; sf.write(sys.argv[2], resampy.resample(d, sr, 16000), 16000, subtype='PCM_16')" in.wav out.wav
   ```
2. Trang điều khiển → khu debug → "Thử bằng tiếng có sẵn" từng file. Chấm bằng mắt: miệng khớp tiếng (đạt ≥ 8/10), không thấy miệng mở khi im.
3. Ghi `first_frame_s`, `render_fps` trả về.
4. Trường hợp biên: một WAV > 30 s (nhép miệng hết câu, không tràn bộ nhớ, xem VRAM trong `GET /api/avatar`) và một WAV toàn im lặng
   (miệng gần như khép, không báo lỗi).

Kết quả 2026-11-07 (T046, phần máy tự kiểm, tiếng **tổng hợp** chứ chưa phải giọng thật; client aiortc giả trang `/host`, gọi
`POST /api/debug/speak-audio` qua app):

| WAV | HTTP | `first_frame_s` | `render_fps` | VRAM fork sau đó |
|---|---|---|---|---|
| 8 s, nhiễu theo nhịp âm tiết 4 Hz | 200 | 1,08 | 24,9 | 2 656 MB |
| 6 s im lặng | 200 | 0,95 | 25,1 | 2 656 MB |
| 32 s, nhiễu theo nhịp âm tiết | 200 | 1,19 | 25,0 | 2 656 MB |

- Gửi thẳng vào fork (`/ailive/ws`): 35 s → 875 khung, suy luận 34,8 fps, phát 25,0 fps, không OOM; 4 s → suy luận 38,8 fps.
- `GET /api/avatar` thuộc T058 (US2), chưa có; VRAM lấy từ `/ailive/health` của fork.
- Lần chạy đầu `render_fps` trả `null`: `speak` trả về ngay khi có `sentence_played`, trước khi `stats` của câu đó tới. Đã sửa
  `LiveTalkingRenderer` chờ `stats` tối đa 0,5 s (test `test_render_stats_ready_when_speak_returns`).
- Còn cần người dùng: 10 WAV giọng Việt thật 5–15 s, chấm bằng mắt ≥ 8/10 khớp (SC-001), xem miệng khép khi im.

Kết quả 2026-11-11 (T046, giọng VieNeu `Thùy Dung` theo giả định sửa của spec 2026-11-10; fork + app chạy trên laptop, Chrome mở
`/host`, clip nói `talk_02` đã làm mượt ở bước 4b). File trong `out/t046/` (ngoài git): `td_01`–`td_10` tạo bằng
`uv run python -m ai_live.tts say "<câu>" --out out/t046/td_NN.wav`, `long_01` là một đoạn văn 34,9 s, `silence_6s` là 6 s số 0.

| WAV | Dài (s) | HTTP | `first_frame_s` | `render_fps` | VRAM fork sau đó |
|---|---|---|---|---|---|
| td_01 | 6,56 | 200 | 0,97 | 25,0 | 2 656 MB |
| td_02 | 5,04 | 200 | 1,16 | 25,1 | 2 656 MB |
| td_03 | 6,88 | 200 | 0,95 | 25,1 | 2 656 MB |
| td_04 | 6,96 | 200 | 0,92 | 24,8 | 2 656 MB |
| td_05 | 5,52 | 200 | 1,00 | 25,2 | 2 656 MB |
| td_06 | 6,56 | 200 | 0,95 | 25,2 | 2 656 MB |
| td_07 | 5,36 | 200 | 1,05 | 25,0 | 2 656 MB |
| td_08 | 5,28 | 200 | 1,02 | 25,1 | 2 656 MB |
| td_09 | 5,04 | 200 | 1,00 | 25,3 | 2 656 MB |
| td_10 | 5,12 | 200 | 1,02 | 25,0 | 2 656 MB |
| long_01 | 34,93 | 200 | 1,05 | 25,0 | 2 656 MB |
| silence_6s | 6,00 | 200 | 1,03 | 25,1 | 2 656 MB |

- Người dùng xem trên Chrome (4 lượt bấm từ trang điều khiển, rồi 12 lượt trên gọi `POST /api/debug/speak-audio`): "khi có âm thanh
  miệng chuyển động và không có thì không mở miệng". `first_frame_s` 0,92–1,16 s; `render_fps` 24,8–25,3; VRAM không tăng sau đoạn
  34,9 s, không lỗi với đoạn im lặng.
- Người dùng chấm từng đoạn: 10/10 khớp; `long_01` nhép hết câu; `silence_6s` miệng khép. **SC-001 đạt, T046 đạt.**

Kết quả 2026-11-11 (T047, SC-002, FR-010):

- Cách chụp: Chrome headless (không dùng màn hình của người vận hành) mở `/host`, bấm "Bắt đầu" qua Chrome DevTools Protocol,
  chụp đúng khung `#video` (`Page.captureScreenshot`, 480×832). 6 ảnh lúc chờ cách nhau ngẫu nhiên 0,5–3 s, rồi phát `long_01`
  (34,9 s) qua `/api/debug/speak-audio` và chụp 6 ảnh ở thời điểm ngẫu nhiên trong 3–32 s của đoạn nói (15:47–15:48).
  `first_frame_s` 1,0; `render_fps` 25,0. Ảnh có gương mặt người mẫu nên để ngoài git (thư mục tạm của phiên).
- 12/12 ảnh có ô nhãn "AI" ở góc trên phải, nằm trong khung hình nhân vật; cả 12 ô cắt ra giống nhau (tỉ lệ điểm đen 0,88,
  trắng 0,08). Logo "LiveTalking" ở góc trên trái.
- Trong lúc video chạy, nhãn CSS dự phòng `#ai-label` bị ẩn (`display: none`, đo 3 lần), nên nhãn thấy trong ảnh là nhãn fork
  ghép thẳng vào khung hình, không phải lớp phủ của trang web (FR-010).
- **SC-002 đạt (12/12), T047 đạt.**

## 7. US2: show kịch bản ở chế độ nhép miệng [GPU laptop]

1. Bắt đầu show (004). Kỳ vọng: phụ đề hiện đúng câu đang nói, tạm dừng / tiếp tục / bỏ qua chạy như cũ (FR-015). Giữa hai câu của cùng
   phân đoạn nhân vật giữ clip nói với miệng khép, không về clip chờ (US2 #1, `LIVETALKING_HOLD_S`); quay màn hình để xem.
2. Bỏ qua lượt đang nói 5 lần: tiếng, miệng, phụ đề dừng ≤ 1 s, về clip chờ (SC-004). Đo bằng quay màn hình.
3. ≥ 20 lượt: không lượt nào tiếng chạy xong trước khi miệng bắt đầu (SC-003); xem `GET /api/latency`.
4. Lỗi giả lập (SC-005): `POST /api/debug/fault {"step":"render","mode":"error","count":1}` → lượt đó lỗi, lượt sau chạy. Lặp với `count: 2`
   → từ lượt thứ 3 trang host đổi sang `face.png` + Web Audio + nhãn CSS, trang điều khiển hiện dải cảnh báo. Bấm "Bật lại nhân vật nhép
   miệng" → lượt kế tiếp quay lại video.
5. Tắt fork (Ctrl+C ở terminal 1) giữa show → 2 lượt lỗi rồi tự về ảnh tĩnh, show không dừng. Bật lại fork, bấm "Bật lại" → video quay lại,
   log `renderer_restarted`.

Kết quả 2026-11-12 (T062, bước 7.1–7.3; laptop chạy pin, chế độ Balanced). Cách đo không cần người xem: bộ ghi luồng của fork (§11) ghi
khung + tiếng + thẻ câu; Chrome mở `/host` qua Chrome DevTools, một đoạn script đo mức tiếng của luồng WebRTC, phụ đề và khung hiển thị
theo giờ thật; script lái gọi `/api/show/start`, `/api/pause`, `/api/resume`, `/api/comments`, `/api/skip`. File trong `out/selfcheck/`
(ngoài git, có mặt và giọng người mẫu).

| Mục | Kết quả | Đạt? |
|---|---|---|
| Show 7 phút | 31 phân đoạn, 75 câu, phụ đề hiện đúng câu đang nói | Đạt |
| Tạm dừng / tiếp tục (FR-015) | Chạy như 004. Lỗi tìm ra: dừng lúc một câu đã gửi fork mà chưa phát thì câu đó vẫn phát +1,41 s sau khi dừng. Đã sửa (tasks T062); chạy lại 12 lần dừng/tiếp tục: không câu nào bắt đầu trong lúc dừng, câu bị giữ lại được nói lại đúng một lần | Đạt sau sửa |
| Comment hỏi giá (US2 #2) | Trả lời đúng giá trong dữ liệu (259.000đ), chen giữa hai câu kịch bản | Đạt |
| Bỏ qua 5 lần (SC-004 ≤ 1 s) | Trước sửa: tiếng còn 1,0–1,5 s. Sau sửa: tiếng tắt 0,00–0,56 s sau lệnh, phụ đề xóa ngay | Đạt sau sửa |
| SC-003 (≥ 20 lượt) | 80 câu trong bản ghi, không câu nào có thẻ kết thúc trước thẻ bắt đầu | Đạt |
| Giữ clip nói giữa hai câu cùng phân đoạn (US2 #1) | Cả 49 khoảng nghỉ về `idle_01` (chưa có `ClipScheduler`) | **Chưa đạt**, chờ T064–T066 (đạt ở T067: 0/49, xem bước 8) |
| Khựng hình | 21 lần khung đứng > 200 ms trong 7 phút | Ghi nhận, xử lý ở US4 (T072–T075) |

- Ở các lần chạy sau, tiếng trễ hơn phụ đề 0,8–1,1 s ngay từ đầu show (lần đầu 0,25 s) và số khung hiển thị/giây thấp hơn: có mặt cả
  trước khi bỏ qua nên không do bản sửa; nghi do laptop chạy pin. TODO: chạy lại khi cắm sạc, chế độ Best performance, để xác nhận.

Kết quả 2026-11-12 (T063, bước 7.4–7.5), cùng show đang chạy; kiểm trang host và trang điều khiển bằng Chrome DevTools, log app:

| Mục | Kết quả | Đạt? |
|---|---|---|
| Lỗi `count: 1` | Một câu `script_error` (`fault_injected`), câu sau phát bình thường, vẫn video, `consecutive_errors` về 0 | Đạt |
| Lỗi `count: 2` (SC-005) | `avatar_fallback`, `GET /api/avatar` báo `active: static`, `reason: render_errors`; trang host hiện `face.png` + nhãn CSS "AI"; trang điều khiển hiện "Nhân vật nhép miệng lỗi 2 lượt liền, đang dùng ảnh tĩnh." + nút bật lại; show không dừng | Đạt |
| Bấm "Bật lại nhân vật nhép miệng" | `avatar_lipsync_enabled`, video quay lại ngay, nhãn AI trong khung hình | Đạt |
| Tắt fork giữa show | Mất kết nối → câu đang phát và câu đã xếp lỗi (`lipsync_unavailable`), về ảnh tĩnh cùng lúc; show nói tiếp bằng ảnh tĩnh | Đạt |
| Bật lại fork | Trang host tự nối lại WebRTC, app tự nối `/ailive/ws`, log `renderer_restarted` (boot_id mới); vẫn ảnh tĩnh tới khi bấm bật lại (`POST /api/avatar/lipsync`) | Đạt |
| Video sau khi bật lại | Lỗi tìm ra: luồng mới đến lúc video đang ẩn và tắt tiếng nên Chrome không tự phát; bật lại thì video đứng ở khung đầu (nhãn CSS vẫn hiện nên không mất nhãn). Đã sửa `host.js` (`showVideo` gọi `play()`); chạy lại tắt/bật fork: video phát ngay, không cần tải lại trang | Đạt sau sửa |

## 8. US3: clip chờ, xoay vòng, chuyển clip (SC-007, SC-008) [GPU laptop]

- Để chờ 3 phút rồi 10 lượt nói, quay màn hình. Đếm lần giật ở chỗ lặp / chuyển clip (đạt ≤ 1). Nếu giật: chỉnh `LIVETALKING_TRANSITION_S`; nếu về clip chờ giữa hai câu: nâng `LIVETALKING_HOLD_S`.
- Xem `clips_used` trong `GET /api/latency` (lượt comment) hoặc `clip` trong bản ghi §11 (câu kịch bản): hai lượt liền nhau đã về clip
  chờ ở giữa không trùng clip nói (có 2 clip); câu kịch bản liền nhau trong khoảng giữ thì nói tiếp trên cùng clip (spec phiên 2026-11-12).
- SC-008: cho ≥ 3 người ngoài dự án xem đoạn chờ 1 phút, hỏi "trông như đang sống không".

Kết quả 2026-11-12 (T067, laptop chạy pin; bộ ghi luồng §11 thay cho quay màn hình). Script lái: chờ rồi `POST /api/show/start` với
`REPLY_ENGINE=fake`, giọng VieNeu thật. `GET /api/latency` không có `clips_used` cho câu kịch bản (chỉ đếm lượt comment), nên clip của
từng câu đọc từ `clip` + thẻ câu trong `<tên>.jsonl` của bản ghi. Bản ghi trong `out/selfcheck/` (ngoài git).

| Lần chạy | Code | Giật (seams) | Câu liền nhau cùng clip nói | Khoảng nghỉ giữa câu hiện clip chờ | Đổi clip nói → clip nói | Miệng r |
|---|---|---|---|---|---|---|
| t067 (chờ 3 phút + 4 phút show, 48 câu) | T066: clip mới ở mỗi `seq 0`, giữ 1,5 s | 0 | 0/47 | 3/49 | 44 | 0,122 |
| t067b (chờ 3 phút + 4 phút show, 48 câu) | sau sửa: giữ clip qua các câu, đổi sau một vòng, giữ 2,5 s | 0 | 25/47 | 0/49 | 22 | 0,082 |
| t067c (chờ 20 s + 4 phút show, 44 câu) | như t067b | 0 | 23/43 | 0/49 | 21 | 0,075 |
| smoke6 (2 câu cách 7 s) | như t067b | 0 | — (2 lượt khác clip: `talk_01` rồi `talk_02`) | về chờ sau 2,5 s, đúng | 0 | 0,201 |

- **SC-007 đạt:** 0 chỗ giật ở mọi lần chạy (đổi clip, lặp đi tới đi lùi, nói ↔ chờ). Đoạn chờ 3 phút: clip chờ đổi đều mỗi ~10,2 s
  (`idle_01` ↔ `idle_02`, đúng một vòng đi tới đi lùi 242 khung).
- Lỗi tìm ra ở lần t067 (code T066): mỗi câu kịch bản là một `utterance_id` riêng nên câu nào cũng tới fork là `seq 0`, clip nói đổi ở
  mọi câu và luôn chạy lại từ khung 0: 3 giây đầu của hai clip nói lặp lại suốt show, và mỗi câu có một lần trộn chồng hình. Giữ 1,5 s
  không đủ cho khoảng nghỉ p95 2,84 s nên 3 khoảng nghỉ thoáng về clip chờ. Đã sửa (spec phiên 2026-11-12, fork-protocol §4): câu
  bắt đầu trong khoảng giữ nói tiếp trên clip đang giữ; clip nói chỉ đổi khi đã chạy hết một vòng và tới ranh giới câu;
  `LIVETALKING_HOLD_S=2.5`.
- **Miệng r thấp hơn sau sửa (0,08 so với 0,12), không do bộ lập lịch mà do nội dung clip:** `talk_02` từ khung ~64 và `talk_01` khung
  ~32–60 có đầu ngửa / nghiêng, miệng dán lên mở chỉ khoảng một nửa (độ mở khi to tiếng 0,0032–0,0036 so với 0,0052–0,0073 ở đoạn mặt
  thẳng, bản ghi t067c). Code cũ luôn bắt đầu câu ở khung 0 (mặt thẳng) nên ít gặp đoạn này. Khung giữ clip nói lúc im lặng có miệng
  khép như clip chờ (không mấp máy). TODO: người dùng xem lại hai clip nói; đề xuất cắt chỉ lấy đoạn mặt thẳng hoặc làm lại clip nói
  quay mặt thẳng suốt clip (gói duyệt).
- `LIVETALKING_TRANSITION_S` giữ 0,3 (không giật). SC-008 (T068) cần người xem ngoài dự án: chưa làm.

## 9. US4: số đo và chạy 30 phút (SC-006) [GPU laptop]

- Chạy show 30 phút. Ghi: `render_fps`, `infer_fps` p50/p95, bước `tts_first_chunk → avatar_first_frame` p50/p95, cả lượt p50/p95, VRAM đỉnh
  (`avatar.jsonl`), số lần `vram_oom` / `renderer_restarted`; khoảng lặng giữa câu p95 và câu đầu show (`segment_requested →
  avatar_first_frame`) từ `GET /api/show` / `GET /api/latency`. Ghi vào ADR-041 và bảng ngay dưới bước này (spec SC-006 chỉ trỏ tới).
- Nếu lặng giữa câu p95 > 1,5 s: đề xuất `LIVETALKING_LEAD_S` (gợi ý bằng độ trễ khung đầu p50) cho người dùng duyệt, chạy lại và so
  sánh (R15).
- Đo lệch ack ↔ hiển thị (R6): ≥ 10 câu. _Đã làm 2026-11-12 (T074) bằng đầu đo trong Chrome thay cho quay màn hình 60 fps: WebAudio bắt
  lúc tiếng bắt đầu sau im lặng, `requestVideoFrameCallback` cho độ trễ khung nhận → vẽ; cách làm và số ở research R6._
- Chỉnh `LIVETALKING_BATCH_SIZE` (16, 8, 4) và nếu fps < 25 thử `LIVETALKING_LIP_EVERY_N=2`, rồi mới tới bộ clip nhỏ hơn (R8, hỏi
  người dùng cách tạo); ghi bảng so sánh.
- Nếu mọi cách đều dưới 25 khung/giây và người dùng thấy không đạt: dừng, báo người dùng, **hỏi chi phí trước khi tính [RunPod]** theo `docs/RUNPOD.md`.

### Kết quả T073 (2026-11-12, phiên `20261112-192347`)

Điều kiện: GTX 1650 Ti, fork `477d4e4`, `LIVETALKING_BATCH_SIZE=16`, `LIVETALKING_LIP_EVERY_N=1`, `LIVETALKING_LEAD_S=0`,
`LIVETALKING_HOLD_S=2.5`, `TTS_PROVIDER=vieneu` (CPU), `REPLY_ENGINE=fake` (không tính thời gian LLM), Chrome thật nhận WebRTC. Nguồn
điện lúc chạy không ghi lại (lúc 20:10 cùng ngày máy chạy pin). Chạy 20 lượt bình luận lúc host rảnh, rồi show kịch bản 30 phút
(12:28:53–12:59:00 UTC).

| Chỉ số | 20 lượt bình luận | Show 30 phút |
|---|---|---|
| Kết quả | 20 xong, 0 lỗi | 322 câu nói, 0 lỗi tts/render, 3 câu bị ngắt; 108 phân đoạn xong, 1 bỏ |
| `render_fps` p50 / p95 | 17,97 / 19,46 | 25,14 / p5 23,83 (thấp nhất 17,62) |
| `infer_fps` p50 / p95 | 24,75 / 26,38 | 25,40 / p5 23,50 |
| `first_sentence → tts_first_chunk` p50 / p95 | 0,547 / 0,732 s | (TTS lấy trước, không so được) |
| `tts_first_chunk → avatar_first_frame` p50 / p95 | 1,289 / 1,714 s | (TTS lấy trước, không so được) |
| Cả lượt p50 / p95 | 1,836 / 2,147 s | — |
| Câu đầu show | — | 1,64 s (≤ 5 s, đạt) |
| Lặng giữa câu (`sentence_gap`, n = 321) | — | trung vị 2,0 s, p95 2,98 s, lớn nhất 3,16 s (vượt 1,5 s) |
| `vram_oom` / `renderer_restarted` | 0 / 0 | 0 / 0 |
| VRAM | 2 656 MB không đổi (183 lần đọc `/ailive/health`, cùng một `boot_id`) | như trái |

- **VRAM đỉnh trong `avatar.jsonl`:** lần này không có. App chưa nối `SessionLog.record_avatar` nên `avatar.jsonl` không được ghi (lỗi
  tìm ra khi đo, đã sửa commit `2c7bbf3`). Số VRAM ở bảng đọc thẳng từ `/ailive/health` của fork.
- **fps lượt bình luận thấp hơn show, nhưng không do suy luận:** `infer_fps` vẫn ~24,7. Ví dụ lượt `4ed360ea`: 108 khung (4,32 s tiếng) phát
  trong 5,89 s. Ở lượt bình luận, VieNeu vừa tổng hợp vừa phát nên tiếng tới fork chậm hơn thời gian thực khi tranh CPU với fork; fork
  hết tiếng thì không có khung nhép miệng để đếm. Show lấy trước tiếng nên đạt ~25. Vì vậy giảm `LIVETALKING_BATCH_SIZE` hay bật
  `LIVETALKING_LIP_EVERY_N=2` không chữa được chỗ này (xem T075). Người xem thấy miệng ngừng giữa câu trả lời. TODO: người dùng xem bản
  ghi một lượt bình luận để đánh giá có chấp nhận được không.
- **Lặng giữa câu p95 2,98 s > 1,5 s** và lớn hơn `LIVETALKING_HOLD_S` 2,5 s (một số khoảng nghỉ thoáng về clip chờ). Theo R15: thử
  `LIVETALKING_LEAD_S` = độ trễ khung đầu p50 ≈ 1,3 s, kết quả ở mục "Thử `LIVETALKING_LEAD_S`" dưới.
- Đo cạnh trình duyệt (T074, research R6): Chrome phát tiếng chậm hơn ack trung vị 0,28 s (p95 0,64 s), tiếng và hình cùng một luồng
  WebRTC nên vẫn khớp. Số độ trễ ở bảng thấp hơn lúc người xem thấy khoảng chừng ấy.

### Thử `LIVETALKING_LEAD_S` (2026-11-12, T073/T075)

Cùng điều kiện T073, chỉ đổi `LIVETALKING_LEAD_S` (biến môi trường của app). Số `sentence_gap` của app lúc đó bị tính dư khi `LEAD_S > 0` (lỗi
đo, xem dưới), nên khoảng lặng lấy từ chỗ người xem nghe: đầu đo WebAudio trong Chrome (như T074) ghi mức tiếng 20 ms một lần; một
khoảng lặng là đoạn ≥ 300 ms dưới RMS 0,003 ngay trước câu kịch bản (khớp với ack `avatar_first_frame` của câu trong cửa sổ −0,3…+1,5 s);
câu bắt đầu không qua khoảng lặng ≥ 300 ms tính là 0.

| `LEAD_S` | Phiên | Câu đã nói | Lặng nghe được p50 / p95 / lớn nhất | Tỉ lệ > 1,5 s | Tỉ lệ > 2,5 s |
|----------|-------|----------|--------------------------------------|---------------|---------------|
| 0 (T073, 30 phút) | `20261112-192347` | 322 | 2,24 / 3,19 / 3,32 s | 0,88 | 0,39 |
| 1,3 (≈ trễ khung đầu p50) | `20261112-200619` | 140 | 1,20 / 1,96 / 2,00 s | 0,26 | 0 |
| 2,5 | `20261112-202003` | 82 | 0,53 / 0,76 / 1,46 s | 0 | 0 |
| 2,5, sau khi sửa lỗi đo | `20261112-203110` | 51 | 0,53 / 1,00 / 1,64 s | 0,02 | 0 |

- `LEAD_S` 2,5 đưa khoảng lặng p95 xuống dưới mục tiêu 1,5 s của Điều VI. Không lỗi, không `vram_oom`, VRAM vẫn 2 656 MB; câu đầu show 1,6–2,1 s.
  Một câu dài hơn 2,5 s thì `speak` trả về ngay sau `playback_started`, câu sau xếp hàng ở fork. Câu sau chờ khung đầu lâu hơn chừng
  `LEAD_S`, nên `LIVETALKING_LEAD_S` phải nhỏ hơn hẳn `LIVETALKING_FIRST_FRAME_TIMEOUT_S` (10 s) trừ thời gian khởi động câu (~1,3 s).
- Lặng p95 với `LEAD_S` 2,5 nhỏ hơn `LIVETALKING_HOLD_S` 2,5 s nên không cần nâng `LIVETALKING_HOLD_S`.
- **Đề xuất cho người dùng duyệt:** đặt `LIVETALKING_LEAD_S=2.5` cho buổi demo. Mặc định trong `.env.example` vẫn là `0` tới khi người dùng
  duyệt. TODO: người dùng duyệt đổi mặc định thành 2,5.
- **Lỗi đo tìm ra khi thử (đã sửa 2026-11-12, contracts/adapters.md §2):**
  - Với `LEAD_S > 0`, `sentence_gap` tính từ lúc `speak` trả về (sớm hơn lúc phát xong tới `LEAD_S`), nên bị thổi lên. App báo p95 3,30 s
    trong khi tai nghe p95 0,76 s.
  - Số đo (`render_stats`, cột fps của `/api/latency`) của câu trả về sớm bị mất.
  - Đã sửa: `sentence_gap` tính từ `sentence_played` của fork. Số đo lấy sau khi câu cuối phát xong (`RenderSettleSource`).
  - Lần chạy kiểm `20261112-203110`: app báo lặng trung vị 0,55 s, p95 0,76 s, khớp số nghe được (phần chênh là độ lệch ack ↔ Chrome của
    T074). Đủ 56 dòng `render_stats` (51 câu + 5 lượt).

### So sánh `LIVETALKING_BATCH_SIZE` và `LIVETALKING_LIP_EVERY_N` (2026-11-12, T075)

Cùng điều kiện T073 nhưng `LIVETALKING_LEAD_S=2.5`. Mỗi cấu hình chạy trên một phiên app mới: 10 lượt bình luận lúc host rảnh rồi show
kịch bản 3 phút (không phải 30 phút). Lặng nghe được đo bằng đầu đo Chrome như mục trên. Hàng batch 16 lấy số lượt bình luận từ 5 lượt
của lần chạy kiểm `20261112-203110`, vì 20 lượt của lần chạy riêng bị app bỏ (`show_ended`: show trước đó đã kết thúc trong cùng phiên).

| Cấu hình | Phiên | Lượt: khung đầu p50 / cả lượt p50 | Lượt: `render_fps` / `infer_fps` p50 | Câu đầu show | Show: `render_fps` p50 (p5) / `infer_fps` p50 | Lặng app p95 | Lặng nghe được p50 / p95 / lớn nhất | VRAM | Lỗi |
|---|---|---|---|---|---|---|---|---|---|
| batch 16, n = 1 (mặc định) | `20261112-203110` | 1,36 / 1,86 s | 18,8 / 25,1 | 2,81 s | 24,0 (21,6) / 23,8 | 0,70 s | 0,48 / 0,86 / 1,30 s | 2 656 MB | 0 |
| batch 8 | `20261112-212250` | 0,73 / 1,27 s | 17,9 / 21,2 | 1,17 s | 20,0 (18,6) / 20,0 | 0,36 s | 0,00 / 0,58 / 0,76 s | 1 004 MB | 0 |
| batch 4 | `20261112-212937` | 0,45 / 1,06 s | 18,7 / 20,2 | 0,97 s | 19,1 (15,8) / 19,7 | 0,03 s | 0,00 / 1,03 / 1,22 s | 894 MB | 0 |
| batch 16, n = 2 | `20261112-213850` | 1,06 / 1,66 s | 20,3 / 42,9 | 1,73 s | 20,1 (16,0) / 38,0 | 0,91 s | 0,47 / 1,05 / 1,33 s | 2 660 MB | 0 |

- Không cấu hình nào giữ được 25 khung/giây suốt. Chỉ batch 16, n = 1 gần đạt ở show (p50 24). Batch nhỏ hơn cho khung đầu sớm hơn và
  lặng ngắn hơn, nhưng fps tụt còn ~19–20 (miệng giật hơn). Không có `vram_oom` hay `renderer_restarted` ở cấu hình nào.
- n = 2 làm `infer_fps` gần gấp đôi nhưng `render_fps` không tăng (thấp hơn n = 1). Nút cổ chai không nằm ở suy luận. Có thể do nhịp
  phát khung hoặc do tranh CPU với VieNeu; chưa đo tách. Vì không có lợi nên không xem chất lượng môi của n = 2.
- **Lệch ack ↔ Chrome của lượt bình luận** (khung đầu tới lúc nghe tiếng, cùng cách đo T074): batch 16 0,81 s (n = 5), batch 8 1,32 s,
  batch 4 1,18 s, n = 2 0,33 s; LEAD 0 (T073) 0,47 s (n = 4). Các số này cao hơn số 0,28 s của T074 (đo chủ yếu trên câu kịch bản) và
  dao động mạnh giữa các lần chạy. Cộng thêm phần lệch này, bình luận → nghe tiếng vẫn ~2,2–3,2 s (< 5 s).
  _Đo lại 2026-11-13 (phiên `20261113-010317`, batch 16, n = 1, LEAD 2,5, 30 lượt bình luận trên host đang chờ, `REPLY_ENGINE=fake`):_
  khớp 30/30 lượt; lệch p5 0,35 s, trung vị 0,63 s, p95 0,81 s, max 1,02 s. Các số lẻ ở trên (n ≤ 5) đều nằm trong khoảng này, nên
  phần lớn là dao động giữa các lượt chứ không phải do cấu hình (batch 8 và 4 chưa đo lại với nhiều lượt). Lượt bình luận lệch nhiều
  hơn câu kịch bản (0,28 s ở T074), có thể vì mỗi lượt bắt đầu từ host đang chờ (fork đổi clip chờ sang clip nói); chưa đo tách.
  Cùng phiên: tổng bình luận → khung đầu trung vị 1,82 s, p95 2,08 s; `render_fps` 18,5 (p95 22,5), `infer_fps` 25,9; không có
  `vram_oom` hay `renderer_restarted`. Bình luận → nghe tiếng ≈ 2,5 s trung vị, ≤ 2,9 s ở p95 (cộng p95 hai phần), còn xa ngưỡng 5 s;
  LLM thật cộng thêm thời gian ra câu đầu.
- **Đề xuất:** giữ mặc định batch 16, n = 1. Batch 8 là lựa chọn nếu người dùng ưu tiên phản ứng nhanh hơn miệng mượt.
  TODO: người dùng chọn batch 16 hay 8. Bước tiếp theo (bộ clip nhỏ hơn, R8, hoặc [RunPod]) cần người dùng quyết định và hỏi chi phí trước.

## 10. Chia sẻ vào Google Meet (FR-018) [GPU laptop]

Chia sẻ tab `/host` có tiếng vào Meet; người xem bên kia thấy nhân vật, nhãn "AI", nghe tiếng khớp miệng.

## 11. Tự kiểm không cần người xem: bộ ghi luồng (thêm 2026-11-12) [GPU laptop]

Dùng cho bước 6–9 khi không có người ngồi xem: fork ghi lại đúng khung hình + tiếng nó gửi sang WebRTC (sau khi dán nhãn "AI"),
rồi một script chấm điểm. Bản ghi chứa mặt và giọng người mẫu nên chỉ nằm trong `out/` (ngoài git), không gửi đi đâu.

1. Trong `.env`: `AILIVE_RECORD_DIR=out/selfcheck` (để trống là tắt, mặc định tắt), `AILIVE_RECORD_MAX_S=600` (mỗi bản ghi tự dừng).
   Bật lại fork bằng `run.ps1` (in "Ghi luồng tự kiểm: bật"), bật app `APP_ENV=dev`, mở `/host`, bấm "Bắt đầu" một lần.
2. Chạy:
   ```bash
   uv run python scripts/selfcheck/lipsync_check.py --name t062 --text "Câu một." --text "Câu hai."
   uv run python scripts/selfcheck/lipsync_check.py --name wav1 --wav out/t052/sample.wav --idle 5
   ```
   Script lấy phiên từ `/ailive/health`, gọi `POST /ailive/record/start`, đọc từng câu qua `/api/debug/speak` (hoặc
   `/api/debug/speak-audio` cho WAV), dừng ghi, rồi chạy `python -m ailive_ext.analyze` trong venv fork. Mã thoát 0 = đạt.
3. Kết quả cạnh bản ghi: `<tên>.mp4/.wav/.jsonl` (bản ghi), `.report.json`, `.sheet.jpg` (khung đầu câu, hai bên chỗ chuyển clip,
   khung to tiếng nhất), `.mouth.jpg` (50 khung miệng liền nhau quanh đoạn to nhất, kèm vạch âm lượng), `.driver.json`.

Các mục chấm (chỉ là số đo thay thế, không chấm được độ tự nhiên của giọng và mặt; việc đó vẫn cần người xem ở gói duyệt):

| Mục | Đo gì | Đạt khi |
|-----|-------|---------|
| stream | số khung, fps theo đồng hồ, khung bộ ghi bỏ; ước lượng khựng phía người xem (`playout_freezes`) | đủ khung, không bỏ khung, fps ≥ 23,5 (khựng chỉ báo, chưa chấm) |
| label | hộp nhãn "AI" có mặt ở mọi khung | không khung nào thiếu |
| audio | đỉnh, vỡ tiếng, tiếng lọt vào lúc chờ, câu không có thẻ kết thúc | vỡ < 0,1 %, không lọt, câu nào cũng kết thúc |
| mouth | độ mở miệng (điểm ảnh không phải môi nằm trong viền môi) so với đường bao âm lượng, quét lệch ±6 khung | r ≥ 0,15, đỉnh rõ (≥ 0,2 so với mép), lệch ≤ 2 khung (80 ms), to tiếng mở hơn lúc chờ ≥ 1,5 lần |
| seams | hình nhảy ở chỗ đổi nói/chờ hoặc đổi clip | không chỗ nào chênh > 3 lần chuyển động quanh nó (và > 6 mức xám) |

Khựng thật phía trình duyệt: đo bằng `requestVideoFrameCallback` trên thẻ `video` của `/host` (Chrome DevTools MCP chạy script đếm
khoảng cách giữa các khung được hiển thị > 80 ms).

Kết quả chạy đầu (2026-11-12, `smoke3`, `smoke4`; 2 câu VieNeu, batch 16, laptop GTX 1650 Ti):

- stream, label, audio đạt; miệng đạt với ngưỡng mới (r 0,33 và 0,21, cả hai đỉnh ở lệch 0, mở khi nói gấp ~2,8 lần lúc chờ). Ngưỡng
  ban đầu (r ≥ 0,3, đo phần tối trong vùng dưới mặt) đánh trượt nhầm: vùng tóc và bóng cằm bị tính là miệng mở.
- **seams trượt:** chuyển `talk_02 → idle_01` cắt cứng (chênh ~29 so với ~1,8 quanh đó). Đúng như chờ đợi: trộn dần
  `LIVETALKING_TRANSITION_S` thuộc T066 (US3), chưa làm. Dùng bản ghi này làm mốc so sánh cho T066–T067 (T067: 0 chỗ giật,
  xem bước 8).
- **Khựng lúc bắt đầu nói:** bộ ghi thấy khoảng trống ~1,4–1,6 s ở khung đầu câu (ước lượng khựng ~0,7 s); trình duyệt đo được 10 lần
  khựng 0,28–0,41 s trong 33 s, dồn quanh lúc bắt đầu câu. TODO: tìm nguyên nhân ở T062–T063 (TTS CPU tranh CPU với fork? lô suy luận
  đầu câu chờ đủ 16 khung tiếng?).

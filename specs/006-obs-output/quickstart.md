# Quickstart: Đưa AI host vào OBS

- **Feature ID:** `006-obs-output` · **Ngày:** 2026-11-13 · **Plan:** [plan.md](./plan.md)
- Không gọi LLM free: mọi show ở đây chạy `REPLY_ENGINE=fake` hoặc nội dung `verbatim` (007).
- Ký hiệu: **[không GPU]** chạy với `AVATAR_MODE=static`; **[GPU laptop]** chạy fork nhép miệng trên GTX 1650 Ti (ADR-023). Không dùng
  RunPod.

## 0. Chuẩn bị

```bash
uv sync
uv run pytest tests/unit/test_host_roles.py tests/integration/test_obs_page.py   # [không GPU]
```

- OBS Studio: máy demo dùng bản cài chính thức của người vận hành. Máy dev dùng bản portable để kiểm (ADR-059), giải nén ở
  `%LOCALAPPDATA%\ai-live\obs` (ngoài repo), chạy `bin\64bit\obs64.exe --portable`.

## 1. US1: thêm AI host vào OBS (P1)

1. **[không GPU]** `OUTPUT_MODE=obs AVATAR_MODE=static REPLY_ENGINE=fake TTS_PROVIDER=fake uv run uvicorn ai_live.app.main:app --port 8000`.
2. Trong OBS: Sources → + → Browser.
   - URL `http://127.0.0.1:8000/obs`, Width 720, Height 1248.
   - Bật "Control audio via OBS"; bỏ chọn "Shutdown source when not visible"; bỏ trống Custom CSS.
3. Trên trang điều khiển (`http://127.0.0.1:8000/`): bấm "Kiểm tra trước demo" → mục host ĐẠT "Nguồn OBS đã nối".
4. Bắt đầu show (nội dung `verbatim`): trong ≤ 10 s OBS có hình + tiếng, thanh âm lượng nguồn trong mixer nhảy, không bấm gì trong nguồn.
5. Kéo nguồn sang kích thước khác (ví dụ 1280×720): nội dung thu nhỏ có viền đen, nhãn "AI" vẫn đủ.
6. Dừng show: nguồn còn ảnh chờ + nhãn "AI".
7. **[GPU laptop]** lặp 1–6 với `AVATAR_MODE=livetalking` (fork chạy bằng `scripts/livetalking/run.ps1`).
8. Chấm SC-002, SC-003: OBS ghi 5 phút (Settings → Output → Recording Format `Fragmented MP4`, bản ghi vẫn đọc được khi OBS bị tắt ngang), rồi
   `uv run python scripts/selfcheck/lipsync_check.py <file>` (nhãn trong mọi khung lấy mẫu, lệch hình–tiếng); so lệch hình–tiếng với bản ghi
   của chính fork (`AILIVE_RECORD_DIR`) cùng show.

## 2. US2: chạy lâu không chạm vào OBS (P2)

Trong lúc OBS đang ghi, show đang chạy:

1. **[GPU laptop]** Tắt fork (Ctrl+C trong terminal fork), đợi 10 s, chạy lại `run.ps1`; bấm "Bật lại nhân vật nhép miệng" khi banner
   `fork_lost` tắt. OBS: ảnh tĩnh có tiếng → hình nhép miệng ≤ 10 s sau khi fork sẵn sàng. Lặp 5 lần (SC-004).
2. **[không GPU]** Tắt app (Ctrl+C), chạy lại. OBS tự tải lại nguồn và có hình + tiếng ≤ 15 s sau khi app sẵn sàng. Lặp 5 lần.
3. **[không GPU]** Mở `http://127.0.0.1:8000/host` trên Chrome, bấm "Bắt đầu": trang báo "Đang phát qua OBS, xem trong cửa sổ OBS",
   không có tiếng; OBS vẫn có tiếng. Đóng tab. Lặp 5 lần (SC-006).
4. **[không GPU]** Thêm nguồn `/obs` thứ hai trong OBS: chỉ nguồn mới có tiếng, nguồn cũ im (ảnh + nhãn). Xóa nguồn thừa.
5. Chấm bản ghi: không đoạn nói đôi, không câu mất; `uv run python -m ai_live.ops report <phiên>` so lặng p95 với một show `/host` cùng
   cấu hình (SC-005: ≤ +0,2 s).

## 3. US3: biết đầu ra OBS có đang nhận không (P3)

1. **[không GPU]** `OUTPUT_MODE=obs`, chưa thêm nguồn: "Kiểm tra trước demo" → mục host LỖI "Nguồn OBS chưa nối" kèm hướng dẫn.
2. Mở `/host` trên Chrome (chưa có OBS): mục host LỖI "Đang phát ở trang host trên Chrome, chưa phải OBS".
3. Thêm nguồn OBS: mục host ĐẠT.
4. Trong show, ẩn nguồn bằng con mắt (khi đã bật "Shutdown source when not visible" để thử) hoặc xóa nguồn: banner "Nguồn OBS đã ngắt"
   trên trang điều khiển ≤ 10 s; hiện lại nguồn: banner tự tắt. Lặp 3 lần (SC-007).
5. `OUTPUT_MODE=meet` (hoặc `webrtc` cũ): mục host và banner giữ lời của 007.

## 4. Kiểm tự động (không cần người)

- Chrome DevTools MCP với Chrome chạy `--autoplay-policy=no-user-gesture-required` (mô phỏng CEF của OBS): §1 bước 3–6, §2 bước 2–3,
  §3 bước 1–4.
- OBS portable (ADR-059): dựng sẵn `config/obs-studio/basic/scenes/ailive.json` (một Browser Source `/obs`) và profile ghi `Fragmented MP4` (tắt tiến trình không làm hỏng file), chạy
  `obs64.exe --portable --collection ailive --startrecording --minimize-to-tray`, dừng bằng đóng tiến trình sau N phút, chấm file ghi
  như §1 bước 8.

## 5. Kết quả kiểm chứng

Ngày 2026-11-13, laptop dev, `OUTPUT_MODE=obs`, `AVATAR_MODE=static`, `REPLY_ENGINE=fake`, `TTS_PROVIDER=fake` (không gọi LLM free).

- **Tự động:** `uv run pytest` 2461 passed, 11 xfailed; `ruff check` và `ruff format --check` sạch. Test 006: vai `obs` > `host`
  (`test_host_roles.py`), trang `/obs`, `/ws/host?role=`, `/api/state` và mốc độ trễ khi show phát qua OBS (`test_obs_page.py`,
  FR-013), kiểm tra trước demo (`test_readiness.py`), canh show chế độ obs (`test_watchdog.py`, `test_watchdog_show.py`).
- **FR-012:** `host.js`/`host.html` chỉ có hai nguồn hình: ảnh `/api/scene/still.png` (ảnh chờ do app vẽ) và luồng WebRTC của fork
  (`srcObject`); không có đường nào phát file `.mp4`/`.wav`. Không route nào trả video (`test_no_route_serves_a_video_file`).
- **§1 bước 3–6 (Chrome MCP, cờ autoplay như CEF):** `/obs` tự phát không cần bấm, không có lớp phủ, chữ trạng thái hay phụ đề; chỉ ảnh
  + nhãn "AI"; ở 720×1248 và 1280×720 nhãn nằm trong khung, không thanh cuộn; show fake phát 3 câu có `avatar_first_frame`; kiểm tra
  trước demo ĐẠT "Nguồn OBS đã nối, âm thanh sẵn sàng". Khi tắt cảnh 009, nhãn nằm ở dải đen trên ảnh (như `/host`).
- **§2 bước 2–4:** app tắt rồi chạy lại → `/obs` tự tải lại và phát tiếp sau ~9 s (≤ 15 s). `/host` mở khi OBS đang phát → báo "Đang
  phát qua OBS…", không tiếng; `/host` đang phát rồi mở `/obs` → trang host nhận 4001, tắt tiếng, nhả phiên fork (4/4 peer đóng). Hai
  nguồn `/obs` → nguồn cũ im (ảnh + nhãn), không nối lại.
- **§3 bước 1–5:** chưa có nguồn → badge đỏ "OBS (chưa nối)" kèm URL nguồn; `/host` phát thay → "…đang phát thay" + cảnh báo "Nguồn OBS
  đã ngắt"; đóng/mở `/obs` 3 lần → banner hiện và tắt mỗi lần (< 0,1 s, 3/3, SC-007); `/obs` ngừng nhịp → banner "không gửi nhịp trạng
  thái" sau đúng ngưỡng, Refresh thì tắt. `OUTPUT_MODE=webrtc` → chạy như `meet`, log WARNING `output_mode_legacy`, lời 007 giữ nguyên.
  Ghi nhận: khi nguồn ngừng nhịp, badge vẫn "OBS (đã nối)" (kết nối còn mở) trong khi banner báo ngắt; chấp nhận được.
- **§4 OBS portable (T029):** OBS 33.0.1 đã giải nén ở `%LOCALAPPDATA%\ai-live\obs`, có sẵn `config/obs-studio` (collection và profile
  `ailive`: một Browser Source `http://127.0.0.1:8766/obs` 720×1248 "Control audio via OBS", ghi Fragmented MP4 ra `out/006_obs/`).
  Chưa chạy được: bộ phân quyền của Claude Code chặn chạy `obs64.exe` vừa tải. Chưa đo R3 (`framesDecoded`, tiếng vào mixer trong CEF).
  R10: `lipsync_check.py` điều khiển fork rồi chấm bản ghi của fork (`<prefix>.mp4/.wav/.jsonl`), không nhận file ngoài; file OBS cần
  chấm bằng mắt hoặc thêm bước tách tiếng (TODO ở research R10).
- **Chưa làm ([GPU]):** T018, T019, T030 (SC-002, SC-003), T031 (SC-005, SC-006).

### Gói duyệt cho người dùng

1. Cho phép chạy OBS portable để tôi làm nốt T029, hoặc tự gõ trong Claude Code (app phải đang chạy `OUTPUT_MODE=obs` cổng 8766):
   `! "$LOCALAPPDATA/ai-live/obs/bin/64bit/obs64.exe" --portable --profile ailive --collection ailive --startrecording --minimize-to-tray --disable-updater`
2. Trong OBS thật của mình: thêm nguồn theo [RUNBOOK](../../docs/RUNBOOK.md) §8, bấm giờ từ lúc mở OBS tới lúc có hình + tiếng (SC-001:
   ≤ 2 phút, không bấm gì trong nguồn).
3. Xem/nghe một bản ghi OBS: tiếng rõ, nhãn "AI" mọi lúc, không nói đôi.
4. Xác nhận ADR-058 (bỏ YouTube, đầu ra OBS bằng `/obs`) và ADR-059 (OBS portable làm công cụ kiểm ngoài repo).
5. Khi tắt cảnh 009, nhãn "AI" nằm ở dải đen phía trên ảnh: có cần đưa vào trong ảnh không?

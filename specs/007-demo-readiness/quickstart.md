# Quickstart: 007 Sẵn sàng cho buổi demo

> Bước 1–4 chạy không GPU (`AVATAR_MODE=static`, `TTS_PROVIDER=fake`). Bước 5–6 cần fork và GPU laptop (ADR-023). Không bước nào gọi
> LLM free: luôn `REPLY_ENGINE=fake` khi thử (SC-007). Biến truyền thẳng trên dòng lệnh, không sửa `.env`.

## 1. Kiểm tra trước demo

```bash
APP_ENV=dev REPLY_ENGINE=fake TTS_PROVIDER=fake AVATAR_MODE=static uv run uvicorn ai_live.app.main:app --port 8000
uv run python -m ai_live.ops readiness          # hoặc nút "Kiểm tra trước demo" trên trang điều khiển
```

Với cấu hình thử này kết quả phải là "Chưa sẵn sàng" với Lỗi ở `app_env`, `reply_engine`, `tts_provider`, `host` (chưa mở `/host`),
`backup_video` (chưa làm). Tắt app rồi chạy lại lệnh: `source: offline`, mục `host`/`llm_chain` báo "app chưa bật".

## 2. Thấy cảnh báo canh show

```bash
FAKE_TTS_DELAY_MS=0 APP_ENV=dev REPLY_ENGINE=fake TTS_PROVIDER=fake AVATAR_MODE=static uv run uvicorn ai_live.app.main:app --port 8000
```

Mở `/host`, bấm "Bắt đầu", rồi "Bắt đầu show" trên trang điều khiển. Giả lập:

- Bước tạo tiếng treo: `curl -X POST localhost:8000/api/debug/fault -H 'content-type: application/json' -d '{"step":"tts","mode":"timeout","count":3}'`
  → banner "Host im lặng" sau 5 s; nếu còn treo tới 15 s thì tự bỏ câu (ghi "đã tự bỏ câu").
- Đóng tab `/host` → banner đỏ "Màn hình host đã đóng"; mở lại và bấm "Bắt đầu" → banner tự tắt.
- Tạm dừng show 20 s → không có banner im lặng.

Xem `data/sessions/<phiên>/alerts.jsonl`.

## 3. Báo cáo tổng duyệt

```bash
uv run python -m ai_live.ops report <session_id>               # show cuối của phiên
uv run python -m ai_live.ops report <session_id> --show <show_id>
```

Ra `data/sessions/<phiên>/rehearsal_<show_id>.md/.json`. Show chạy bằng bộ trả lời giả luôn có ghi chú "chưa phải tổng duyệt thật".

## 4. Test

```bash
uv run pytest tests/unit/test_readiness.py tests/unit/test_watchdog.py tests/unit/test_rehearsal.py tests/unit/test_backup_video.py
uv run pytest tests/integration/test_readiness_api.py tests/integration/test_watchdog_show.py tests/integration/test_show_verbatim.py
cd vendor/livetalking && .venv/Scripts/python.exe -m pytest -q ailive_ext/tests
```

## 5. Làm video dự phòng (GPU laptop)

1. Bật fork có ghi luồng: đặt `AILIVE_RECORD_DIR=out/record` trong `.env` rồi chạy `scripts/livetalking/run.ps1` (`run.ps1` đọc `.env`;
   biến môi trường chỉ có tác dụng khi `.env` không có dòng này; `app.py` của fork còn tự nạp `.env` của repo bằng `load_dotenv()`).
   Nhớ xóa trước buổi demo, readiness sẽ báo Lỗi nếu quên.
2. Bật app với `AVATAR_MODE=livetalking`, `TTS_PROVIDER=vieneu`; `REPLY_ENGINE` để gì cũng được vì `verbatim` không gọi engine
   (để `fake` cho chắc không tốn hạn mức).
3. Mở `/host`, bấm "Bắt đầu", chờ nhân vật hiện.
4. `uv run python -m ai_live.ops backup-video` → khoảng 3 phút sau có `out/backup_video/backup_<ngày>_<khách>.mp4` + `.sheet.md`.
5. **Người xem lại** video (tiếng khớp miệng, nhãn "AI") và thử phát qua Meet có tiếng (SC-006). Chỉ dùng ngoài Shopee.
6. Tắt fork, bật lại không có `AILIVE_RECORD_DIR`.

## 6. Đo SC-004: show 30 phút với canh show bật (GPU laptop)

```bash
# fork: powershell scripts/livetalking/run.ps1
REPLY_ENGINE=fake TTS_PROVIDER=vieneu AVATAR_MODE=livetalking APP_ENV=dev uv run uvicorn ai_live.app.main:app --port 8000
# mở /host trên một cửa sổ Chrome riêng, "Bắt đầu", rồi:
curl -X POST localhost:8000/api/show/start; sleep 1800; curl -X POST localhost:8000/api/show/end
uv run python -m ai_live.ops report <session_id>
```

So `gaps.p95_s` và câu đầu với 005 T073 (lặng p95 2,98 s): không tệ hơn quá 0,1 s; số cảnh báo sai = 0 (SC-002).

## Kết quả kiểm chứng

### §1 Kiểm tra trước demo (T026, 2026-11-13, laptop, không GPU, không gọi LLM)

App `APP_ENV=dev REPLY_ENGINE=fake TTS_PROVIDER=fake AVATAR_MODE=static`, cổng 8031 (không đụng app của người dùng ở 8000),
trang mới qua Chrome DevTools MCP.

- Bấm "Kiểm tra trước demo" trên trang điều khiển: nhãn "CHƯA SẴN SÀNG", bảng 15 mục đúng thứ tự. Lỗi ở `app_env`, `reply_engine`,
  `tts_provider`, `host`, `backup_video`, đúng như mục §1 nói. Chú ý ở `avatar_mode` (ảnh tĩnh) và `power` (đang chạy pin), các mục
  còn lại Đạt (ổ đĩa còn 156,3 GB). Mỗi mục Lỗi/Chú ý có việc cần làm. Có 3 ô tự xác nhận. Kiểm mất 1 ms (SC-001: ≤ 5 s).
- Mở `/host` trên một trang mới rồi bấm "Bắt đầu": mục `host` chuyển từ Lỗi sang Chú ý với lời "chưa gửi nhịp trạng thái". Lý do là
  nhịp `host_status` 1 giây từ `host.js` thuộc US2 (T031) và chưa làm; sau T031 mục này phải lên Đạt.
- `uv run python -m ai_live.ops readiness --url http://127.0.0.1:8031`: cùng bảng ở dạng chữ, thoát mã 1. Gọi `--url` một cổng không có
  app thì ra `app chưa bật, chỉ kiểm phần không cần app` sau 156 ms, thoát mã 1.
- Đã sửa sau lần kiểm: lời nhắc mục `host` ghi cứng `127.0.0.1:8000`, đổi thành "Mở trang /host của app". Đo thời gian chuyển sang
  `perf_counter`, vì `monotonic` trên Windows chỉ chính xác khoảng 15 ms nên trước đó báo 0 ms.

### §2 Cảnh báo canh show (T035, 2026-11-13, laptop, không GPU, không gọi LLM)

App như §1 thêm `TTS_TIMEOUT_S=30` (để thấy tự bỏ câu trước khi bước tạo tiếng tự hết giờ), cổng 8031, trang điều khiển và `/host` mở
trên hai trang mới qua Chrome DevTools MCP.

- Tạo tiếng treo (`tts` / `timeout`): sau 5 s có banner vàng "Host im lặng 5 giây — Đợi vài giây; nếu quá 15 giây hệ thống sẽ tự bỏ câu
  đang kẹt". Tới 15 s canh show tự bỏ câu, host nói tiếp và banner tắt. `alerts.jsonl` có đúng 3 dòng: `open` 08:53:22.467, `auto_skip`
  08:53:32.496 ("đã tự bỏ câu đang kẹt"), `close` 08:53:32.558 (15,3 s). Không lên mức gọi người vận hành.
- Rời trang `/host` (đi sang trang khác trong cùng tab): banner đỏ "Màn hình host đã đóng — Mở lại /host, bấm "Bắt đầu" rồi chia sẻ lại
  tab vào Meet" hiện trong vòng 1,5 s. Mở lại `/host` và bấm "Bắt đầu" thì banner tắt, mục "Lượt đã xong" ghi "đã hết cảnh báo · Màn hình
  host đã đóng (10 giây)". Mục `host` của §1 lên Đạt ("Màn hình host đã mở, âm thanh sẵn sàng") nhờ nhịp `host_status`.
- Tạm dừng show 30 s: không có banner nào, log không có `watchdog_alert` giữa `show_paused` và `show_resumed`.
- Đã sửa sau lần kiểm:
  1. Lần đầu rời trang `/host`, server chỉ thấy host mất sau khoảng 40 s (lúc ping hết giờ). Trong lúc đó chỉ có cảnh báo vàng
     `audio_missing`. Lý do là Chrome giữ trang trong bộ nhớ đệm quay lại (bfcache) với socket còn mở; đóng socket ở `pagehide` không đủ,
     vì trang bị đóng băng trước khi gửi khung đóng. Đã thêm `Cache-Control: no-store` cho `/host` để trang không vào bfcache, và giữ
     `pagehide` đóng socket. Test: `test_host_page_stays_out_of_the_back_forward_cache`.
  2. Banner "đã tự bỏ câu" tắt chỉ khoảng 60 ms sau khi hiện, người vận hành gần như không kịp thấy. Giờ mỗi cảnh báo hết đều để lại
     một dòng trong "Lượt đã xong".
  3. Khi bấm bỏ câu lúc bước tạo tiếng đang treo, câu kẹt không bị hủy nên im lặng kéo dài tới hết giờ chờ và lên mức gọi người vận hành.
     `ScriptRunner.skip` giờ bỏ luôn câu đang chờ tiếng đầu tiên. Test: `test_stuck_sentence_is_skipped_once_then_the_show_speaks_again`.

### §3 Báo cáo tổng duyệt (T042, 2026-11-13, laptop, không GPU, không gọi LLM)

Chạy `uv run python -m ai_live.ops report 20261113-155721` trên log của app thử ở cổng 8031 (`REPLY_ENGINE=fake`, `TTS_PROVIDER=fake`,
ảnh tĩnh). Phiên này có hai show.

- Show `406d8169…` (show của lần kiểm §2, có lỗi giả lập và rời trang `/host`): thoát mã 1. Tiêu chí 3 KHÔNG ĐẠT: 14 khoảng lặng được
  đếm (dưới 20 nên p95 lấy bằng khoảng dài nhất, có ghi chú), dài nhất 13,312 s là khoảng `error` lúc 15:57:54, câu liền trước
  "Câu 3 Chào mở màn.". Tiêu chí 4 KHÔNG ĐẠT: có cảnh báo `host_closed` và 1 câu `render_error`. Phần không tính: tạm dừng 1 lần,
  27,485 s. Đếm tay lại trong `gaps.jsonl`: 14 khoảng được đếm, dài nhất 13,312 s, trung vị 0,078 s, khoảng `error` 13,312 s, tạm dừng
  27,485 s, khớp báo cáo.
- Show `9aeafdd2…` (show sạch 4 phút, kết thúc bằng `POST /api/show/end`): mặc định lấy show cuối, thoát mã 1. Tiêu chí 3 ĐẠT
  (62 khoảng, trung vị 0,063 s, p95 0,079 s, dài nhất 0,094 s). Tiêu chí 4 CHƯA ĐỦ 30 PHÚT (4,1 phút, kết thúc bình thường, không cảnh
  báo). 63 câu đã nói, không lỗi. Có ghi chú "chưa phải tổng duyệt thật" và "tiêu chí 2 không chấm".
- Cả hai lần đều ghi `rehearsal_<show>.md` và `.json` cạnh log phiên. Phiên `20261113-155300` (show ngắn trước đó) cũng ra báo cáo, mã 1.

### §5 Video dự phòng (T055, 2026-11-13, GPU laptop GTX 1650 Ti, chạy pin, không gọi LLM)

Fork bật bằng `run.ps1` (ghi luồng bật vì `.env` của máy có `AILIVE_RECORD_DIR=out/selfcheck`), app cổng 8032 với `REPLY_ENGINE=fake`,
`TTS_PROVIDER=vieneu`, `AVATAR_MODE=livetalking`, giọng VieNeu thật, `/host` mở trên Chrome và đã bấm "Bắt đầu".

- `uv run python -m ai_live.ops backup-video --url http://127.0.0.1:8032 --seconds 150 --content verbatim`: mã thoát 0, "Kết quả: Đạt".
  Show `b937dc11…` nội dung `verbatim`, tiến độ in mỗi 10 giây, tự kết thúc show và nói câu kết, tự dừng ghi và chấm.
- Video `out/backup_video/backup_20261113-1634_demo_customer_01.mp4` (16,6 MB) + `.sheet.md` + `.sheet.json`: dài 157,4 giây (trong
  120–180), có tiếng, nhãn "AI" đủ 3936/3936 khung. Tờ mô tả ghi khách, nhân vật, bản nội dung `2a1a52d5ae99`, nguồn `verbatim`, dòng
  "Chỉ dùng cho demo Meet/YouTube, không phát trên Shopee Live".
- Bộ chấm của fork (`ailive_ext.analyze`): stream 25,3 khung/giây, 0 khung rơi; 4 lần hình đứng khi phát, dài nhất 1,1 s, đều trong
  ~5 giây đầu (khung 16–128, lúc nạp clip nói đầu tiên); tiếng 26 câu, không câu nào cụt, không có tiếng lúc nghỉ; miệng khớp tiếng
  ở độ lệch 0 khung; 87 mối nối clip, không có bước nhảy. Ảnh tờ kiểm: nhãn "AI" và watermark LiveTalking ở mọi khung.
- Kiểm trước demo lúc fork còn ghi: mục "Ghi luồng thử" `LỖI` kèm việc cần làm, mục "Video dự phòng" `ĐẠT` (157,44 giây, đã kiểm đạt).
- Tắt fork, bật lại không ghi: **phát hiện** chỉ bỏ biến môi trường là chưa tắt, vì `app.py` gốc của fork gọi `load_dotenv()` và tự
  nạp `.env` của repo (`/ailive/health` vẫn báo `record_enabled: true`). Lần thử dùng launcher tạm đặt `AILIVE_RECORD_DIR` là một dấu
  cách (không sửa `.env` của người dùng): `record_enabled: false`, mục "Ghi luồng thử" về `ĐẠT`. Runbook §5 bước 6 (xóa dòng trong
  `.env`) vẫn đúng; đã ghi thêm vào runbook và RISKS Q26.
- Phần người (SC-006): xem lại video và thử phát qua Meet, chờ người dùng (T058).

### §6 Show 30 phút với canh show bật (T054, 2026-11-13, GPU laptop GTX 1650 Ti, chạy pin, không gọi LLM)

Cùng lần bật fork với §5 (đã tắt ghi luồng), app cổng 8032 `REPLY_ENGINE=fake TTS_PROVIDER=vieneu AVATAR_MODE=livetalking`, canh show
bật với ngưỡng mặc định lúc đó. Phiên `out/007-gpu/sessions/20261113-163404`, show `8ad923dd…`, 30,1 phút.

- `report`: 327 câu, 0 câu lỗi, câu đầu 2,188 s. 326 khoảng lặng: trung vị 1,774 s, p95 3,0 s, dài nhất 3,156 s, 0 khoảng > 5 s.
  Mã thoát 1: tiêu chí 3 `CHƯA ĐẠT` vì p95 > 1,5 s (vấn đề đã biết của 005, fork bắt đầu câu sau ~3 s, không do 007); tiêu chí 4 trượt
  chỉ vì 2 cảnh báo sai ở dưới.
- So 005 T073 (câu đầu 1,64 s; lặng trung vị 2,0 s, p95 2,98 s, dài nhất 3,16 s): p95 +0,02 s, trong mức cho phép 0,1 s (SC-004 ĐẠT).
  Câu đầu +0,55 s là nhiễu của một mẫu: đo lại khi fork đã ấm, canh show bật 2,281 / 1,719 / 1,594 s, canh show tắt
  (`WATCHDOG_ENABLED=false`) 2,266 / 1,562 / 1,657 / 2,016 s; bật lại app có canh show 2,282 / 1,734 / 2,047 s. Canh show không làm chậm
  câu đầu.
- **Cảnh báo sai: 2** (SC-002 chưa đạt ở lần này): 2 banner "Có thể mất tiếng" khi tab host báo bắt đầu phát sau 3,03 s và 3,16 s, đúng
  độ trễ vốn có của fork (005 lặng p95 2,98 s) nhưng vượt ngưỡng 3 s dành cho ảnh tĩnh. **Đã sửa**: thêm ngưỡng riêng khi đang nhép
  miệng `WATCHDOG_AUDIO_ACK_LIPSYNC_S` (mặc định 6 s); ảnh tĩnh, kể cả khi rơi về ảnh tĩnh giữa show nhép miệng, vẫn dùng 3 s. Có 2 test
  đơn vị mới. Lần chạy 10 phút ở §T056 với ngưỡng mới: 0 cảnh báo mất tiếng. Chưa chạy lại trọn 30 phút với ngưỡng mới (không bắt buộc;
  tổng duyệt thật với LLM ở T-1 ngày sẽ đo lại).

### §T056 Mất fork giữa show trên GPU (2026-11-13, GPU laptop, không gọi LLM)

Phiên `out/007-gpu/sessions/20261113-200820`, show `f7853fa0…`, 10,1 phút, canh show bật (ngưỡng mới). Giờ UTC theo `alerts.jsonl`.

- 13:12:06,586 tắt tiến trình fork (cổng 8010). 13:12:07,194 banner đỏ "Mất kết nối tới fork nhép miệng" và 13:12:07,201 banner vàng
  "Nhân vật nhép miệng lỗi, đang dùng ảnh tĩnh": **báo sau ~0,6 s**. Show tiếp tục bằng ảnh tĩnh, không ngắt.
- Bật lại fork bằng launcher không ghi: khỏe sau ~27 s. Bấm "Bật lại nhân vật nhép miệng" lần 1 lúc 13:13:48,4: banner ảnh tĩnh đóng rồi
  mở lại lúc 13:13:50,397 sau 2 lần render lỗi `lipsync_unavailable`, vì app chưa thấy lần bật mới của fork (kiểm sức khỏe ~5 s/lần).
  `fork_lost` đóng lúc 13:13:55,370 (mở 108,2 s) khi app thấy `boot_id` mới. Bấm lần 2 lúc 13:14:51,0: banner ảnh tĩnh đóng lúc
  13:14:51,262 và nhân vật nhép miệng chạy lại.
- **Sửa**: chữ "Làm gì" của banner mất fork và runbook §4 nay dặn đợi banner đỏ tắt rồi mới bấm, bấm sớm thì bấm lại.
- `report` của show: 130 câu, 4 câu `render_error` (trong lúc mất fork), 162,3 s ở ảnh tĩnh; 129 khoảng lặng, trung vị 1,157 s, p95
  2,968 s, dài nhất 3,032 s, 0 khoảng > 5 s; 0 cảnh báo mất tiếng.
- Một banner "Host im lặng" 5,343 s lúc đầu show là **cảnh báo đúng**: câu đầu lạnh (`tts_first_chunk` 0,453 s, `avatar_first_frame`
  5,343 s). Các lần đo câu đầu khác sau khi bật fork hoặc tải lại `/host` chỉ 2,27–2,28 s, nên 5,3 s là thỉnh thoảng. Runbook §3 ghi
  thêm: show đầu tiên sau khi bật fork có thể nói câu đầu chậm tới ~5 s.

### §T057 Không gọi chuỗi model LLM (SC-007, 2026-11-13)

- Mọi lần chạy app trong feature (cổng 8031, 8032; log `app8031*.log`, `app8032*.log`) ghi `reply_engine` `fake`; không có dòng
  `llm_chain`, `freellmapi` hay `groq` nào trong log app.
- Trong log phiên `out/007-gpu/sessions/`, chữ `llm_chain` chỉ xuất hiện là mã mục của bảng kiểm trước demo với lời "Không dùng chuỗi
  model" (mục `ok`), không phải lượt gọi. Test tự động không gọi LLM (`live_llm` bị bỏ qua mặc định).

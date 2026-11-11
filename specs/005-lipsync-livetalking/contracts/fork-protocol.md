# Hợp đồng app ↔ fork LiveTalking

- **Ngày:** 2026-11-06 · Nguồn quyết định: [research.md](../research.md) R2–R8, R10, R11.
- Fork là process riêng (venv riêng), chỉ nghe `127.0.0.1:8010`. App là client; trang host là client WebRTC.
- Mọi đoạn trong fork do mình viết nằm ở gói `ailive_ext/`; file gốc chỉ có móc nhỏ, đánh dấu `# ailive:` (Apache-2.0 §4b: ghi rõ file đã sửa).

## 1. Endpoint của fork

| Endpoint | Ai gọi | Nguồn gốc | Ghi chú |
|----------|--------|-----------|---------|
| `POST /offer` | trang host | upstream | SDP JSON `{sdp, type}` → `{sdp, type, sessionid}`; `sessionid` là chuỗi UUID của upstream (mở, app không phân tích). `max_session: 1`; phiên thứ hai bị từ chối (upstream trả HTTP 200 `{"code": -1, "msg"}`) |
| `GET /ailive/ws?sessionid=<str>` | app | **mới** | §2–§3. `sessionid` không tồn tại → đóng mã `4404` |
| `POST /interrupt_talk` | (không dùng) | upstream | Thay bằng tin `stop` trên `/ailive/ws` |
| `GET /ailive/health` | quickstart, script | **mới** | `{"ok": true, "boot_id", "fork_commit", "sessions": [..], "vram_used_mb"}` |

Các endpoint upstream khác (`/human`, `/humanaudio`, `/record`, `/set_audiotype`, `/sse`, `/whep`) giữ nguyên, không dùng.

## 2. App → fork trên `/ailive/ws`

| Tin | Dạng | Trường | Hành vi của fork |
|-----|------|--------|-----------------|
| `sentence_start` | JSON | `utterance_id: str`, `seq: int`, `text: str`, `sample_rate: 16000` | Ghi nhớ câu đang nhận. `sample_rate` khác 16000 → `error {kind:"bad_audio"}`. `seq == 0` = lượt mới → chọn clip nói (§4) |
| (nhị phân) | bytes | PCM16 LE mono 16 kHz, độ dài bất kỳ (số chẵn byte) | Ghép đệm, cắt khung 320 mẫu, đổi float32 `/32768`, `put_audio_frame(chunk, datainfo)`. Khung đầu câu có `datainfo={"status":"start","utterance_id","seq"}` |
| `sentence_end` | JSON | `utterance_id`, `seq` | Khung lẻ cuối được độn im lặng cho đủ 320 mẫu; khung cuối mang `datainfo={"status":"end",...}` |
| `stop` | JSON | `utterance_id` | `flush_talk()`, bỏ phần đệm, về clip chờ (§4); không gửi `sentence_played` cho câu bị dừng |
| `ping` | JSON | — | Trả `pong` |

Fork tự đệm, app được gửi nhanh hơn thời gian thật (hàng đợi tiếng của LiveTalking không giới hạn, R3).

## 3. Fork → app trên `/ailive/ws`

| Tin | Trường | Khi nào |
|-----|--------|---------|
| `hello` | `boot_id: str` (uuid mỗi lần process bật), `fork_commit: str`, `sessionid: str`, `fps: 25`, `batch_size: int`, `lip_every_n: int`, `ai_label: str` | Ngay khi nối |
| `playback_started` | `utterance_id`, `seq` | WebRTC gửi khung tiếng mang `status:"start"` của câu (cùng khung hình nhép miệng đầu tiên), qua `notify` của avatar |
| `sentence_played` | `utterance_id`, `seq` | WebRTC gửi khung tiếng mang `status:"end"` của câu |
| `stats` | `utterance_id`, `seq`, `frames: int`, `infer_fps: float`, `render_fps: float`, `clip_id: str` | Ngay sau `sentence_played` |
| `health` | `vram_used_mb: int`, `vram_peak_mb: int`, `infer_fps: float \| null` | Mỗi 5 s |
| `error` | `kind: str`, `message: str`, `utterance_id?: str`, `vram_peak_mb?: int` (chỉ `vram_oom`) | `vram_oom` (bắt `torch.cuda.OutOfMemoryError` trong vòng suy luận), `bad_audio`, `inference_failed`. Lỗi suy luận: lô hỏng thành khung im lặng, fork `flush_talk()` (bỏ tiếng còn trong hàng đợi, như `stop`), bỏ phần tiếng còn lại của `utterance_id` đó và về clip chờ |
| `pong` | — | Trả `ping` |

Ack chỉ gửi cho câu đã nhận `sentence_start` trên **cùng** kết nối. Mất kết nối giữa câu: fork `flush_talk()` và về clip chờ.

## 4. Hành vi hình của fork (`ailive_ext/`)

- **Nhãn AI** (`label.py`): vẽ trên mọi khung trong `process_frames`, ngay trước `push_video_frame`, sau watermark gốc. Hình chữ nhật nền
  đặc + chữ trắng, góc theo `AI_LABEL_POSITION`, lề 12 px, cỡ chữ tỉ lệ chiều cao khung. Chữ rỗng hoặc ngoài ASCII → fork thoát với mã lỗi
  khi khởi động. Không có endpoint hay tham số nào tắt nhãn.
- **Watermark "LiveTalking"** của upstream: giữ nguyên, không sửa.
- **Xoay clip** (`rotation.py`, thuần Python): `pick_next(clips: Sequence[Clip], kind, last_id: str | None, rng) -> Clip`: chọn ngẫu nhiên
  trong các clip đúng loại khác `last_id`; chỉ có một thì trả clip đó. Clip nói chọn khi nhận `sentence_start seq=0`; clip chờ chọn khi
  hết lượt nói (hết khoảng giữ dưới đây) và sau mỗi vòng đi tới đi lùi đầy đủ của clip chờ.
- **Giữ clip nói giữa hai câu** (`ClipScheduler` trong `rotation.py`, thuần Python, research R7): sau khung cuối của câu, fork giữ clip nói
  hiện tại thêm tối đa `LIVETALKING_HOLD_S` (mặc định 1,5 s): phát khung nền gốc của clip nói (không dán miệng), chỉ số khung chạy tiếp.
  Câu mới trong khoảng giữ: `seq > 0` nói tiếp trên clip đó; `seq == 0` chọn clip nói mới. Im lặng quá `LIVETALKING_HOLD_S` hoặc `stop`
  → chuyển dần về clip chờ.
- **Chuyển clip**: clip mới bắt đầu ở khung 0; trộn dần từ khung cuối của clip cũ trong `LIVETALKING_TRANSITION_S` (mặc định 0,3 s) bằng
  cơ chế `enable_transition` sẵn có. Chuyển im lặng → nói đưa cả chỉ số clip chờ về 0 khi quay lại chờ.
- **Giảm tải** (`lipskip.py`, numpy): `LIVETALKING_LIP_EVERY_N = n`: chỉ suy luận miệng cho 1/n khung trong lô, khung khác dán lại miệng vừa tạo lên khung nền
  hiện tại. `LIVETALKING_BATCH_SIZE` truyền vào `batch_size` của LiveTalking.
- **Nạp avatar**: một thư mục avatar LiveTalking cho mỗi clip (`<character_id>__<clip_id>`), nạp hết lúc khởi động (R7 TODO RAM).

## 5. Khởi động và chuẩn bị

- `scripts/livetalking/setup.ps1`: clone `https://github.com/lipku/LiveTalking` vào `vendor/livetalking`, checkout commit ghim
  (`LIVETALKING_UPSTREAM_COMMIT` = `c7269433a2b6`, main ngày 2026-11-07), áp nhánh `ailive` (TODO R2: lấy từ đâu), tạo venv, cài torch cu128 + requirements.
  Không tải model; in hướng dẫn tải tay (quickstart bước 3) sau khi người dùng duyệt ADR-048.
- `scripts/livetalking/run.ps1`: đọc `.env` của repo, chạy `python app.py --model wav2lip --transport webrtc --max_session 1 --listenport 8010`
  với các biến ở data-model §1; thêm `--batch_size` (từ `LIVETALKING_BATCH_SIZE`) và `--ailive_character <AVATAR_DIR>` (cờ thêm bằng móc `# ailive:` trong `config.py`; các cờ khác đã kiểm với `config.py` của commit ghim).
- `python -m ailive_ext.prepare <AVATAR_DIR> --json`: đọc `character.json`, chạy `genavatar` cho từng clip, đếm mặt bằng S3FD mọi khung,
  in **một** dòng JSON ra stdout: `{"status": "ready"|"failed", "fork_commit", "frame_size", "clips": {...}, "errors": [PrepareError]}`.
  Mã thoát 0 khi `ready`, 1 khi `failed`, 2 khi lỗi không lường trước. Nhật ký chi tiết ra stderr.

## 6. Kiểm thử của fork (venv fork, không GPU)

`vendor/livetalking/ailive_ext/tests/`: `test_rotation.py` (`pick_next`, `ClipScheduler`), `test_lipskip.py` (khung nào suy luận, dán
lại miệng đúng vị trí), `test_ingest.py` (cắt khung, độn khung cuối, gắn `datainfo`, `stop` xóa đệm),
`test_label.py` (nhãn có mặt ở đúng góc trên khung giả; chữ rỗng / không ASCII bị từ chối), `test_ws.py` (`/ailive/ws` và
`/ailive/health` với avatar giả: 4404, `hello`, ack, `stop`, kết nối mới thay kết nối cũ), `test_clips.py` (đọc danh sách clip, chọn
clip chờ/nói theo lô), `test_prepare.py` (kiểm clip trước `genavatar` với video nhỏ và bộ đếm mặt giả). Chạy: `vendor/livetalking/.venv/Scripts/python -m pytest ailive_ext/tests`.

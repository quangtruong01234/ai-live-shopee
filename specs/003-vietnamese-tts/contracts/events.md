# Hợp đồng sự kiện, log và cấu hình: 003-vietnamese-tts

> Bổ sung cho [001 events.md](../../001-local-reply-pipeline/contracts/events.md). Không có endpoint HTTP hay WebSocket mới.

## 1. Log JSON (thêm)

| `event` | Khi nào | Trường thêm |
|---------|---------|-------------|
| `tts_ready` | `warm_up()` xong | `provider`, `voice`, `model`?, `warm_up_s` |
| `tts_warm_up_failed` | `warm_up()` lỗi | `provider`, `kind`, `message` |
| `tts_quota_exhausted` | Lớp bọc vào trạng thái nghỉ | `provider`, `cooldown_s` |
| `tts_usage` | Đóng app | các trường `TTSUsage` (data-model §4) |

- Không log chữ đã chuẩn hóa ở mức INFO (có thể chứa tên người xem); chỉ ở DEBUG, như nội dung comment ở 001.
- `GEMINI_API_KEY` không bao giờ vào log (FR-016): formatter đã che qua `security/redact.py` (001).
- Mốc `tts_first_chunk` giữ nguyên như 001 (FR-015).

## 2. Lỗi bước `tts` (đã có từ 001, thêm `kind`)

ShowDirector ghi `error_step=tts` và `kind` vào `errors.jsonl`, trang điều khiển hiện "Lỗi ở bước tts: <thông báo>". Lượt trả
lời comment mang `kind` và thông báo trong sự kiện WebSocket `turn_finished` (`error_kind`, `error_message`, contracts/events.md
của 001); lượt kịch bản đi qua `show_error` như 004. Thông báo của `TTSEngineError` được dùng nguyên văn, không thêm tiền tố
"TTS lỗi: "; lớp bọc `SpeechTTS` gắn "Thử lại sau N giây." vào thông báo hết hạn mức. `kind` mới:

| `kind` | Nguồn | Thông báo (tiếng Việt, người vận hành thấy) |
|--------|-------|--------------------------------------------|
| `quota_exhausted` | Gemini 429, hoặc lớp bọc đang nghỉ | `Hết hạn mức giọng nói (Gemini TTS, gói miễn phí). Thử lại sau N giây.` |
| `api_error` | Gemini lỗi khác | `Gemini TTS lỗi HTTP <mã>: <mô tả>` |
| `config_error` | Thiếu model/khóa, sai tên giọng | `Nguồn giọng chưa sẵn sàng: <lý do>` |
| `model_error` | VieNeu lỗi khi tạo tiếng | `VieNeu lỗi khi đọc câu: <lý do>` |
| `timeout` | ShowDirector (001): một lần chờ chunk (đầu hoặc kế tiếp) quá `TTS_TIMEOUT_S` | `TTS quá N s` |

## 3. File phiên (thêm)

`data/sessions/<session_id>/tts_usage.json`, ghi một lần lúc đóng app:
```json
{"provider": "gemini", "requests": 182, "chars": 9120, "quota_errors": 0, "rejected_in_cooldown": 0}
```

## 4. Biến môi trường (`.env.example`, khối TTS mới)

```bash
# ---------- TTS (spec 003, ADR-024) ----------
TTS_PROVIDER=fake                 # fake | vieneu | gemini
TTS_SAMPLE_RATE=16000             # hợp đồng chung PCM16 mono 16 kHz (ADR-025)
TTS_TIMEOUT_S=5
TTS_QUOTA_COOLDOWN_S=60           # sau lỗi hết hạn mức, từ chối ngay trong N giây (không thử lại liên tục)
FAKE_TTS_DELAY_MS=0
VIENEU_VOICE=Thùy Dung            # giọng nữ miền Nam có sẵn; người dùng chọn sau khi nghe thử (T049, research R1)
VIENEU_REF_AUDIO=                 # tùy chọn: WAV đoạn mẫu do chính VIENEU_VOICE đọc, ngoài git (FR-002, research R1); trống = giọng có sẵn
VIENEU_CPU_THREADS=4              # đã đo 2 / 4 / 6 ở T049, giữ 4 (research R1)
VIENEU_MODEL_CACHE=~/.cache/ai-live/hf   # cache model riêng (581 MB), ngoài repo, không symlink (research R1)
GEMINI_TTS_MODEL=gemini-3.8-flash-tts
GEMINI_TTS_VOICE=Leda             # chốt sau khi nghe thử (SC-006); dùng chung GEMINI_API_KEY ở trên
```
Bỏ: `ELEVENLABS_API_KEY`, `ELEVENLABS_VOICE_ID`, `ELEVENLABS_MODEL_ID`, `OSS_TTS_MODEL_PATH`. `test_config` (001) tiếp tục kiểm
`Settings` và `.env.example` khớp nhau.

## 5. CLI (đã có từ 001, thêm thông tin in ra)

`uv run python -m ai_live.tts say "<câu>" --out out.wav` (FR-012) in thêm: nguồn giọng, chữ đã chuẩn hóa, số ký tự đã gửi.
Thêm lệnh con `normalize "<câu>"`: chỉ in chữ đã chuẩn hóa, không gọi nguồn giọng (FR-010).

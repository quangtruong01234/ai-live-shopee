# Quickstart: 003-vietnamese-tts

> **Mọi bước chạy trên laptop**, không cần RunPod. Ký hiệu: 🌐 cần mạng; 🔑 cần `GEMINI_API_KEY` và tính vào hạn mức free tier;
> 📦 cần model VieNeu đã tải (chỉ tải sau khi người dùng duyệt ADR-024); 🎭 cần nhân vật nhép miệng của feature 005.

## 0. Chuẩn bị

1. Kiểm tra mặc định không cần gì thêm: `uv run pytest` (mọi test chạy không mạng, không key, không model).
2. 📦 🌐 Sau khi ADR-024 được duyệt: `uv add vieneu` (bản CPU/ONNX), rồi chạy một lần để thư viện tải model về cache.
   Ghi dung lượng tải và thư mục cache vào research R1.
3. 🔑 Gemini: dùng lại `GEMINI_API_KEY` đã có trong `.env`. Mở AI Studio xem giới hạn RPM/RPD của model TTS, ghi vào research R2.

## US2: Chuyển chữ (làm trước được, không cần nguồn giọng)

1. `uv run pytest tests/unit/test_tts_normalize.py -v` → bảng ≥ 40 câu đạt 100% (SC-001).
2. Thử tay: `uv run python -m ai_live.tts normalize "Combo 250k, giảm 15%, chai 1,5L giá 259.000đ–439.000đ"`
   → `Combo hai trăm năm mươi ngàn, giảm mười lăm phần trăm, chai một phẩy năm lít giá từ hai trăm năm mươi chín ngàn đồng đến bốn trăm ba mươi chín ngàn đồng`.

## US3: Thử giọng riêng lẻ, lưu file (FR-012)

1. 📦 `TTS_PROVIDER=vieneu` trong `.env`, rồi:
   `uv run python -m ai_live.tts say "Dạ chị ơi, son này giá 259.000đ, đang giảm 15% ạ." --out out_vieneu.wav`
   → in thời gian tới chunk đầu, chữ đã chuẩn hóa; mở `out_vieneu.wav` nghe được (file `.wav` đã nằm trong `.gitignore`).
2. 🌐 🔑 `TTS_PROVIDER=gemini`, chạy cùng câu với `--out out_gemini.wav`.
3. Đổi giọng: sửa `VIENEU_VOICE` hoặc `GEMINI_TTS_VOICE`, chạy lại, nghe khác giọng (FR-011, không sửa code).
4. Lỗi hết hạn mức (không tốn hạn mức): `uv run pytest tests/unit/test_tts_speech.py -k quota -v` (lớp bọc nghỉ sau 429 giả).

## US1: Host trả lời bằng giọng thật

1. `uv run uvicorn ai_live.app.main:app --port 8000` với `TTS_PROVIDER=vieneu` (📦) hoặc `gemini` (🌐 🔑).
   Log có `tts_ready` (thời gian warm-up).
2. Mở `/host`, bấm "Bắt đầu"; mở trang điều khiển, gửi "Giá bao nhiêu vậy shop?".
   → Nghe tiếng Việt đúng dấu; phụ đề hiện `259.000đ` (dạng gốc) trong khi tiếng đọc "hai trăm năm mươi chín ngàn đồng" (FR-009).
3. Câu trả lời 3 câu: câu đầu phát trước khi câu cuối tạo xong, giữa các câu không có khoảng lặng dài (US1 #2).
4. Bấm "Bỏ qua" giữa câu: tiếng dừng ngay; CPU (VieNeu) hạ xuống trong vài giây vì phần tạo dở bị hủy (FR-014).
5. `TTS_PROVIDER=fake`: mọi thứ như 001 (US1 #3).
6. Lỗi giả lập ở bước tts, với nguồn giọng thật đang chạy:
   `curl -X POST http://127.0.0.1:8000/api/debug/fault -H "Content-Type: application/json" -d '{"step": "tts", "mode": "error", "count": 1}'`
   (lặp với `"mode": "timeout"`) → lượt báo "Lỗi ở bước tts", comment sau vẫn được trả lời bằng giọng thật (SC-004).

## SC-003 / SC-006: So sánh hai nguồn giọng

1. Lấy 10 câu trả lời mẫu (từ bộ câu hỏi `data/eval/demo_questions.json` của 001).
2. Với mỗi nguồn (📦 `vieneu`, 🌐 🔑 `gemini`), chạy ít nhất 20 lượt **không có** nhân vật nhép miệng; xem `GET /api/latency`, bước
   `first_sentence_to_tts_first_chunk` p95 ≤ 1,0 s (SC-003).
3. Nghe 10 câu, chấm "nghe rõ, đúng dấu, không đọc sai số" (SC-002, ≥ 8/10). Ghi cả giọng miền nào.
4. 🎭 Khi feature 005 chạy được: lặp bước 2 khi có nhân vật nhép miệng cùng lúc, chỉ ghi số (ADR-023).
5. Ghi bảng kết quả vào research (điểm nghe, p95 chạy riêng, p95 khi có lip-sync, `chars` trong `tts_usage.json`), rồi ghi ADR chọn
   nguồn mặc định.

## SC-005: Phiên 30 phút

1. Nguồn mặc định đã chọn, comment định kỳ (mỗi khoảng 30 giây), chạy 30 phút.
2. Kết quả: phiên không dừng vì nguồn giọng. Với Gemini: nếu hết hạn mức, trang điều khiển báo "Hết hạn mức giọng nói" và không có
   chuỗi lỗi liên tục (mỗi `TTS_QUOTA_COOLDOWN_S` giây nhiều nhất một lần gọi thật). Xem `tts_usage.json`.

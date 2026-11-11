# Cấu trúc mã nguồn

> Dùng src layout với package `ai_live`
> để tránh tên module trùng thư viện chuẩn (ví dụ `queue`).

```
src/ai_live/
├── app/           FastAPI: điểm vào, route API (comment, show, debug), trang điều khiển cho người vận hành, trang /host, /health
├── core/          Cấu hình (.env), mô hình dữ liệu dùng chung (Comment, Product, Segment...), Protocol adapter, logging
├── comments/      Adapter CommentSource: mock (gõ tay), youtube (Live Chat API), shopee (làm sau)
├── comment_queue/ Hàng đợi ưu tiên: lọc spam, chống trùng, chấm điểm ưu tiên, bỏ comment quá cũ (memory / redis)
├── products/      ProductStore: đọc file Word theo mẫu (ADR-014), giữ catalog đang nạp
├── brain/         ReplyEngine: chuỗi model OpenAI-compatible (chain_engine.py, chain_state.py, openai_compat.py; spec 008), Gemini (streaming theo câu), engine giả cho test, prompt, làm sạch câu, guardrail chỉ dùng dữ liệu sản phẩm
├── director/      ShowDirector: điều phối phiên (show kịch bản của 004 và lượt trả lời comment của 001), đo độ trễ, log phiên
├── tts/           Adapter TTSEngine: fake (test), vieneu (CPU), gemini (free tier), lớp bọc SpeechTTS; chuẩn hóa văn bản tiếng Việt (số, giá, viết tắt)
├── avatar/        Adapter AvatarRenderer: static (laptop) và livetalking (GPU, gọi fork LiveTalking)
├── qa_eval/       Lệnh `python -m ai_live.qa_eval run` (bộ câu hỏi mẫu của 001) và `script` (tự kiểm tra kịch bản của 004)
├── output/        Adapter OutputSink: webrtc, virtualcam, rtmp; overlay nhãn "AI" ghép vào frame
└── security/      Lưu và đọc phiên Shopee đã mã hóa; tiện ích che secret trong log
```

Module của show kịch bản (feature 004; luồng ở `docs/ARCHITECTURE.md` §1):

| Module | Vai trò |
|--------|---------|
| `director/show_director.py` | Bộ điều phối phiên duy nhất: bắt đầu, tạm dừng, tiếp tục, bỏ qua, kết thúc, chọn phân đoạn kế; giữ khóa `_floor` (quyền nói) giữa kịch bản và comment chen vào |
| `director/segment_planner.py` | Logic thuần (không I/O): chủ đề nào có dữ liệu, xoay vòng sản phẩm × chủ đề, lựa chọn của người vận hành |
| `director/script_runner.py` | Chạy show bằng ba tầng song song: sinh chữ (đi trước một phân đoạn) → tạo tiếng (tối đa 2 câu) → phát; chế độ dự phòng; ghi khoảng lặng |
| `director/show_stats.py` | Thống kê của một show: khoảng lặng theo nhãn (trung vị, p95, lớn nhất), số phân đoạn theo sản phẩm/chủ đề, tỷ lệ câu trùng |
| `director/faults.py` | Giả lập lỗi `llm`/`tts`/`render` dùng chung cho cả hai đường (chỉ dev, `POST /api/debug/fault`) |
| `brain/script_prompt.py` | Prompt kịch bản cho `ReplyEngine.narrate()`; phần hệ thống chỉ phụ thuộc catalog để dùng được cache của Gemini |
| `brain/sanitize.py` | `clean_spoken()`: bỏ markdown, emoji, ký hiệu trước guard; chữ đã làm sạch là chữ đọc và phụ đề (ADR-031) |
| `qa_eval/script_grader.py` | Chấm câu kịch bản trên chữ thô: qua `OutputGuard` như lúc live, thêm `bad_pronoun` và `formatting` |
| `qa_eval/script_eval.py` | Sinh phân đoạn mẫu cho mọi tổ hợp có dữ liệu, chấm, lưu, so với lần trước; `--session DIR` chấm lại một phiên đã chạy |

Thư mục khác ở gốc repo:

| Thư mục | Nội dung | Có commit không |
|---------|----------|-----------------|
| `tests/` | Unit test và bộ 10 câu hỏi mẫu (regression cho prompt); chạy được không cần GPU | Có |
| `data/products/` | Dữ liệu sản phẩm **mẫu** cho dev và test | Có (chỉ dữ liệu mẫu) |
| `data/eval/` | Bộ câu hỏi mẫu để chấm (`demo_questions.json`); kết quả ở `data/eval/runs/`, kết quả tự kiểm tra kịch bản ở `data/eval/script_runs/` | Có (trừ `runs/`, `script_runs/`, gitignore) |
| `data/rules/` | Từ cấm, từ khóa ưu tiên, cụm từ nền tảng (`platform_phrases.txt`) cho bộ lọc và guard | Có |
| `data/sessions/` | Log phiên (comment, lượt nói, lỗi, tổng hợp độ trễ; với show thêm `script_sentences.jsonl`, `show_summary_<show_id>.json`) | Không (gitignore) |
| `data/customers/` | Dữ liệu thật của khách | Không (gitignore) |
| `scripts/runpod/` | Script dựng và khởi động môi trường GPU (xem `docs/RUNPOD.md`) | Có |
| `scripts/avatar_clips/` | Notebook Kaggle/Colab tạo gương mặt AI và clip nền (ADR-036); chạy trên cloud, không chạy trên laptop | Có (chỉ notebook, kết quả không commit) |
| `models/` | Checkpoint model (Wav2Lip, MuseTalk, whisper, TTS...) | Không (gitignore) |
| `assets/avatars/` | Ảnh, video nền avatar và mẫu giọng của người mẫu | Không (gitignore) |
| `vendor/` | Fork LiveTalking (TODO: submodule hay repo riêng? ADR-004) | Chưa chốt |

Quy ước (ADR-022): tên file, định danh, docstring và comment dùng tiếng Anh. Comment tiếng Việt cũ được dịch khi sửa tới file đó.
Chữ người dùng thấy (UI, thông báo lỗi API, prompt LLM) vẫn tiếng Việt (xem `CLAUDE.md`).

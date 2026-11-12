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
├── avatar/        Adapter AvatarRenderer: static (ảnh + tiếng), livetalking (nhép miệng qua fork LiveTalking), switching (chọn theo lượt); hồ sơ nhân vật
├── qa_eval/       Lệnh `python -m ai_live.qa_eval run` (bộ câu hỏi mẫu của 001) và `script` (tự kiểm tra kịch bản của 004)
├── output/        Để dành cho OutputSink (virtualcam, rtmp) của feature OBS/RTMP; chưa có code. Ở 005 fork tự phát WebRTC và vẽ nhãn "AI"
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

Module nhép miệng (feature 005; giao diện ở `specs/005-lipsync-livetalking/contracts/adapters.md`):

| Module | Vai trò |
|--------|---------|
| `avatar/livetalking_renderer.py` | `LiveTalkingRenderer`: đẩy PCM từng câu vào `/ailive/ws` của fork, nhận ack phát (`playback_started`, `sentence_played`), đo fps của lượt; `LIVETALKING_LEAD_S` cho câu kế vào hàng sớm |
| `avatar/switching_renderer.py` | `SwitchingRenderer`: giữ cả renderer tĩnh lẫn nhép miệng, chọn theo lượt, tự về ảnh tĩnh sau lỗi liên tiếp, người vận hành bật lại (FR-022) |
| `avatar/static_renderer.py` | `StaticRenderer` (ảnh + tiếng tới trang `/host`) và Protocol `HostLink` (kênh `/host` dùng chung cho cả hai renderer) |
| `avatar/character.py` | Đọc và kiểm thư mục nhân vật `AVATAR_DIR` (`character.json`, một khách), gọi bước `prepare` trong venv của fork |
| `avatar/factory.py` | Chọn renderer theo `AVATAR_MODE` |
| `avatar/__main__.py` | `uv run python -m ai_live.avatar check\|prepare <dir>` cho người vận hành |

Thư mục khác ở gốc repo:

| Thư mục | Nội dung | Có commit không |
|---------|----------|-----------------|
| `tests/` | Unit test và bộ 10 câu hỏi mẫu (regression cho prompt); chạy được không cần GPU | Có |
| `data/products/` | Dữ liệu sản phẩm **mẫu** cho dev và test | Có (chỉ dữ liệu mẫu) |
| `data/eval/` | Bộ câu hỏi mẫu để chấm (`demo_questions.json`); kết quả ở `data/eval/runs/`, kết quả tự kiểm tra kịch bản ở `data/eval/script_runs/` | Có (trừ `runs/`, `script_runs/`, gitignore) |
| `data/rules/` | Từ cấm, từ khóa ưu tiên, cụm từ nền tảng (`platform_phrases.txt`), cụm khẳng định không có căn cứ (`claim_phrases.txt`, ADR-050) cho bộ lọc và guard | Có |
| `data/sessions/` | Log phiên (comment, lượt nói, lỗi, tổng hợp độ trễ; với show thêm `script_sentences.jsonl`, `show_summary_<show_id>.json`) | Không (gitignore) |
| `data/customers/` | Dữ liệu thật của khách | Không (gitignore) |
| `scripts/runpod/` | Script dựng và khởi động môi trường GPU (xem `docs/RUNPOD.md`) | Có |
| `scripts/livetalking/` | `setup.ps1` dựng fork LiveTalking vào `vendor/livetalking/` (venv riêng, không tải model), `run.ps1` bật fork với biến lấy từ `.env` (quickstart 005 bước 1, 5) | Có |
| `scripts/selfcheck/` | `lipsync_check.py`: ghi và chấm một lượt nhép miệng từ bộ ghi luồng của fork, không cần người xem (quickstart 005 bước 11) | Có |
| `out/` | Bản ghi, ảnh chụp, số đo tự kiểm (có gương mặt nhân vật) | Không (gitignore) |
| `scripts/avatar_clips/` | Notebook Kaggle/Colab tạo gương mặt AI và clip nền (ADR-036); chạy trên cloud, không chạy trên laptop | Có (chỉ notebook, kết quả không commit) |
| `models/` | Checkpoint model (Wav2Lip, MuseTalk, whisper, TTS...) | Không (gitignore) |
| `assets/avatars/` | Ảnh, video nền avatar và mẫu giọng của người mẫu | Không (gitignore) |
| `vendor/livetalking/` | Fork LiveTalking (nhánh `ailive`, commit ghim): upstream cộng gói `ailive_ext/` (nhận tiếng `/ailive/ws`, nhãn AI, xoay clip, `prepare`, bỏ bớt khung suy luận, bộ ghi luồng). Chạy process riêng, venv riêng (ADR-042) | Không (gitignore, ngoài git) |

Quy ước (ADR-022): tên file, định danh, docstring và comment dùng tiếng Anh. Comment tiếng Việt cũ được dịch khi sửa tới file đó.
Chữ người dùng thấy (UI, thông báo lỗi API, prompt LLM) vẫn tiếng Việt (xem `CLAUDE.md`).

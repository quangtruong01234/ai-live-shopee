# Cấu trúc mã nguồn

> Dùng src layout với package `ai_live`
> để tránh tên module trùng thư viện chuẩn (ví dụ `queue`).

```
src/ai_live/
├── app/           FastAPI: điểm vào, route API, trang điều khiển cho người vận hành, /health
├── core/          Cấu hình (.env), mô hình dữ liệu dùng chung (Comment, Product), logging và đo độ trễ
├── comments/      Adapter CommentSource: mock (gõ tay), youtube (Live Chat API), shopee (làm sau)
├── comment_queue/ Hàng đợi ưu tiên: lọc spam, chống trùng, chấm điểm ưu tiên, bỏ comment quá cũ (memory / redis)
├── products/      ProductStore: đọc dữ liệu sản phẩm JSON/SQLite, tìm sản phẩm liên quan theo từ khóa
├── brain/         ReplyEngine: gọi Gemini API (streaming theo câu), prompt, guardrail chỉ dùng dữ liệu sản phẩm
├── director/      ShowDirector: điều phối lượt nói, kịch bản khi rảnh, ngắt lời, câu đệm che độ trễ
├── tts/           Adapter TTSEngine: fake (test), elevenlabs, oss; chuẩn hóa văn bản tiếng Việt (số, giá, viết tắt)
├── avatar/        Adapter AvatarRenderer: static (laptop) và livetalking (GPU, gọi fork LiveTalking)
├── qa_eval/       Bộ chấm và lệnh `python -m ai_live.qa_eval run`: chạy bộ câu hỏi mẫu qua ReplyEngine + OutputGuard, ghi báo cáo
├── output/        Adapter OutputSink: webrtc, virtualcam, rtmp; overlay nhãn "AI" ghép vào frame
└── security/      Lưu và đọc phiên Shopee đã mã hóa; tiện ích che secret trong log
```

Thư mục khác ở gốc repo:

| Thư mục | Nội dung | Có commit không |
|---------|----------|-----------------|
| `tests/` | Unit test và bộ 10 câu hỏi mẫu (regression cho prompt); chạy được không cần GPU | Có |
| `data/products/` | Dữ liệu sản phẩm **mẫu** cho dev và test | Có (chỉ dữ liệu mẫu) |
| `data/eval/` | Bộ câu hỏi mẫu để chấm (`demo_questions.json`); kết quả chạy ở `data/eval/runs/` | Có (trừ `runs/`, gitignore) |
| `data/sessions/` | Log phiên (comment, lượt nói, lỗi, tổng hợp độ trễ) | Không (gitignore) |
| `data/customers/` | Dữ liệu thật của khách | Không (gitignore) |
| `scripts/runpod/` | Script dựng và khởi động môi trường GPU (xem `docs/RUNPOD.md`) | Có |
| `models/` | Checkpoint model (Wav2Lip, MuseTalk, whisper, TTS...) | Không (gitignore) |
| `assets/avatars/` | Ảnh, video nền avatar và mẫu giọng của người mẫu | Không (gitignore) |
| `vendor/` | Fork LiveTalking (TODO: submodule hay repo riêng? ADR-004) | Chưa chốt |

Quy ước (ADR-022): tên file, định danh, docstring và comment dùng tiếng Anh. Comment tiếng Việt cũ được dịch khi sửa tới file đó.
Chữ người dùng thấy (UI, thông báo lỗi API, prompt LLM) vẫn tiếng Việt (xem `CLAUDE.md`).

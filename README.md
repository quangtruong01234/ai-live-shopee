# AI Live Shopee

Dịch vụ livestream bán hàng với **host AI**: avatar nhép miệng theo thời gian thực, giọng tiếng Việt, tự dẫn show giới thiệu
sản phẩm từ dữ liệu khách cung cấp.

- **Mô hình kinh doanh:** làm trọn gói cho khách. Khách chỉ đưa dữ liệu sản phẩm; bên mình lo avatar, giọng, kịch bản và vận hành
  buổi live.
- **Giai đoạn hiện tại: DEMO.** Một khách, một sản phẩm chính và 2–3 sản phẩm phụ. Demo chạy ngoài Shopee: chia sẻ tab Chrome
  (có tiếng) qua Google Meet.
- **Giai đoạn sau:** Shopee Live qua OBS (RTMP + Stream Key).

Tiến độ chi tiết: [`progress/STATUS.md`](progress/STATUS.md) và [`progress/FEATURES.md`](progress/FEATURES.md).

## Ràng buộc bắt buộc

1. **Chỉ tạo hình và tiếng theo thời gian thực.** Shopee cấm phát video quay sẵn (kể cả video AI) làm nội dung live. Video dự
   phòng 2–3 phút chỉ dùng cho demo Meet.
2. **Nhãn "AI" luôn hiện trên màn hình**, ghép thẳng vào khung hình trong pipeline. Trang `/host` và `/obs` cố ý không đọc query
   string để không có cách ẩn nhãn qua URL.
3. **Một host AI cho một tài khoản.** Avatar và giọng chỉ thuộc về một khách, một shop.
4. **Có giấy đồng ý đã ký** của người mẫu cho cả gương mặt lẫn giọng nói trước khi dùng.
5. **Chỉ trả lời dựa trên dữ liệu sản phẩm.** Không bịa giá, khuyến mãi, tồn kho, công dụng, tuyên bố y tế hay chính sách đổi trả.
6. **Secret chỉ nằm trong `.env`**, không commit. Phiên Shopee của khách được mã hóa và chỉ lưu trên máy chạy live.

Toàn văn: [`.specify/memory/constitution.md`](.specify/memory/constitution.md) và [`CLAUDE.md`](CLAUDE.md).

## Kiến trúc

Pipeline 6 khâu, mỗi khâu là một adapter sau một interface chung (`typing.Protocol`), chọn bằng biến môi trường:

```
Nguồn comment → Hàng đợi ưu tiên → ReplyEngine (LLM) → TTS tiếng Việt → AvatarRenderer → Đầu ra
```

| Khâu | Biến môi trường | Lựa chọn |
|------|-----------------|----------|
| Nguồn comment | `COMMENT_SOURCE` | `mock` (gõ tay); `shopee` làm sau |
| Sinh câu trả lời | `REPLY_ENGINE` | `chain` (chuỗi model miễn phí, tự chuyển khi lỗi), `gemini`, `fake` |
| Giọng nói | `TTS_PROVIDER` | `vieneu` (CPU, dùng cho phiên live), `gemini` (free tier, chỉ thử ngắn), `fake` |
| Avatar | `AVATAR_MODE` | `static` (ảnh + tiếng), `livetalking` (nhép miệng qua fork LiveTalking, Wav2Lip/MuseTalk) |
| Đầu ra | `OUTPUT_MODE` | `meet` (chia sẻ tab `/host`), `obs` (trang `/obs` làm OBS Browser Source) |

Nội dung chính của host là **show kịch bản** do `ShowDirector` sinh theo thời gian thực từ dữ liệu sản phẩm (feature 004). Phần đọc
chat để trả lời người xem đang tạm hoãn (ADR-026); đường comment của feature 001 vẫn giữ trong code làm công cụ thử.

Mục tiêu độ trễ: câu đầu của show ≤ 5 s, khoảng lặng giữa các câu p95 ≤ 1,5 s; comment → miệng bắt đầu nói < 5 s p95.

Chi tiết: [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md), cấu trúc mã nguồn: [`src/README.md`](src/README.md).

## Bắt đầu nhanh

Cần [uv](https://docs.astral.sh/uv/) và Python 3.12 (uv tự cài theo `.python-version`).

```bash
uv sync
cp .env.example .env        # rồi điền secret (key LLM, ...)
uv run uvicorn ai_live.app.main:app --reload --port 8000
```

Mặc định trong `.env.example` chạy được mà không cần GPU: `AVATAR_MODE=static`, `TTS_PROVIDER=fake`. Với `REPLY_ENGINE=fake` thì
không cần cả key LLM.

| Trang | Dùng cho |
|-------|----------|
| `http://localhost:8000/` | Trang điều khiển cho người vận hành: nạp sản phẩm, bắt đầu/tạm dừng show, cảnh báo |
| `/host` | Trang host để chia sẻ lên Google Meet (`OUTPUT_MODE=meet`) |
| `/obs` | Trang host cho OBS Browser Source (`OUTPUT_MODE=obs`) |
| `/health` | Kiểm tra sức khỏe |

### Kiểm thử và lint

```bash
uv run pytest                                          # mặc định bỏ qua test `live_llm` (gọi LLM thật)
uv run ruff check . && uv run ruff format --check .
```

Logic pipeline chạy được hoàn toàn không cần GPU (nguồn comment giả, TTS giả, renderer tĩnh).

### Lệnh riêng từng khâu

```bash
uv run python -m ai_live.products validate data/products/demo.docx   # kiểm file nội dung sản phẩm
uv run python -m ai_live.brain ask "<comment>"                       # LLM + guard, in từng câu kèm thời gian
uv run python -m ai_live.tts say "<câu>" --out f.wav                 # tạo giọng một câu
uv run python -m ai_live.ops readiness                               # kiểm tra trước buổi demo
```

Danh sách đầy đủ ở [`src/README.md`](src/README.md).

### Nhép miệng (LiveTalking)

Fork LiveTalking nằm ở `vendor/livetalking/` (không đưa vào git), dùng venv riêng:

```powershell
powershell scripts/livetalking/setup.ps1     # clone, ghim commit, tạo nhánh ailive và venv
powershell scripts/livetalking/run.ps1
```

Script không tải trọng số model; tải bằng tay theo hướng dẫn script in ra, sau khi kiểm giấy phép. Laptop dev (GTX 1650 Ti 4 GB) chạy
được nhép miệng ở FPS/độ phân giải thấp (ADR-023). GPU thuê trên RunPod chỉ là dự phòng: [`docs/RUNPOD.md`](docs/RUNPOD.md).

## Quy trình làm việc

Feature mới đi qua quy trình Spec-Driven 7 bước (`/sdd.specify` → `/sdd.clarify` → `/sdd.plan` → `/sdd.tasks` → `/sdd.analyze` →
`/sdd.implement` → `/update-context`), mỗi feature một thư mục `specs/NNN-slug/`. Làm thẳng trên nhánh `main`. Chi tiết:
[`docs/WORKFLOW.md`](docs/WORKFLOW.md).

Quy ước code: định danh, comment và commit bằng tiếng Anh; tài liệu (`docs/`, `specs/`) và chữ người dùng thấy bằng tiếng Việt
(ADR-022). Cấu hình chỉ đọc từ biến môi trường qua `pydantic-settings`.

## Cấu trúc thư mục

```
src/ai_live/     Mã nguồn (src layout): app, core, comments, comment_queue, products, brain, director, tts, avatar, scene, ops, ...
tests/           unit, integration, contract, live (gọi dịch vụ thật)
specs/           Spec, plan, tasks của từng feature (001–010)
docs/            PRD, kiến trúc, quyết định (ADR), lộ trình, rủi ro, runbook
progress/        Trạng thái hiện tại, danh mục feature, câu hỏi mở, nhật ký
scripts/         LiveTalking, notebook Kaggle tạo avatar/huấn luyện, công cụ khẩu hình, tạo nội dung demo
data/            Dữ liệu demo và luật (lọc spam, ưu tiên, cụm từ cấm)
```

Không có trong git: `.env`, `vendor/`, `assets/avatars/`, `assets/scenes/`, trọng số model, ảnh/video/giọng của người mẫu, dữ liệu
khách.

## Tài liệu

| File | Nội dung |
|------|----------|
| [`docs/PRD.md`](docs/PRD.md) | Phạm vi demo, giai đoạn 2, tiêu chí thành công |
| [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) | Pipeline, sơ đồ, interface adapter, ngân sách độ trễ |
| [`docs/DECISIONS.md`](docs/DECISIONS.md) | Nhật ký quyết định (ADR) |
| [`docs/ROADMAP.md`](docs/ROADMAP.md) | Các mốc Demo → Pilot → Shopee thật → Nhiều khách |
| [`docs/RISKS.md`](docs/RISKS.md) | Rủi ro chính sách, kỹ thuật, giấy phép, GPU, bảo mật |
| [`docs/RUNBOOK.md`](docs/RUNBOOK.md) | Checklist ngày demo, xử lý sự cố, video dự phòng |
| [`docs/VENDORS.md`](docs/VENDORS.md) | SDK/API ứng viên cho từng khâu |

## Giấy phép

Repo riêng tư, chưa chọn giấy phép. Phải kiểm giấy phép của LiveTalking (yêu cầu watermark), Wav2Lip, MuseTalk, S3FD, whisper và
model TTS trước khi thương mại hóa; theo dõi ở [`docs/RISKS.md`](docs/RISKS.md).

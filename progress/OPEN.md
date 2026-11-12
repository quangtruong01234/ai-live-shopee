# Câu hỏi và quyết định đang chờ

> Chỉ liệt kê việc **chờ người dùng**. Giải quyết xong thì sửa nguồn gốc (spec, ADR, hiến pháp, doc), rồi xóa dòng ở đây và ghi LOG.
> Thứ tự trong mỗi mục: ảnh hưởng lớn trước.

## 1. Câu hỏi làm rõ của spec (`[NEEDS CLARIFICATION]`)

| Feature | Vị trí | Câu hỏi | Giải bằng |
|---------|--------|---------|-----------|
| — | — | Không có câu nào đang mở | — |

## 2. ADR chưa chốt (`Đề xuất`)

| ADR | Nội dung chờ | Chặn gì |
|-----|-------------|---------|
| [ADR-010](../docs/DECISIONS.md) | Cơ chế mã hóa phiên Shopee | M2 |
| [ADR-021](../docs/DECISIONS.md) | App desktop cài trên Windows | Sau demo |

## 3. Hiến pháp chờ sửa (`/sdd.constitution`)

Không có. Hiến pháp ở 1.2.0 (sửa 2026-11-01, [ADR-029](../docs/DECISIONS.md): Điều V, VI, VIII).

## 4. `TODO:` quan trọng trong docs

| Nguồn | Câu hỏi |
|-------|---------|
| [ADR-047](../docs/DECISIONS.md), [005 quickstart](../specs/005-lipsync-livetalking/quickstart.md) bước 9 | Đổi mặc định `LIVETALKING_LEAD_S` trong `.env.example` từ 0 thành 2,5? (lặng giữa câu nghe được p95 2,98 s → 0,76–1,0 s, 0 lỗi; phải nhỏ hơn `LIVETALKING_FIRST_FRAME_TIMEOUT_S`) |
| [ADR-041](../docs/DECISIONS.md), 005 quickstart bước 9 (T075) | Chọn `LIVETALKING_BATCH_SIZE` 16 (show ~24 khung/giây, khung đầu 1,36 s) hay 8 (~20 khung/giây, khung đầu 0,73 s)? Có làm bộ clip nhỏ hơn (R8) hoặc thử RunPod (tốn tiền) không? |
| [005 quickstart](../specs/005-lipsync-livetalking/quickstart.md) bước 9 | Xem bản ghi một lượt trả lời comment: miệng chỉ ~18 khung/giây vì VieNeu vừa tổng hợp vừa phát. Chấp nhận được không? |
| [ADR-050](../docs/DECISIONS.md), `data/rules/claim_phrases.txt` | Duyệt danh sách 38 cụm "khẳng định không có căn cứ" mà guard chặn. Câu trả lời comment trung thực kiểu "chưa có thông tin về kích ứng" cũng bị chặn và thay bằng câu từ chối: chấp nhận được không? |
| [005 quickstart](../specs/005-lipsync-livetalking/quickstart.md) bước 8 | Clip nói có đoạn đầu ngửa/nghiêng (`talk_02` khung ~64–120, `talk_01` ~32–60), miệng dán mở chỉ ~một nửa: cắt chỉ lấy đoạn mặt thẳng hay làm lại clip nói? Và duyệt sửa spec 005 phiên 2026-11-12 (giữ clip nói qua các câu, `HOLD_S` 2,5) |
| [PRD.md](../docs/PRD.md) §3 số 1 | Có chấm độ khớp miệng theo thang 1–5 không? |
| [PRD.md](../docs/PRD.md) | Avatar là người thật (ai làm mẫu) hay nhân vật AI? Giọng clone từ người mẫu hay giọng có sẵn? |
| [PRD.md](../docs/PRD.md) | Giới hạn ngân sách mỗi buổi demo (GPU, API)? |
| [ROADMAP.md](../docs/ROADMAP.md) | Ngày dự kiến demo với khách? |
| [004 research](../specs/004-show-director/research.md) R14 | RPM/RPD thật của từng model trong chuỗi ADR-035 (trước là Gemini free tier) (quyết định số phân đoạn mỗi lần tự kiểm tra) |
| [ADR-036](../docs/DECISIONS.md), [RISKS](../docs/RISKS.md) G8 | Trước khi khách trả tiền: điều khoản Kaggle/Colab có cho dùng thương mại không (không thì tạo lại clip trên RunPod)? |
| [RISKS](../docs/RISKS.md) P2 | Shopee có tính video nền lặp (miệng sinh realtime) là nội dung quay sẵn không? Khách hỏi lúc đăng ký live AI |
| [RISKS](../docs/RISKS.md) L10 | License chính xác của checkpoint ảnh/video (cả VAE, text encoder) trước khi thu tiền khách |
| [ADR-035](../docs/DECISIONS.md) | Hạn mức neuron/ngày thật của Cloudflare Workers AI (xem dashboard Cloudflare) |
| [ADR-035](../docs/DECISIONS.md) | IteraCompute: có thêm key không (khuyến mãi hết 2026-11-24, chưa đọc chính sách bảo mật)? Điều khoản free của Cloudflare, Groq |
| [WORKFLOW.md](../docs/WORKFLOW.md) §2b | Repo đã có commit: có chạy sub-agent trong worktree riêng không? |

Danh sách đầy đủ: `grep -rn "TODO:" docs specs`.

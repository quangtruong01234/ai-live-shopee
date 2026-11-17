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
| [ADR-057](../docs/DECISIONS.md) | 007: canh show chỉ cảnh báo + tự bỏ câu kẹt một lần; video dự phòng ghi từ đường realtime (`verbatim`). Xác nhận sau khi xem video dự phòng (dòng 007 ở §4) | M1d |
| [ADR-060](../docs/DECISIONS.md) | Thử Ultralight với video huấn luyện tạo bằng InfiniteTalk trên Kaggle (đã xác nhận 2026-11-17, `ffmpeg` đã cài). Nhân vật mới `demo_host_02` (ngồi bàn trong shop, người dùng yêu cầu 2026-11-17): 8 ảnh ứng viên đã tạo (`make_host_scene.ipynb`, 25 s/ảnh trên T4), lần 1 chọn `scene_chest_up_seed202`; người dùng thấy da "nhựa" nên lần 2 thử làm lại da (img2img nhiễu 0,25/0,35/0,45) và 4 mặt mới với prompt ưu tiên ảnh thật, mình chọn mặt mới `scene_real_chest_up_seed606` (da lì, mặt bình thường, môi khép, tay sạch, không logo; ảnh cũ giữ ở `training/start_seed202_kaggle.png`). **Chờ người dùng:** duyệt ảnh seed 606; tạo dataset Kaggle riêng tư `ai-live-infinitetalk-input` từ `assets/avatars/demo_host_02/training/kaggle_input/` (`start.png` + `preview.wav`) để chạy thử 13 giây | Lần thử Ultralight |
| [ADR-061](../docs/DECISIONS.md) | Sửa ảnh host seed 606 cho giống ảnh chụp thật bằng Qwen-Image-Edit-2511 (GGUF Q4_K_M + LoRA Lightning 8 bước) trên Kaggle, người dùng cho triển khai 2026-11-17. Notebook `scripts/avatar_clips/edit_host_photo.ipynb`, chạy ở Kaggle `jintran0501/ai-host-edit-demo-host-02`. **Chờ người dùng:** chọn ảnh từ `contact_sheet_edit.jpg` và `face_compare_edit.jpg`; sau đó làm lại `training/kaggle_input/start.png`. TODO: kiểm lại giấy phép LoRA Lightning và bản GGUF trước khi khách trả tiền | Lần thử Ultralight |
| [ADR-058](../docs/DECISIONS.md) | 006: bỏ YouTube (M1c); đầu ra OBS bằng Browser Source trang `/obs`, vai obs ưu tiên hơn trang host, `OUTPUT_MODE=meet` hoặc `obs`. Xác nhận ở gói duyệt 006 | M2 |

## 3. Hiến pháp chờ sửa (`/sdd.constitution`)

Không có. Hiến pháp ở 1.2.0 (sửa 2026-11-01, [ADR-029](../docs/DECISIONS.md): Điều V, VI, VIII).

## 4. `TODO:` quan trọng trong docs

| Nguồn | Câu hỏi |
|-------|---------|
| [007 quickstart](../specs/007-demo-readiness/quickstart.md) §5, SC-006 (T058) | Xem lại video dự phòng `out/backup_video/backup_20261113-1634_demo_customer_01.mp4` (157 s, nhãn "AI" mọi khung, miệng khớp tiếng theo bộ chấm): tiếng khớp miệng, đúng sản phẩm? Thử phát qua Meet có tiếng. Đạt thì xác nhận ADR-057 |
| [007 quickstart](../specs/007-demo-readiness/quickstart.md) §5 | Trước demo xóa dòng `AILIVE_RECORD_DIR=out/selfcheck` trong `.env` (fork tự nạp `.env`, nên còn dòng này là còn ghi luồng; lệnh kiểm trước demo báo `LỖI`). Mình không sửa `.env` của bạn |
| [007 quickstart](../specs/007-demo-readiness/quickstart.md) §6 | Tổng duyệt 30 phút với LLM thật (tốn hạn mức free) ở T-1 ngày để chấm tiêu chí 3 và 4 thật; lần đo GPU với `REPLY_ENGINE=fake` chỉ đạt SC-004 (p95 lặng 3,0 s với `LIVETALKING_LEAD_S` 0; mặc định nay là 2,5, đo T075 0,86 s) |
| [010 quickstart](../specs/010-natural-mouth-shapes/quickstart.md) §7, SC-004 | Chấm gói xem mù `out/mouth/runs/r4/ab/PHIEU.md` (≥ 3 người, 4 cặp ~20 s): bản nào miệng giống người hơn? Nếu `shift=-1` thắng thì đổi mặc định `LIVETALKING_MOUTH_METHOD` (ADR mới thay ADR-055) |
| [RUNBOOK.md](../docs/RUNBOOK.md) | Bản nháp runbook demo: ai là người vận hành, ai là người dẫn? Meet chạy trên máy demo hay máy thứ hai? Sự cố quá bao lâu thì chuyển sang video dự phòng (đề xuất 1 phút)? |
| [RUNBOOK.md](../docs/RUNBOOK.md) §6, kiểm 2026-11-17 | `.env` còn `APP_ENV=dev`, `REPLY_ENGINE=fake`, `OUTPUT_MODE=webrtc` (tên cũ) nên lệnh kiểm trước demo báo `LỖI`; sửa theo bảng RUNBOOK §6 trước tổng duyệt. Mình không sửa `.env` của bạn |
| [ROADMAP.md](../docs/ROADMAP.md) M2, [VENDORS.md](../docs/VENDORS.md) "Sản phẩm cùng loại" | Thứ tự ưu tiên sau demo: (1) license nhép miệng, (2) trả lời bình luận Shopee (đảo ADR-026), (3) chạy ổn 4 → 8 → 15 giờ. Đồng ý không? |
| [RISKS.md](../docs/RISKS.md) P9, P10 | Shopee Việt Nam bắt khai báo nội dung AI trên Shopee Live bằng cách nào (nút khai báo, nhãn trên hình, bình luận ghim)? Khách hỏi Shopee lúc xin whitelist. Hợp đồng ghi ai chịu trách nhiệm về lời host AI nói? |
| [RISKS.md](../docs/RISKS.md) L2, L4, L11 | Trước M2 (thu tiền): Wav2Lip gốc ghi rõ cấm thương mại. Người dùng có muốn gửi thư hỏi Sync Labs (điều kiện thương mại) và tác giả LiveTalking (license checkpoint `wav2lip256`, logo trên YouTube/Shopee) không? Mình không tự gửi thư ra ngoài. Không xin được thì cần hướng khác (bản thương mại LiveTalking, model lip-sync có license rõ; ADR mới) |
| [RISKS](../docs/RISKS.md) Q22, 010 research R10, [R13](../specs/010-natural-mouth-shapes/research.md) | Người dùng chọn hướng 2 (Ultralight) ngày 2026-11-17, xem ADR-060 ở §2. Song song vẫn có thể quay clip nói mới (miễn phí). Nếu Ultralight trượt: hỏi giá bản thương mại LiveTalking hoặc thuê RunPod chạy MuseTalk (tốn tiền) |
| [ADR-051](../docs/DECISIONS.md), [ADR-052](../docs/DECISIONS.md) | Xác nhận hai ADR tự chốt cho 009 (Pillow + font máy; app vẽ cảnh, fork trộn trước watermark/nhãn, bộ cảnh ngoài git) |
| [009 quickstart](../specs/009-live-scene-layout/quickstart.md) §9, SC-007 | Ảnh thật của khách cho từng sản phẩm (bộ demo đang dùng ảnh "ẢNH MẪU"): mình cắt nền tay, ghi `provenance.json`, người dùng đặt ảnh gốc cạnh ảnh đã chỉnh để xác nhận |
| [009 spec](../specs/009-live-scene-layout/spec.md) SC-006 | 3 người xem so hai đoạn 1 phút có/không cảnh (gộp với 005 T068) |
| [006 quickstart](../specs/006-obs-output/quickstart.md) §5 "Gói duyệt" | Cho phép chạy OBS portable (`%LOCALAPPDATA%/ai-live/obs`, bộ phân quyền chặn) để làm T029; thêm nguồn `/obs` trong OBS thật theo RUNBOOK §8 và bấm giờ (SC-001); nghe/xem bản ghi OBS; xác nhận ADR-058 và ADR-059 (đã tự chốt); khi tắt cảnh 009 nhãn "AI" nằm ở dải đen trên ảnh, có cần đưa vào trong ảnh? |
| [001 quickstart](../specs/001-local-reply-pipeline/quickstart.md) (T100) | `.env` đặt `LIVETALKING_URL` cổng 8010, trùng nếu chạy app ở 8010: đổi cổng fork hay cổng app? Quickstart 001 còn ghi `REPLY_ENGINE=gemini`, sửa thành `chain` khi chạy lần hai. Kiểm Word chưa đủ: chưa thử Word giao diện tiếng Việt, Google Docs (cần đăng nhập Google của bạn), WPS (chưa cài) |
| [RISKS](../docs/RISKS.md) L12 | License dùng Segoe UI / Arial trong luồng thương mại, hay đổi sang font OFL (Be Vietnam Pro, cần ADR)? |
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

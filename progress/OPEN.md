# Câu hỏi và quyết định đang chờ

> Chỉ liệt kê việc **chờ người dùng**. Giải quyết xong thì sửa nguồn gốc (spec, ADR, hiến pháp, doc), rồi xóa dòng ở đây và ghi LOG.
> Thứ tự trong mỗi mục: ảnh hưởng lớn trước.

## 1. Câu hỏi làm rõ của spec (`[NEEDS CLARIFICATION]`)

| Feature | Vị trí | Câu hỏi | Giải bằng |
|---------|--------|---------|-----------|
| – | – | Hiện không còn câu nào | – |

## 2. ADR chưa chốt (`Đề xuất`)

| ADR | Nội dung chờ | Chặn gì |
|-----|-------------|---------|
| [ADR-010](../docs/DECISIONS.md) | Cơ chế mã hóa phiên Shopee | M2 |
| [ADR-021](../docs/DECISIONS.md) | App desktop cài trên Windows | Sau demo |
| [ADR-057](../docs/DECISIONS.md) | 007: canh show chỉ cảnh báo + tự bỏ câu kẹt một lần; video dự phòng ghi từ đường realtime (`verbatim`). Xác nhận sau khi xem video dự phòng (dòng 007 ở §4) | M1d |
| [ADR-060](../docs/DECISIONS.md) | Thử Ultralight với video huấn luyện tạo bằng InfiniteTalk trên Kaggle (đã xác nhận 2026-11-17, `ffmpeg` đã cài). Nhân vật mới `demo_host_02` (ngồi bàn trong shop, người dùng yêu cầu 2026-11-17): 8 ảnh ứng viên đã tạo (`make_host_scene.ipynb`, 25 s/ảnh trên T4), lần 1 chọn `scene_chest_up_seed202`; người dùng thấy da "nhựa" nên lần 2 thử làm lại da (img2img nhiễu 0,25/0,35/0,45) và 4 mặt mới với prompt ưu tiên ảnh thật, mình chọn mặt mới `scene_real_chest_up_seed606` (da lì, mặt bình thường, môi khép, tay sạch, không logo; ảnh cũ giữ ở `training/start_seed202_kaggle.png`). Ảnh seed 606 đã sửa (ADR-061) và được duyệt 2026-11-18, `start.png` đã làm lại. Người dùng tạo dataset `jintran0501/ai-live-infinitetalk-input` 2026-11-18 (khớp file trong máy); bản thử 13 giây ở Kaggle `jintran0501/ai-host-infinitetalk-demo-host-02` lỗi 3 lần (version 1–3) vì dataset không được gắn: trường `datasetDataSources`/`datasetDataSourcesSetter` của MCP không có tác dụng, kagglehub không gắn được dataset khi chạy batch. Version 4 (người dùng gắn dataset trên giao diện) lỗi ở nút wav2vec vì transformers 5; đã ghim `transformers==4.57.6`. Version 5 (kiểm 2026-11-18) dừng sau khoảng 76 giây ở "Không thấy start.png": đẩy code bằng API làm mất dataset đã gắn (transformers 4.57.6 đã cài đúng). Version 6 (dataset gắn trên giao diện) qua được wav2vec (bản ghim transformers đúng) và sinh xong cửa sổ đầu 81 khung, nhưng **quá chậm trên T4**: 6 bước × khoảng 261 giây = 26,5 phút cho mỗi cửa sổ (72 khung mới), khoảng 22 giây GPU cho mỗi khung. Bản thử 13,5 giây cần khoảng 2,2 giờ; video huấn luyện 4 phút (khoảng 84 cửa sổ) cần khoảng 37 giờ, vượt hạn mức GPU Kaggle mỗi tuần. Sau cửa sổ đầu ComfyUI chết không để lại lỗi khi nạp lại model GGUF (RAM giới hạn 30 GB, ComfyUI ghim 14 GB bộ nhớ; nhiều khả năng bị hệ thống giết vì hết RAM, chưa xác nhận). Notebook còn lỗi đếm khung: wrapper lưu khung vào thư mục con `frames/<thời gian>_infinitetalk_output/`, notebook chỉ tìm `frames/frame_*.png`. Người dùng chọn 2026-11-18: thử MuseTalk 1.5 làm "thầy" thay InfiniteTalk (dòng ADR-063) | Lần thử Ultralight |
| [ADR-063](../docs/DECISIONS.md) | Thử MuseTalk 1.5 làm "thầy" tạo video huấn luyện Ultralight (người dùng đồng ý 2026-11-18). Notebook `scripts/avatar_clips/musetalk_compare.ipynb` ở Kaggle `jintran0501/ai-host-musetalk-compare-demo-host-02` (version 5 chạy xong 2026-11-18: 5,4–7,2 khung/giây trên T4, VRAM 6,86 GB; chấm sơ bộ qua ảnh: miệng mở ít, mờ, ít răng hơn InfiniteTalk, nghiêng về không đạt). **Người dùng cần làm:** mở `C:\Users\Quang Truong\Downloads\musetalk_compare_v1\`, xem `side_by_side.mp4` và `mouth_closeup.mp4` có tiếng (đã xem 2026-11-18: chọn dùng cả hai, MuseTalk làm thầy dev, InfiniteTalk làm thầy prod, dòng ADR-064). TODO: kiểm giấy phép trọng số BiSeNet face-parse trước khi khách trả tiền | Lần thử Ultralight |
| [ADR-064](../docs/DECISIONS.md) | Hai "thầy" cho Ultralight, đổi bằng biến `TEACHER` (người dùng chọn 2026-11-18). **Dev:** video MuseTalk xong 2026-11-18; huấn luyện `ai-host-train-ultralight-demo-host-02` version 3 (`TEACHER = "musetalk"`, T4) xong 2026-11-19 (200 epoch), đã cài trên laptop (011 T036). Công cụ trên laptop đã sẵn (fork, 2026-11-19): `python -m ailive_ext.ultralight install` dựng avatar `demo_host_02__ultralight_<thầy>` + `demo_host_02__w2l_<thầy>` từ cùng khung hình, và phương pháp `ultralight` trong benchmark 010. Khi huấn luyện xong: Claude tải đầu ra, xem `loss.png`/ảnh preview, chạy install và benchmark; **người dùng** xem kết quả. **Live:** dùng Ultralight trong show cần feature tích hợp mới qua `/sdd.specify` (ADR-064 mục 4: chọn mô hình khi live, `run.ps1` chế độ ultralight, `character.json`/chuẩn bị và đồng ý cho `demo_host_02`), đã mở feature 011 (Clarified 2026-11-19). **Prod:** không bắt buộc cho buổi demo (ADR-066: model thầy MuseTalk đạt ngưỡng thì demo dùng nó); video InfiniteTalk 3–5 phút cần GPU thuê, hỏi giá trước khi bật. TODO: thử `EXTRA_MARGIN` 15–20 nếu miệng mở ít; chọn mô hình khi live (feature 011) | Lần thử Ultralight |
| [ADR-061](../docs/DECISIONS.md) | Sửa ảnh host seed 606 cho giống ảnh chụp thật bằng Qwen-Image-Edit-2511 (GGUF Q4_K_M + LoRA Lightning 8 bước) trên Kaggle, người dùng cho triển khai 2026-11-17. Notebook `scripts/avatar_clips/edit_host_photo.ipynb`, chạy ở Kaggle `jintran0501/ai-host-edit-demo-host-02`. Chạy xong 2026-11-18 (1 giờ 59 phút, 12 ảnh, ảnh tải về `assets/avatars/demo_host_02/run3/`). Người dùng chọn `edit/seed11_combined.png` 2026-11-18; `training/kaggle_input/start.png` 480×832 đã làm lại (bản cũ ở `training/start_seed606_raw.png`). Dataset Kaggle `ai-live-infinitetalk-input` đã tạo 2026-11-18, ảnh này đang dùng cho bản thử InfiniteTalk (dòng ADR-060). TODO: kiểm lại giấy phép LoRA Lightning và bản GGUF trước khi khách trả tiền | Lần thử Ultralight |

## 3. Hiến pháp chờ sửa (`/sdd.constitution`)

Hiến pháp ở 1.2.0 (sửa 2026-11-01, [ADR-029](../docs/DECISIONS.md): Điều V, VI, VIII).

| Đề xuất | Nguồn |
|---------|-------|
| Điều I: "nhãn AI rõ ràng theo quy định nền tảng" (không chỉ chữ "AI"); Điều II: không dùng hình người dưới 18 tuổi, người nổi tiếng, logo hay ảnh của bên thứ ba khi chưa được phép. Người dùng gõ `/sdd.constitution` nếu đồng ý | [ADR-065](../docs/DECISIONS.md) mục 6 |

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
| [RISKS.md](../docs/RISKS.md) P11, [ADR-065](../docs/DECISIONS.md) | Quy định nội dung AI của Shopee (ảnh người dùng gửi 2026-11-19) coi "không tương tác với người xem" là chất lượng thấp, trong khi ADR-026 hoãn trả lời chat. Có đưa trả lời bình luận Shopee lên trước giai đoạn Shopee không (nối với thứ tự ưu tiên M2)? Ảnh quy định lấy từ trang nào (URL, bản nước nào)? |
| [RISKS.md](../docs/RISKS.md) P9, P10, P12–P15 | Shopee Việt Nam bắt khai báo nội dung AI trên Shopee Live bằng cách nào (nút khai báo, nhãn trên hình, bình luận ghim)? Khách hỏi Shopee lúc xin whitelist. Hợp đồng ghi ai chịu trách nhiệm về lời host AI nói? |
| [RISKS.md](../docs/RISKS.md) L2, L4, L11 | Trước M2 (thu tiền): Wav2Lip gốc ghi rõ cấm thương mại. Người dùng có muốn gửi thư hỏi Sync Labs (điều kiện thương mại) và tác giả LiveTalking (license checkpoint `wav2lip256`, logo trên YouTube/Shopee) không? Mình không tự gửi thư ra ngoài. Không xin được thì cần hướng khác (bản thương mại LiveTalking, model lip-sync có license rõ; ADR mới) |
| [RISKS](../docs/RISKS.md) Q22, 010 research R10, [R13](../specs/010-natural-mouth-shapes/research.md) | Người dùng chọn hướng 2 (Ultralight) ngày 2026-11-17, xem ADR-060 ở §2. Song song vẫn có thể quay clip nói mới (miễn phí). Nếu Ultralight trượt: hỏi giá bản thương mại LiveTalking hoặc thuê RunPod chạy MuseTalk (tốn tiền) |
| [ADR-051](../docs/DECISIONS.md), [ADR-052](../docs/DECISIONS.md) | Xác nhận hai ADR tự chốt cho 009 (Pillow + font máy; app vẽ cảnh, fork trộn trước watermark/nhãn, bộ cảnh ngoài git) |
| [009 quickstart](../specs/009-live-scene-layout/quickstart.md) §9, SC-007 | Ảnh thật của khách cho từng sản phẩm (bộ demo đang dùng ảnh "ẢNH MẪU"): mình cắt nền tay, ghi `provenance.json`, người dùng đặt ảnh gốc cạnh ảnh đã chỉnh để xác nhận |
| [009 spec](../specs/009-live-scene-layout/spec.md) SC-006 | 3 người xem so hai đoạn 1 phút có/không cảnh (gộp với 005 T068) |
| [011 tasks](../specs/011-ultralight-live-lipsync/tasks.md) T040 | Xem bằng mắt Ultralight `demo_host_02` trên `/host` vài phút: chỗ nối vòng khung có giật không (FR-005)? Số đo đã đạt (research R7) |
| [011 quickstart](../specs/011-ultralight-live-lipsync/quickstart.md) US2 bước 4 | Chấm gói xem mù `out/mouth/runs/011_t046_r1/ab/PHIEU.md` (4 cặp X/Y, không mở `ab_key.json` trước khi chấm) |
| [006 quickstart](../specs/006-obs-output/quickstart.md) §5 "Gói duyệt" | (T029 OBS portable xong 2026-11-19: bản ghi có tiếng + nhãn "AI"; đã sửa tiếng giật/tách tách, người dùng nghe lại đạt 2026-11-19) thêm nguồn `/obs` trong OBS thật theo RUNBOOK §8 và bấm giờ (SC-001; máy dev chưa cài OBS, đo khi cài OBS trên máy chạy live); khi tắt cảnh 009 nhãn "AI" nằm ở dải đen trên ảnh, có cần đưa vào trong ảnh? |
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

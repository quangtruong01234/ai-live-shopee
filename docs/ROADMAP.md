# Roadmap

> Mốc hiện tại: **M1: Demo** (M0 đã xong). Đánh dấu `[x]` chỉ khi đã kiểm chứng.
> Chưa có ngày đích cho từng mốc. TODO: ngày dự kiến demo với khách là khi nào?

## M0: Khung context ✅
- [x] `CLAUDE.md`, `docs/` (PRD, ARCHITECTURE, DECISIONS, ROADMAP, RISKS, RUNPOD)
- [x] `.env.example`, `.gitignore`, khung thư mục `src/`
- [x] Lệnh `/update-context`
- [x] Quy trình Spec-Driven: hiến pháp, template, lệnh `/sdd.*`, `docs/WORKFLOW.md` (ADR-013)
- [x] uv + Python 3.12 trên laptop dev (ADR-012, đổi từ 3.10 theo ADR-020)
- [x] `git init` và commit đầu tiên (198a6d4, branch `main`, ADR-027)
- [ ] Trả lời các câu hỏi mở ưu tiên cao (xem cuối CLAUDE.md và các `TODO:`)

## M1: Demo cho 1 khách (ngoài Shopee)

### M1a: Logic chạy local (laptop, `AVATAR_MODE=static`)
- [ ] `pyproject.toml`, lint/format, cấu hình test, cấu hình từ `.env`
- [ ] Mô hình dữ liệu `Comment`, `Product`; dữ liệu mẫu cho 1 sản phẩm chính và 2–3 sản phẩm phụ trong `data/products/`
- [ ] `MockSource` cùng trang điều khiển để gõ comment
- [ ] `CommentQueue` in-process gồm ưu tiên, chống trùng, lọc spam và bỏ comment quá cũ
- [ ] `ProductStore` (JSON)
- [x] `ReplyEngine` streaming theo câu với guardrail chỉ dùng dữ liệu sản phẩm: chuỗi model free ghim sẵn, tự chuyển khi lỗi (feature 008,
  ADR-035, ADR-037–040; Gemini xuống dự phòng, ADR-018). Kiểm ở quickstart 008 ngày 2026-11-05
- [x] Bộ 10 câu hỏi mẫu kèm đáp án kỳ vọng, chạy tự động, đạt ≥ 8/10 (`qa_eval run`: `sealion` 10/10, `qwen` 9/10, 2026-11-04)
- [x] `TTSEngine`: 1 nhà cung cấp chạy được, có thêm `FakeTTS` cho test (feature 003, ADR-024: VieNeu trên CPU mặc định, giọng
  `Thùy Dung` + đoạn mẫu; phiên 30 phút 60/60 lượt, p95 câu đầu → chunk đầu 0,484 s, 2026-11-09). Gemini TTS free (3 RPM / 10 RPD)
  chỉ để thử. Đo cùng lip-sync 005 (T050, 2026-11-12): p95 câu đầu → chunk đầu 0,921 s, đạt ≤ 1,0 s nhưng sát ngưỡng
- [ ] `StaticRenderer`: ảnh tĩnh + audio phát trên trình duyệt
- [ ] `ShowDirector`: kịch bản giới thiệu sản phẩm sinh realtime, là nội dung chính (feature 004, ADR-026)
- [ ] Log độ trễ từng khâu và trang/endpoint xem số liệu

### M1b: Lip-sync (tạm chạy trên GPU laptop, ADR-023; RunPod là dự phòng)
- [ ] Văn bản đồng ý của người mẫu (hình + giọng) đã ký và lưu ngoài git
- [x] Fork LiveTalking; chốt cách tích hợp (ADR-042, ADR-043: fork chạy process riêng ở `vendor/livetalking`, tiếng vào qua
  `/ailive/ws`, hình ra `/host` bằng WebRTC). Chạy được trên laptop, người dùng duyệt nhép miệng 2026-11-10/11 (005 T045, T046)
- [ ] Dựng RunPod theo `RUNPOD.md`; thời gian từ lúc bật pod đến lúc sẵn sàng < 15 phút (TODO: mục tiêu này có hợp lý không?)
- [ ] Kiểm tra WebRTC từ RunPod về Chrome laptop (rủi ro UDP)
- [ ] Benchmark Wav2Lip vs MuseTalk: độ trễ, chất lượng miệng, VRAM; ghi ADR chọn model. Một phần: ADR-041 chọn Wav2Lip cho laptop
  (MuseTalk không đủ 4 GB, chưa benchmark); số đo laptop 2026-11-11: `render_fps` 24,8–25,3, VRAM 2 656 MB; còn chạy 30 phút (SC-006 của 005)
- [x] Chuẩn bị dữ liệu avatar (video/ảnh nền) theo yêu cầu của model đã chọn: 4 clip Wan 2.2 (ADR-036), làm mượt bằng
  `scripts/avatar_clips/smooth_clips.py`, `prepare` cho Wav2Lip; người dùng duyệt hết rung 2026-11-10 (005 T044, T045)
- [x] Nhãn "AI" ghép vào frame (ADR-044): 12/12 ảnh chụp `/host` lúc chờ và lúc nói có nhãn trong khung hình, 2026-11-11 (005 T047, SC-002)
- [ ] Bố cục cảnh live quanh host (bàn, sản phẩm hai bên/phía sau, thẻ giá): đề xuất `009-live-scene-layout`, làm sau 003
- [ ] ~~Đo độ trễ end-to-end < 5 giây (p95) với comment mock~~ tạm hoãn (ADR-026); đo tốc độ nhân vật theo spec 005

### M1c: YouTube Unlisted (tùy chọn)
- [ ] (Tạm hoãn, ADR-026) `YouTubeChatSource` (Live Chat API) với xử lý `pollingIntervalMillis` và quota
- [ ] Output RTMP lên YouTube Unlisted
- [ ] (Tạm hoãn, ADR-026) Chạy thử comment thật từ YouTube

### M1d: Tổng duyệt và demo
- [ ] Phiên chạy liên tục 30 phút không lỗi (ghi lại log)
- [ ] Video dự phòng 2–3 phút đã quay và đã thử phát qua Meet
- [ ] Runbook buổi demo: checklist T-1 ngày và T-1 giờ, xử lý sự cố, ai làm gì
- [ ] Thử chia sẻ tab Chrome có âm thanh vào Google Meet từ máy khác
- [ ] **Demo với khách.** Ghi phản hồi vào ADR/ROADMAP

**Điều kiện qua M1:** đạt đủ 5 tiêu chí trong `PRD.md` §3 và khách đồng ý trả tiền.

## M2: Pilot 1 khách
- [ ] Hoàn tất kiểm tra license: LiveTalking (watermark), Wav2Lip, MuseTalk, S3FD, whisper, model TTS (xem `RISKS.md`)
- [ ] Hợp đồng dịch vụ có điều khoản dữ liệu, đồng ý về hình/giọng và trách nhiệm whitelist
- [ ] Khách xin được whitelist live AI với Shopee
- [ ] Output cho OBS: virtual cam và/hoặc RTMP + Stream Key
- [ ] (Tạm hoãn, ADR-026) Khảo sát cách đọc comment Shopee Live PC và làm prototype `ShopeeSource`
- [ ] Lưu phiên Shopee ở dạng mã hóa (ADR-010)
- [ ] Chạy ổn định 4 giờ, rồi 8 giờ, rồi 15 giờ (tự khởi động lại, watchdog, cảnh báo)
- [ ] Xoay vòng kịch bản để không lặp nội dung trong ngày
- [ ] Mô hình chi phí/giờ (GPU, LLM, TTS) và giá bán
- [ ] Chốt hạ tầng chạy 15 giờ/ngày (thuê dài hạn hay mua GPU?) và ghi ADR
- [ ] Feature đóng gói app desktop cài trên máy vận hành (ADR-021), làm sau khi khách duyệt demo

## M3: Chạy Shopee thật
- [ ] Phiên live đầu tiên trên Shopee có nhãn AI và người vận hành túc trực
- [ ] Nhật ký sự cố cùng quy trình xử lý (comment không vào, mất hình, mất tiếng, LLM lỗi)
- [ ] Theo dõi thay đổi giao diện Shopee làm hỏng `ShopeeSource`, có cảnh báo sớm
- [ ] Đối chiếu thống kê Shopee với phiên live để báo cáo cho khách
- [ ] Chạy 15 giờ/ngày liên tục 1 tuần

## M4: Nhiều khách
- [ ] Cấu hình theo khách (tenant): sản phẩm, avatar, giọng, kịch bản, lịch live
- [ ] Sổ đăng ký AI host để chặn dùng một host trên nhiều tài khoản
- [ ] Chuyển queue sang Redis; mỗi phiên live là một tiến trình riêng
- [ ] Lập lịch GPU cho nhiều phiên song song
- [ ] Dashboard vận hành cho nhiều phiên
- [ ] Quy trình onboarding khách mới (dữ liệu, đồng ý, whitelist)
- [ ] (Tùy chọn) App desktop cho khách tự cài: cập nhật, license, khóa avatar/giọng theo shop (ADR-021); sửa PRD trước

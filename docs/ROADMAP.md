# Roadmap

> Mốc hiện tại: **M1: Demo** (M0 đã xong). Đánh dấu `[x]` chỉ khi đã kiểm chứng.
> Chưa có ngày đích cho từng mốc. TODO: ngày dự kiến demo với khách là khi nào?

## M0: Khung context ✅
- [x] `CLAUDE.md`, `docs/` (PRD, ARCHITECTURE, DECISIONS, ROADMAP, RISKS, RUNPOD)
- [x] `.env.example`, `.gitignore`, khung thư mục `src/`
- [x] Lệnh `/update-context`
- [x] Quy trình Spec-Driven: hiến pháp, template, lệnh `/sdd.*`, `docs/WORKFLOW.md` (ADR-013)
- [x] uv + Python 3.10 trên laptop dev (ADR-012)
- [ ] `git init` và commit đầu tiên
- [ ] Trả lời các câu hỏi mở ưu tiên cao (xem cuối CLAUDE.md và các `TODO:`)

## M1: Demo cho 1 khách (ngoài Shopee)

### M1a: Logic chạy local (laptop, `AVATAR_MODE=static`)
- [ ] `pyproject.toml`, lint/format, cấu hình test, cấu hình từ `.env`
- [ ] Mô hình dữ liệu `Comment`, `Product`; dữ liệu mẫu cho 1 sản phẩm chính và 2–3 sản phẩm phụ trong `data/products/`
- [ ] `MockSource` cùng trang điều khiển để gõ comment
- [ ] `CommentQueue` in-process gồm ưu tiên, chống trùng, lọc spam và bỏ comment quá cũ
- [ ] `ProductStore` (JSON)
- [ ] `ReplyEngine` (Gemini streaming theo câu) với guardrail chỉ dùng dữ liệu sản phẩm
- [ ] Bộ 10 câu hỏi mẫu kèm đáp án kỳ vọng, chạy tự động, đạt ≥ 8/10
- [ ] `TTSEngine`: 1 nhà cung cấp chạy được, có thêm `FakeTTS` cho test
- [ ] `StaticRenderer`: ảnh tĩnh + audio phát trên trình duyệt
- [ ] `ShowDirector`: kịch bản giới thiệu sản phẩm sinh realtime, là nội dung chính (feature 004, ADR-026)
- [ ] Log độ trễ từng khâu và trang/endpoint xem số liệu

### M1b: Lip-sync (tạm chạy trên GPU laptop, ADR-023; RunPod là dự phòng)
- [ ] Văn bản đồng ý của người mẫu (hình + giọng) đã ký và lưu ngoài git
- [ ] Fork LiveTalking; chốt cách tích hợp (ADR-004 TODO)
- [ ] Dựng RunPod theo `RUNPOD.md`; thời gian từ lúc bật pod đến lúc sẵn sàng < 15 phút (TODO: mục tiêu này có hợp lý không?)
- [ ] Kiểm tra WebRTC từ RunPod về Chrome laptop (rủi ro UDP)
- [ ] Benchmark Wav2Lip vs MuseTalk: độ trễ, chất lượng miệng, VRAM; ghi ADR chọn model
- [ ] Chuẩn bị dữ liệu avatar (video/ảnh nền) theo yêu cầu của model đã chọn
- [ ] Nhãn "AI" ghép vào frame
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

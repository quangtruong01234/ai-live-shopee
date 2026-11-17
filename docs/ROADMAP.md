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
- [x] `pyproject.toml`, lint/format, cấu hình test, cấu hình từ `.env` (001, kiểm 2026-11-13: `uv run pytest` 1929 passed, ruff sạch)
- [x] Mô hình dữ liệu `Comment`, `Product`; dữ liệu mẫu cho 1 sản phẩm chính và 2–3 sản phẩm phụ trong `data/products/`
  (`demo.docx`, 3 sản phẩm; 001 T015, T016, T028, T029)
- [x] `MockSource` cùng trang điều khiển để gõ comment (001 T044, T068; dùng làm công cụ thử cho 003, 005)
- [x] `CommentQueue` in-process gồm ưu tiên, chống trùng, lọc spam và bỏ comment quá cũ (001, có test unit)
- [x] `ProductStore`: đổi từ JSON sang file Word theo mẫu (ADR-014), `DocxProductStore` + lệnh `validate` (001 T024–T026)
- [x] `ReplyEngine` streaming theo câu với guardrail chỉ dùng dữ liệu sản phẩm: chuỗi model free ghim sẵn, tự chuyển khi lỗi (feature 008,
  ADR-035, ADR-037–040; Gemini xuống dự phòng, ADR-018). Kiểm ở quickstart 008 ngày 2026-11-05
- [x] Bộ 10 câu hỏi mẫu kèm đáp án kỳ vọng, chạy tự động, đạt ≥ 8/10 (`qa_eval run`: `sealion` 10/10, `qwen` 9/10, 2026-11-04)
- [x] `TTSEngine`: 1 nhà cung cấp chạy được, có thêm `FakeTTS` cho test (feature 003, ADR-024: VieNeu trên CPU mặc định, giọng
  `Thùy Dung` + đoạn mẫu; phiên 30 phút 60/60 lượt, p95 câu đầu → chunk đầu 0,484 s, 2026-11-09). Gemini TTS free (3 RPM / 10 RPD)
  chỉ để thử. Đo cùng lip-sync 005 (T050, 2026-11-12): p95 câu đầu → chunk đầu 0,921 s, đạt ≤ 1,0 s nhưng sát ngưỡng
- [x] `StaticRenderer`: ảnh tĩnh + audio phát trên trình duyệt (001 T050, ADR-016)
- [ ] `ShowDirector`: kịch bản giới thiệu sản phẩm sinh realtime, là nội dung chính (feature 004, ADR-026). 80/81: còn T079
  (SC-009 người chấm, tổng duyệt lại ngày riêng khi cắm sạc)
- [x] Log độ trễ từng khâu và trang/endpoint xem số liệu (`/api/latency`, 001 T073, T078; thêm cột fps và clip ở 005 T083)

### M1b: Lip-sync (tạm chạy trên GPU laptop, ADR-023; RunPod là dự phòng)
- [ ] Văn bản đồng ý của người mẫu (hình + giọng) đã ký và lưu ngoài git
- [x] Fork LiveTalking; chốt cách tích hợp (ADR-042, ADR-043: fork chạy process riêng ở `vendor/livetalking`, tiếng vào qua
  `/ailive/ws`, hình ra `/host` bằng WebRTC). Chạy được trên laptop, người dùng duyệt nhép miệng 2026-11-10/11 (005 T045, T046)
- [ ] Dựng RunPod theo `RUNPOD.md`; thời gian từ lúc bật pod đến lúc sẵn sàng < 15 phút (TODO: mục tiêu này có hợp lý không?)
- [ ] Kiểm tra WebRTC từ RunPod về Chrome laptop (rủi ro UDP)
- [ ] Benchmark Wav2Lip vs MuseTalk: độ trễ, chất lượng miệng, VRAM; ghi ADR chọn model. Một phần: ADR-041 chọn Wav2Lip cho laptop
  (MuseTalk không đủ 4 GB, chưa benchmark); số đo laptop 2026-11-11: `render_fps` 24,8–25,3, VRAM 2 656 MB; chạy 30 phút 2026-11-12 (005 T073): 322 câu, 0 lỗi, `render_fps` p50 25,1, VRAM 2 656 MB không đổi; so sánh batch 16/8/4 và
  `LIP_EVERY_N` 2 (T075, ADR-041): giữ batch 16. Còn benchmark MuseTalk trên GPU lớn (RunPod, hỏi chi phí trước)
- [x] Chuẩn bị dữ liệu avatar (video/ảnh nền) theo yêu cầu của model đã chọn: 4 clip Wan 2.2 (ADR-036), làm mượt bằng
  `scripts/avatar_clips/smooth_clips.py`, `prepare` cho Wav2Lip; người dùng duyệt hết rung 2026-11-10 (005 T044, T045)
- [x] Nhãn "AI" ghép vào frame (ADR-044): 12/12 ảnh chụp `/host` lúc chờ và lúc nói có nhãn trong khung hình, 2026-11-11 (005 T047, SC-002)
- [x] Duyệt số đo 005 US4 (2026-11-16): `LIVETALKING_LEAD_S` mặc định 2,5, batch 16, chấp nhận ~18 khung/giây ở lượt bình luận,
  không làm bộ clip nhỏ hơn / RunPod
- [x] Bố cục cảnh live quanh host (khung dọc, bàn bày sản phẩm trước host, thẻ tên/giá): [spec `009-live-scene-layout`](../specs/009-live-scene-layout/spec.md) Done 2026-11-13 (38/38; còn ảnh thật của khách, SC-006, SC-007)
- [ ] Khẩu hình giống người: [spec `010-natural-mouth-shapes`](../specs/010-natural-mouth-shapes/spec.md) In progress 2026-11-13 (29/32):
  bộ đo khẩu hình, núm `LIVETALKING_MOUTH_METHOD` (mặc định `w2l`, ADR-055), loại đoạn clip nói đầu nghiêng (ADR-056). Còn chấm A/B
  `w2l` vs `shift=-1` (ngưỡng góc đầu giữ 35/20/30, 2026-11-16)
- [ ] ~~Đo độ trễ end-to-end < 5 giây (p95) với comment mock~~ tạm hoãn (ADR-026); đo tốc độ nhân vật theo spec 005

### ~~M1c: YouTube Unlisted (tùy chọn)~~ Bỏ (ADR-058)
- Người dùng không live trên YouTube (2026-11-13). Không làm `YouTubeChatSource`, không đẩy RTMP lên YouTube. Đầu ra cho giai đoạn
  Shopee chuyển sang 006 OBS (M2).

### M1d: Tổng duyệt và demo
- [ ] Phiên chạy liên tục 30 phút không lỗi (ghi lại log). Một phần: 004 G5 (2026-11-12, LLM thật + nhép miệng, có lỗi giả lập) chạy hết
  30 phút về `ended`; 005 T073 (`REPLY_ENGINE=fake`) 322 câu, 0 lỗi tts/render; 007 T054 (2026-11-13, fake, canh show bật) 327 câu,
  0 lỗi, lặng p95 3,0 s. Còn tổng duyệt lại ngày riêng với LLM thật, cắm sạc, theo `RUNBOOK.md` §7 (lệnh `report` chấm tiêu chí 3, 4)
- [ ] Video dự phòng 2–3 phút đã quay và đã thử phát qua Meet. Một phần: 007 T055 (2026-11-13) làm bằng lệnh `backup-video`
  (157 s, nhãn "AI" mọi khung, phiếu `Đạt`); còn người dùng xem lại và thử phát qua Meet (007 T058)
- [ ] Sẵn sàng demo: [spec `007-demo-readiness`](../specs/007-demo-readiness/spec.md) In progress 2026-11-13 (58/59): kiểm tra trước
  demo, canh show + banner, báo cáo tổng duyệt, video dự phòng `verbatim` (ADR-057 Đề xuất). Còn T058 (người dùng)
- [ ] Runbook buổi demo: checklist T-1 ngày và T-1 giờ, xử lý sự cố, ai làm gì. Bản nháp [`RUNBOOK.md`](RUNBOOK.md) 2026-11-13; còn
  `TODO:` ai làm gì, Meet chạy máy nào, ngưỡng chuyển sang video dự phòng. 007 thêm §2–§7 (lệnh kiểm, banner, làm video dự phòng, `report`)
- [ ] Thử chia sẻ tab Chrome có âm thanh vào Google Meet từ máy khác
- [ ] **Demo với khách.** Ghi phản hồi vào ADR/ROADMAP

**Điều kiện qua M1:** đạt đủ 5 tiêu chí trong `PRD.md` §3 và khách đồng ý trả tiền.

## M2: Pilot 1 khách

Thứ tự ưu tiên đề xuất sau demo (2026-11-17, chờ người dùng), theo so sánh với sản phẩm cùng loại ở [VENDORS.md](VENDORS.md) mục
"Sản phẩm cùng loại trên thị trường": (1) đường license cho nhép miệng, (2) trả lời bình luận Shopee, (3) chạy ổn 4 → 8 → 15 giờ
trên máy đích.

- [ ] Xác minh cách khai báo nội dung AI trên Shopee Live Việt Nam (RISKS P9): nhãn "AI" trong hình đã đủ chưa, có nút khai báo hay
  phải ghim bình luận (P8) không
- [ ] Hoàn tất kiểm tra license: LiveTalking (watermark), Wav2Lip, MuseTalk, S3FD, whisper, model TTS (xem `RISKS.md`). Đọc 2026-11-13:
  Wav2Lip gốc cấm thương mại (L2, phải hỏi Sync Labs), code S3FD BSD-3 nhưng weights chưa rõ (L4), whisper không nằm trên đường wav2lip (L5),
  VieNeu cho dùng thương mại tiếng tạo ra (L8). Còn L1 logo trên YouTube/Shopee, L2, L4 weights, L11 checkpoint `wav2lip256`
- [ ] Hợp đồng dịch vụ có điều khoản dữ liệu, đồng ý về hình/giọng và trách nhiệm whitelist
- [ ] Khách xin được whitelist live AI với Shopee
- [ ] Output cho OBS: [spec `006-obs-output`](../specs/006-obs-output/spec.md) In progress 2026-11-13 (30/35, phần không GPU xong; còn
  task `[GPU]` và gói duyệt): OBS Browser Source trang `/obs`
  có hình + tiếng không cần bấm, vai `obs` ưu tiên hơn trang `/host`, `OUTPUT_MODE=meet|obs` (ADR-058 Đề xuất). OBS tự đẩy RTMP + Stream
  Key lên Shopee; virtualcam/RTMP trực tiếp từ fork để sau
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

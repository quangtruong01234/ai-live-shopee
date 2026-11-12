# Sổ rủi ro

> Thang đo: Khả năng (Thấp / TB / Cao) × Tác động (Thấp / TB / Cao). Cập nhật khi có thông tin mới.
> Các nhận định về license và chính sách dưới đây **chưa được xác minh pháp lý**. Mọi dòng có `TODO:` phải kiểm tra lại từ nguồn gốc.

## 1. Chính sách Shopee

| ID | Rủi ro | Khả năng | Tác động | Giảm thiểu |
|----|--------|----------|----------|------------|
| P1 | Shopee coi nội dung là "video quay sẵn" (cấm, kể cả video AI) | TB | Cao | Mọi hình và tiếng được sinh realtime; không có đường phát file video tới Shopee; video dự phòng chỉ dùng cho demo |
| P2 | Lip-sync kiểu LiveTalking dùng **video nền lặp** (spec 005: bộ clip nền tạo từ gương mặt AI, ADR-036); có thể bị hiểu là nội dung quay sẵn. Hướng dẫn chính thức của Shopee (SG/PH/MY) cấm "pre-recorded or replay content, including AI-generated recordings"; một blog bên thứ ba nói nội dung lặp được phép, không phải nguồn chính thức | TB | Cao | Clip nền không có tiếng, miệng tạo realtime; nhiều clip chờ và clip nói xoay vòng, không chọn lại đúng clip vừa dùng (005 FR-013; clip cử chỉ để feature sau). TODO: khách hỏi Shopee lúc đăng ký live AI: video nền lặp có miệng sinh realtime có được tính là live không? Chỉ ảnh hưởng giai đoạn Shopee, không ảnh hưởng demo Meet/YouTube |
| P3 | Thiếu hoặc che nhãn "AI" | Thấp | Cao | Nhãn ghép vào frame trong pipeline; test tự động kiểm tra overlay luôn bật |
| P4 | Dùng cùng một AI host trên nhiều tài khoản | Thấp | Cao | Sổ đăng ký host ↔ tài khoản; app từ chối chạy nếu host đã gán cho tài khoản khác |
| P5 | Khách chưa có whitelist mà vẫn lên live AI | TB | Cao | Checklist trước phiên live đầu yêu cầu bằng chứng whitelist; ghi rõ trách nhiệm trong hợp đồng |
| P6 | Shopee đổi chính sách live AI | TB | Cao | Theo dõi định kỳ; kiến trúc cho phép chuyển nền tảng (YouTube, TikTok...). TODO: ai phụ trách theo dõi? |
| P7 | Host chỉ nói kịch bản, không tương tác với người xem: nội dung lặp có thể bị coi giống video quay sẵn, hoặc người xem rời phiên | TB | TB | Kịch bản sinh realtime, không lặp nguyên văn (spec 004 SC-005: chống trùng theo `word_form`, research R11); xoay vòng sản phẩm × chủ đề (004 R5), lịch cả ngày ở M2. TODO: Shopee có yêu cầu host AI phải tương tác với người xem không? (ADR-026) |
| P8 | Shopee yêu cầu ngoài nhãn "AI-generated" trên hình còn phải **ghim một bình luận báo là AI**, và nhân vật không được trông như người dưới 18 tuổi hay giống người nổi tiếng; thiếu thì phiên live có thể bị dừng | TB | Cao | Nhãn trong frame (005 FR-010); gương mặt trông là người trưởng thành, ghi trong hồ sơ nguồn gốc (005 FR-005). TODO: thêm bước ghim bình luận báo AI vào runbook vận hành (feature 007) |

## 2. Đọc comment Shopee

| ID | Rủi ro | Khả năng | Tác động | Giảm thiểu |
|----|--------|----------|----------|------------|
| C1 | Đọc comment từ Shopee Live PC hỏng khi Shopee đổi giao diện | Cao | Cao | Cô lập trong `ShopeeSource`; selector để trong config; có health check "không có comment mới quá N phút" và cảnh báo; người vận hành nhập tay qua `MockSource` khi hỏng |
| C2 | Tự động hóa trình duyệt bị coi là bot, dẫn đến khóa hoặc hạn chế tài khoản khách | TB | Cao | Chỉ đọc, không thao tác; tần suất thấp. TODO: điều khoản Shopee có cho phép đọc comment kiểu này không? Có API chính thức cho đối tác không? |
| C3 | Độ trễ đọc comment Shopee cộng thêm vào ngân sách 5 giây | TB | TB | Đo riêng; tối ưu sau khi có prototype |

## 3. License model và phần mềm

| ID | Thành phần | Rủi ro | Hành động |
|----|-----------|--------|-----------|
| L1 | LiveTalking | Apache-2.0 (LICENSE). README ghi: video làm từ dự án này đăng trên Bilibili, WeChat Channels, Douyin phải có watermark và logo LiveTalking. Code tự vẽ chữ "LiveTalking" lên mọi khung (plan 005, research R5) | Giữ nguyên watermark trong code (ADR-044), không xóa, không che. TODO: YouTube và Shopee có phải hiện thêm logo không? Hỏi tác giả hoặc đọc điều khoản bản thương mại trước khi thu tiền khách |
| L2 | Wav2Lip | Theo hiểu biết hiện tại, bản gốc chỉ cho phép nghiên cứu/phi thương mại; bản thương mại do đơn vị khác cung cấp | TODO: xác minh license checkpoint và điều kiện thương mại trước M2 |
| L3 | MuseTalk | Code và các model phụ thuộc (VAE, whisper, face parsing, pose...) có thể mang license khác nhau | TODO: liệt kê từng checkpoint và license tương ứng |
| L4 | S3FD (phát hiện khuôn mặt) | License của code/weights chưa rõ | TODO: xác minh |
| L5 | whisper | TODO: xác minh license code và weights của bản đang dùng | TODO |
| L6 | Model TTS mã nguồn mở tiếng Việt | Nhiều model TTS có license phi thương mại | TODO: kiểm tra trước khi chọn làm mặc định |
| L7 | ElevenLabs | Điều khoản về clone giọng và dùng thương mại theo gói | TODO: xác minh gói nào cho dùng thương mại và có giới hạn giờ |
| L8 | VieNeu-TTS (spec 003, ADR-024) | Code và model Apache-2.0; trang model ghi giọng có sẵn được dùng thương mại. Chưa đọc kỹ điều khoản từng giọng và dữ liệu huấn luyện | TODO: đọc LICENSE và model card trước khi thu tiền khách; ghi tên giọng đã dùng |
| L9 | Gemini TTS (spec 003, ADR-024) | Điều khoản dùng tiếng tạo ra cho mục đích thương mại, nhất là ở free tier, chưa xác minh | TODO: đọc Gemini API Additional Terms trước khi thu tiền khách |
| L10 | Model tạo ảnh và tạo video cho clip nền nhân vật (ADR-036): SDXL base 1.0, FLUX.1-schnell, Wan 2.2 | SDXL: CreativeML Open RAIL++-M; FLUX.1-schnell và Wan 2.2: Apache-2.0; FLUX.1-dev phi thương mại nên không dùng. VAE, text encoder đi kèm có thể mang license khác | TODO: đọc model card và license của đúng checkpoint đã dùng, ghi vào hồ sơ nguồn gốc trước khi thu tiền khách |
| L11 | Checkpoint `wav2lip256.pth` (plan 005, ADR-041) | Do tác giả LiveTalking huấn luyện lại ở 256 px, phát qua Google Drive / Quark; chưa thấy license riêng hay dữ liệu huấn luyện. Wav2Lip gốc chỉ cho nghiên cứu (L2) | TODO: hỏi tác giả LiveTalking về license và nguồn dữ liệu của checkpoint; ghi sha256 file đã tải vào ADR-048; chưa xác minh thì không thu tiền khách |

**Quy tắc:** không thu tiền thương mại (M2) khi L1–L7 và L11 chưa được xác minh. Kết quả ghi vào `DECISIONS.md`.

## 4. GPU và hạ tầng

| ID | Rủi ro | Khả năng | Tác động | Giảm thiểu |
|----|--------|----------|----------|------------|
| G1 | RunPod hết RTX 3090/4090 đúng lúc demo | TB | Cao | Bật pod và kiểm tra trước T-2 giờ; có danh sách GPU thay thế (TODO: GPU nào tương đương?); có video dự phòng |
| G2 | WebRTC từ RunPod không chạy do không có cổng UDP | Cao | Cao | Kiểm tra ngay ở M1b; dự phòng TURN qua TCP/TLS hoặc RTMP → trình phát độ trễ thấp |
| G3 | Dựng môi trường lâu (tải model, cài CUDA) | TB | TB | Network volume giữ model và venv; script dựng tự động |
| G4 | Chi phí GPU cho 15 giờ/ngày cao hơn doanh thu | TB | Cao | Lập mô hình chi phí ở M2; so sánh thuê dài hạn và mua máy |
| G5 | Laptop dev 4GB VRAM chạy lip-sync chậm (FPS thấp, độ trễ cao), có thể nóng máy | Cao | TB | Người dùng chấp nhận chậm (ADR-023); giảm FPS/độ phân giải, vẫn sinh realtime; benchmark trước; RunPod làm dự phòng (báo chi phí trước) |
| G6 | Độ trễ mạng từ region RunPod về Việt Nam | TB | TB | TODO: chọn region gần nhất có GPU; đo RTT |
| G7 | VieNeu chạy CPU tranh CPU với app và lip-sync trên laptop (spec 003): tiếng chậm, đứt hoặc lượt bị quá `TTS_TIMEOUT_S` (từ ADR-049 tính mỗi lần chờ chunk, nên câu dài không còn bị cắt) | TB | TB | Giới hạn luồng bằng `VIENEU_CPU_THREADS`; nạp model trước phiên; đo khi chạy cùng 005 (SC-006); tăng `TTS_TIMEOUT_S` hoặc dùng Gemini nếu cần |
| G8 | GPU cloud miễn phí để tạo clip nền (ADR-036): Colab bản miễn phí cấm giao diện web và có thể ngắt phiên, không công bố hạn mức; T4 không có bf16 nên model chạy chậm hoặc lỗi bộ nhớ; điều khoản Colab chưa nói rõ dùng thương mại, Kaggle chỉ cho dùng phi thương mại | TB | TB | Chạy ComfyUI không giao diện trong notebook; lưu kết quả ra ngoài sau mỗi clip. Người dùng chấp nhận dùng Kaggle cho giai đoạn demo (2026-11-03, ADR-036). Đo 2026-11-06 trên Kaggle T4: Wan 2.2 TI2V-5B fp16 chạy được, không lỗi bộ nhớ, khoảng 9,5 phút một clip 5 s ở 480×832 (ADR-036). TODO: trước khi khách trả tiền, đọc lại điều khoản Kaggle và Colab; không cho phép thì tạo lại bộ clip trên RunPod (báo chi phí trước) |
| G9 | Bánh xe torch 2.9.1 cu128 không chạy trên driver 565.90 của laptop (driver báo hỗ trợ tới CUDA 12.7), hoặc thiếu kernel sm_75 (plan 005, research R11) | TB | TB | Kiểm bằng một lệnh Python ngay sau khi cài (quickstart bước 1); không được thì dùng bản cu126; vẫn không được thì hỏi người dùng trước khi cập nhật driver _Đã kiểm 2026-11-07 (T008): `torch 2.9.1+cu128` chạy trên driver 565.90, có `sm_75`; không cần cu126 (ADR-048)._ |
| G10 | GTX 1650 Ti tạo hình dưới 25 khung/giây: độ trễ khung đầu (≥ 0,84 s + suy luận ở `batch_size` 16) và khoảng lặng giữa câu tăng, có thể vượt Điều VI (plan 005, R6, R8, R15) | Cao | TB | Người dùng chấp nhận chậm (ADR-023); giảm `LIVETALKING_BATCH_SIZE`, bật `LIVETALKING_LIP_EVERY_N=2`, `LIVETALKING_LEAD_S`; đo ở quickstart bước 9; vẫn không đạt thì báo người dùng và hỏi chi phí trước khi tính RunPod _Đo 2026-11-12 (T073, T075, quickstart 005 bước 9): batch 16 cho `infer_fps` p50 ~24–25, show 30 phút `render_fps` p50 25,1; lượt bình luận `render_fps` ~18 vì tiếng VieNeu tới chậm, không phải do suy luận. Lặng giữa câu p95 2,98 s với `LIVETALKING_LEAD_S` 0, còn 0,76–1,00 s với 2,5 (chờ người dùng duyệt đổi mặc định). So sánh batch 8 / 4 và `LIP_EVERY_N` 2: ADR-041._ |
| G11 | RAM laptop không đủ nạp mọi clip của nhân vật (mỗi clip 121 khung 480×832 ≈ 145 MB chưa nén; 4–6 clip ≈ 0,6–0,9 GB) cùng fork, app và VieNeu (plan 005, R7) | TB | TB | Đo RAM ở quickstart bước 4–5; nếu thiếu thì giảm số clip hoặc độ phân giải lúc chuẩn bị. ~~TODO: số đo thật~~ _Đo 2026-11-12 lúc chạy show (4 clip 480×832): fork ~2,0 GB RAM, app kèm VieNeu ~1,4 GB, laptop 23,8 GB còn trống ~10 GB; bước `prepare` đỉnh 1,3 GB (T044). Không thiếu RAM với 4 clip._ |
| G12 | LiveTalking không chạy trên Windows native (tác giả chỉ thử Ubuntu 24.04), hoặc `aiortc` / `av` thiếu bánh xe Windows cho Python 3.12 (plan 005, R11) | TB | Cao | Kiểm ngay ở quickstart bước 1 trước mọi việc khác; phương án dự phòng là WSL2 Ubuntu (cần ADR mới); không được nữa thì hỏi người dùng về RunPod _Đã kiểm 2026-11-07 (T008–T009): LiveTalking chạy trên Windows 11 native với Python 3.12, `aiortc` / `av` có bánh xe; không cần WSL2. Chạy 30 phút liền không lỗi (T073)._ |
| G13 | Mốc `avatar_first_frame` lấy từ ack `playback_started` lúc fork gửi khung, sớm hơn lúc Chrome vẽ (jitter buffer WebRTC), nên số đo đẹp hơn thực tế (plan 005, R6, ADR-047) | Cao | Thấp | Đo lệch một lần, ≥ 10 câu (quickstart bước 9); ghi lệch vào ADR-047 và cộng khi báo cáo. _Đã đo 2026-11-12 (T074, đầu đo WebAudio trong Chrome): trung vị +0,28 s, p95 +0,64 s, chung cho tiếng và hình (research 005 R6)_ |
| G14 | Gánh bảo trì fork LiveTalking: rebase khi upstream đổi, sửa trong file gốc bị xung đột, requirements kéo theo gói không dùng (edge_tts, flask, dashscope, openai...) (plan 005, R2, ADR-042) | TB | TB | Ghim SHA upstream; phần của mình nằm trong `ailive_ext/`, chỉ sửa nhỏ vào file gốc; test fork không GPU; không rebase trước buổi demo. TODO: nơi giữ fork (repo riêng hay chỉ trên máy) |
| G15 | `VIENEU_REF_AUDIO` dựa vào hàm nội bộ `engine._encode_ref_wav` của `vieneu` (ADR-024, research R1 của spec 003): nâng phiên bản `vieneu` có thể làm hàm đổi hoặc biến mất | TB | Thấp | Adapter báo `config_error` rõ ràng lúc warm-up, không đổi sang giọng khác; bỏ trống biến để quay về giọng có sẵn; nghe lại giọng sau mỗi lần nâng `vieneu` |

## 5. Bảo mật tài khoản khách

| ID | Rủi ro | Khả năng | Tác động | Giảm thiểu |
|----|--------|----------|----------|------------|
| S1 | Lộ cookie/phiên Shopee của khách | Thấp | Cao | Mã hóa khi lưu, chỉ trên máy chạy; khóa tách khỏi dữ liệu; không log cookie; không đưa lên RunPod hay volume dùng chung |
| S2 | Lộ API key hoặc stream key | TB | TB | `.env` bị gitignore; dùng secret của RunPod thay vì file trên volume; xoay key khi nghi ngờ |
| S3 | Người vận hành có quyền quá rộng trên tài khoản khách | TB | Cao | Chỉ dùng quyền tối thiểu; nhật ký truy cập. TODO: Shopee có tài khoản phụ hoặc phân quyền cho live không? |
| S4 | Lộ dữ liệu sản phẩm chưa công bố, hay ảnh/giọng người mẫu | Thấp | TB | Dữ liệu khách và media không vào git; xóa sau khi kết thúc hợp đồng |
| S5 | Khách hoặc người mẫu rút lại đồng ý | Thấp | Cao | Hợp đồng ghi quy trình rút đồng ý; có thể xóa avatar/giọng nhanh |
| S6 | Trang điều khiển (spec 001) không có đăng nhập; nếu bind ra ngoài localhost (ví dụ RunPod ở 005) thì người lạ điều khiển phiên và thay nội dung được | Thấp | Cao | Mặc định `APP_HOST=127.0.0.1`; truy cập RunPod qua SSH tunnel. TODO: feature 005 có cần đăng nhập hoặc token cho trang điều khiển không? |
| S7 | Free tier Gemini (ADR-018): Google dùng dữ liệu gửi lên để cải thiện sản phẩm và có thể có người duyệt đọc. Gửi comment thật của người xem (tên, nội dung) hoặc tài liệu mật của khách lên đó là lộ dữ liệu | TB | Cao | Ở 001 chỉ gửi nội dung sản phẩm công khai và comment tự gõ. TODO: trước feature 006, chọn gói trả phí hay chấp nhận rủi ro (hỏi người dùng theo ADR-019); có cần báo khách không? |
| S8 | Body lỗi của nhà cung cấp LLM (Groq, freellmapi, OpenAI-compatible) có thể chứa lại key; lọt vào log, `errors.jsonl`, trang điều khiển hoặc thông báo lỗi lúc khởi động (spec 008) | Thấp | Cao | Mẫu che `gsk_…`, `freellmapi-…`, `sk-…` và che theo giá trị key trong `security/redact.py` (ADR-039); không log header `Authorization` hay body request; kiểm SC-008 bằng tìm chuỗi key trong log |
| S9 | Fork LiveTalking (plan 005) không có xác thực: ai gọi được `/offer` hay `/ailive/ws` thì xem được luồng hoặc đẩy tiếng tùy ý vào nhân vật (nói thay host). Nếu bind ra ngoài localhost (ví dụ RunPod) thì người lạ làm được | Thấp | Cao | `run.ps1` luôn bind `127.0.0.1`; `LIVETALKING_URL` chỉ nhận `127.0.0.1` / `localhost` (data-model §1); `max_session` 1; RunPod truy cập qua SSH tunnel như S6 |

## 6. Chất lượng sản phẩm và buổi demo

| ID | Rủi ro | Khả năng | Tác động | Giảm thiểu |
|----|--------|----------|----------|------------|
| Q1 | LLM bịa giá, khuyến mãi hoặc công dụng | TB | Cao | Guardrail chỉ dùng dữ liệu; `forbidden_claims`; regression test bộ 10 câu |
| Q2 | Giọng Việt không tự nhiên, đọc sai số, giá hoặc đơn vị | Cao | TB | Chuẩn hóa văn bản trước TTS (số, tiền, viết tắt); thử nhiều nhà cung cấp qua adapter |
| Q3 | Độ trễ vượt 5 giây | TB | TB | Streaming theo câu, câu đệm, chọn model LLM nhanh, đo từng khâu |
| Q4 | Sự cố trong buổi demo (mạng, API, GPU) | TB | Cao | Tổng duyệt 30 phút; video dự phòng 2–3 phút; runbook xử lý sự cố |
| Q5 | Comment phản cảm hoặc khiêu khích bị AI đọc to lên | TB | TB | Lọc từ khóa trước queue; LLM được dặn bỏ qua; không đọc nguyên văn tên hoặc comment xấu |
| Q6 | Nội dung không qua khách duyệt; mình soạn sai thì host nói sai như sự thật | TB | Cao | Chỉ chép thông tin từ tài liệu khách gửi; lưu bản gốc khách gửi (ngoài git) để đối chiếu; bộ câu hỏi mẫu kiểm các số liệu chính |
| Q7 | File Word không đúng style mẫu (heading tự gõ in đậm, file từ Google Docs/WPS) nên không nạp được | TB | Thấp | Sinh `template.docx` có sẵn style; lệnh `validate` báo rõ mục nào sai. TODO: thử file lưu từ Word tiếng Việt, Google Docs, WPS (spec 001, research R1) |
| Q8 | Guard đầu ra chặn nhầm câu đúng, hoặc bỏ sót số tiền viết bằng chữ / khẳng định bị cấm nói bằng chữ khác | TB | TB | Tập số hợp lệ lấy rộng từ cả file; log `guard_blocked` để rà; prompt dặn ghi giá bằng số. TODO: có cần thêm cách nói tương đương cho khẳng định bị cấm không? |
| Q9 | Tự chấm bộ câu hỏi bằng khớp cụm từ lệch với chấm tay | TB | TB | Mỗi ý có nhiều cách nói tương đương; báo cáo có cột "Chấm tay" để đối chiếu (SC-009) |
| Q10 | Chrome chặn tự phát âm thanh trên trang host, demo bị câm | Cao | TB | Nút "Bắt đầu" mở khóa audio; chưa nhận `ready` thì trang điều khiển báo "chưa mở màn hình host" |
| Q11 | Free tier Gemini không cam kết dịch vụ: vượt giới hạn tần suất (HTTP 429) hoặc API chậm đúng lúc demo; model bị đổi tên hay ngừng | TB | Cao | Tải demo nhỏ (khoảng 90 request / 30 phút); 429 tính là lỗi bước `llm`, host chuyển comment sau; không chạy benchmark ngay trước demo; model đặt bằng `LLM_MODEL`. TODO: xem giới hạn thật trong AI Studio; có cần key dự phòng hoặc bật trả phí riêng ngày demo không (hỏi người dùng theo ADR-019)? |
| Q12 | Giới hạn free tier của Gemini TTS (RPM/RPD) thấp hơn số câu của phiên 30 phút (mỗi câu một request; host nói liên tục theo ADR-026 nên có thể vài trăm request) | TB | TB | Lớp bọc nghỉ `TTS_QUOTA_COOLDOWN_S` sau 429, báo "hết hạn mức giọng nói"; VieNeu làm nguồn chạy không giới hạn. Plan 004 R14 ước tính khoảng 250–450 câu TTS mỗi 30 phút show. Giới hạn thật (AI Studio 2026-11-10, T048): 3 RPM, 10 RPD, tức là chỉ vài phút phát; đã xảy ra nên VieNeu là nguồn mặc định, Gemini chỉ thử và cầm cự vài câu (spec 003 research R2, ADR-024) |
| Q13 | Giọng có sẵn không ra giọng miền Nam (Gemini) hoặc giọng VieNeu không đạt SC-002 (≥ 8/10) | TB | TB | Nghe thử cả hai nguồn ở SC-006 trước khi chốt; đổi giọng bằng cấu hình. Nếu cả hai không đạt thì báo người dùng trước khi xét gói trả phí (ADR-019) |
| Q14 | Hạn mức free tier Gemini (RPD) không đủ cho show liên tục, tổng duyệt và bộ tự kiểm tra kịch bản trong cùng một ngày (plan 004 R14: khoảng 60–120 request LLM / 30 phút show, khoảng 30 / lần kiểm tra, khoảng 250–350 / ngày) | TB | Cao | Phân đoạn 3–6 câu một request; tầng chữ chỉ đi trước một phân đoạn; 429 → bỏ phân đoạn, 3 lần liền → chế độ dự phòng đọc nguyên văn; không chạy bộ tự kiểm tra cùng ngày tổng duyệt; ADR-035: chuỗi nhiều nhà cung cấp free qua freellmapi, tự chuyển khi 429. Số đo 2026-11-12 (T080, research R14): show 30 phút thật tốn 57 request; dồn G1–G5 trong một ngày thì SEA-LION bị `rate_limited` sau khoảng 194 request, chuỗi tự chuyển sang Qwen và show không mất lượt nào. TODO: giới hạn SEA-LION reset lúc nào (theo ngày hay cửa sổ ngắn)? Ngày demo không chạy gì khác ngoài phiên demo |
| Q15 | Guard chặn nhiều câu kịch bản làm phân đoạn bị cụt, mất mạch, nghe lủng củng (spec 004 SC-009) | TB | TB | Prompt nhắc rõ quy tắc số liệu, link và cơ chế nền tảng (004 R4); bộ tự kiểm tra chấm trên chữ thô để bắt prompt kém; `ShowSummary` đếm câu `blocked`; phân đoạn bị chặn hết thì sang phân đoạn kế |
| Q16 | freellmapi gom nhóm theo tên model hoặc tự chuyển nội bộ, cho lượt tới nền tảng chưa benchmark (ví dụ `gpt-oss-120b` qua Cloudflare thay vì Groq), chất lượng khác số đã chấm (spec 008) | TB | TB | Kiểm nền tảng chặt theo `X-Routed-Via` trước chữ đầu, sai thì từ chối và chuyển mục (FR-024, ADR-038); gửi `X-FreeLLM-Cache: off`; log nền tảng thật mỗi lượt và trong báo cáo bộ kiểm; tắt nền tảng chưa benchmark trên dashboard freellmapi |
| Q17 | ~~429 hết hạn mức ngày có `Retry-After` hàng giờ làm mục 1 nghỉ tới hết show~~ **Không còn áp dụng** (làm rõ sau plan 008, 2026-11-03): chuỗi chỉ dùng một ngày demo, không đọc `Retry-After`; mục hết hạn mức chỉ nghỉ 60 s rồi thử lại | — | — | Trang điều khiển hiện model đang nói và lý do chuyển (FR-017) |
| Q18 | Mục 1 (SEA-LION) hết giờ chờ ngay câu chào mở màn thì câu đầu ≈ 5–6 s, vượt 5 s của Điều VI (plan 008) | TB | TB | Đo ở quickstart 008 và G5 của 004; nếu > 1/10 lần thì hỏi người dùng có hạ giới hạn chờ của mục 1 không (research R4 của 008). T055: 1/5 lần 7,08 s; ADR-040 hạ xuống 2,5 s, bỏ gpt-oss-120b |
| Q19 | Giọng văn đổi giữa hai phân đoạn khi chuỗi chuyển model (đã chấp nhận ở làm rõ 008) | TB | Thấp | Cùng prompt và luật xưng hô cho mọi model; bản tổng hợp đếm số lần chuyển mỗi show |

# Sổ rủi ro

> Thang đo: Khả năng (Thấp / TB / Cao) × Tác động (Thấp / TB / Cao). Cập nhật khi có thông tin mới.
> Các nhận định về license và chính sách dưới đây **chưa được xác minh pháp lý**. Mọi dòng có `TODO:` phải kiểm tra lại từ nguồn gốc.

## 1. Chính sách Shopee

| ID | Rủi ro | Khả năng | Tác động | Giảm thiểu |
|----|--------|----------|----------|------------|
| P1 | Shopee coi nội dung là "video quay sẵn" (cấm, kể cả video AI) | TB | Cao | Mọi hình và tiếng được sinh realtime; không có đường phát file video tới Shopee; video dự phòng chỉ dùng cho demo |
| P2 | Lip-sync kiểu LiveTalking dùng **video nền lặp** của người mẫu; có thể bị hiểu là nội dung quay sẵn | TB | Cao | TODO: hỏi khách/Shopee về cách hiểu quy định với video nền lặp có miệng sinh realtime. Cân nhắc biến thể nền (nhiều đoạn, cử động ngẫu nhiên) |
| P3 | Thiếu hoặc che nhãn "AI" | Thấp | Cao | Nhãn ghép vào frame trong pipeline; test tự động kiểm tra overlay luôn bật |
| P4 | Dùng cùng một AI host trên nhiều tài khoản | Thấp | Cao | Sổ đăng ký host ↔ tài khoản; app từ chối chạy nếu host đã gán cho tài khoản khác |
| P5 | Khách chưa có whitelist mà vẫn lên live AI | TB | Cao | Checklist trước phiên live đầu yêu cầu bằng chứng whitelist; ghi rõ trách nhiệm trong hợp đồng |
| P6 | Shopee đổi chính sách live AI | TB | Cao | Theo dõi định kỳ; kiến trúc cho phép chuyển nền tảng (YouTube, TikTok...). TODO: ai phụ trách theo dõi? |
| P7 | Host chỉ nói kịch bản, không tương tác với người xem: nội dung lặp có thể bị coi giống video quay sẵn, hoặc người xem rời phiên | TB | TB | Kịch bản sinh realtime, không lặp nguyên văn; xoay vòng nội dung (M2). TODO: Shopee có yêu cầu host AI phải tương tác với người xem không? (ADR-026) |

## 2. Đọc comment Shopee

| ID | Rủi ro | Khả năng | Tác động | Giảm thiểu |
|----|--------|----------|----------|------------|
| C1 | Đọc comment từ Shopee Live PC hỏng khi Shopee đổi giao diện | Cao | Cao | Cô lập trong `ShopeeSource`; selector để trong config; có health check "không có comment mới quá N phút" và cảnh báo; người vận hành nhập tay qua `MockSource` khi hỏng |
| C2 | Tự động hóa trình duyệt bị coi là bot, dẫn đến khóa hoặc hạn chế tài khoản khách | TB | Cao | Chỉ đọc, không thao tác; tần suất thấp. TODO: điều khoản Shopee có cho phép đọc comment kiểu này không? Có API chính thức cho đối tác không? |
| C3 | Độ trễ đọc comment Shopee cộng thêm vào ngân sách 5 giây | TB | TB | Đo riêng; tối ưu sau khi có prototype |

## 3. License model và phần mềm

| ID | Thành phần | Rủi ro | Hành động |
|----|-----------|--------|-----------|
| L1 | LiveTalking | Có yêu cầu watermark/ghi nguồn khi dùng | TODO: đọc LICENSE và README của repo, ghi điều kiện chính xác; nếu phải hiển thị watermark thì đưa vào overlay |
| L2 | Wav2Lip | Theo hiểu biết hiện tại, bản gốc chỉ cho phép nghiên cứu/phi thương mại; bản thương mại do đơn vị khác cung cấp | TODO: xác minh license checkpoint và điều kiện thương mại trước M2 |
| L3 | MuseTalk | Code và các model phụ thuộc (VAE, whisper, face parsing, pose...) có thể mang license khác nhau | TODO: liệt kê từng checkpoint và license tương ứng |
| L4 | S3FD (phát hiện khuôn mặt) | License của code/weights chưa rõ | TODO: xác minh |
| L5 | whisper | TODO: xác minh license code và weights của bản đang dùng | TODO |
| L6 | Model TTS mã nguồn mở tiếng Việt | Nhiều model TTS có license phi thương mại | TODO: kiểm tra trước khi chọn làm mặc định |
| L7 | ElevenLabs | Điều khoản về clone giọng và dùng thương mại theo gói | TODO: xác minh gói nào cho dùng thương mại và có giới hạn giờ |
| L8 | VieNeu-TTS (spec 003, ADR-024) | Code và model Apache-2.0; trang model ghi giọng có sẵn được dùng thương mại. Chưa đọc kỹ điều khoản từng giọng và dữ liệu huấn luyện | TODO: đọc LICENSE và model card trước khi thu tiền khách; ghi tên giọng đã dùng |
| L9 | Gemini TTS (spec 003, ADR-024) | Điều khoản dùng tiếng tạo ra cho mục đích thương mại, nhất là ở free tier, chưa xác minh | TODO: đọc Gemini API Additional Terms trước khi thu tiền khách |

**Quy tắc:** không thu tiền thương mại (M2) khi L1–L7 chưa được xác minh. Kết quả ghi vào `DECISIONS.md`.

## 4. GPU và hạ tầng

| ID | Rủi ro | Khả năng | Tác động | Giảm thiểu |
|----|--------|----------|----------|------------|
| G1 | RunPod hết RTX 3090/4090 đúng lúc demo | TB | Cao | Bật pod và kiểm tra trước T-2 giờ; có danh sách GPU thay thế (TODO: GPU nào tương đương?); có video dự phòng |
| G2 | WebRTC từ RunPod không chạy do không có cổng UDP | Cao | Cao | Kiểm tra ngay ở M1b; dự phòng TURN qua TCP/TLS hoặc RTMP → trình phát độ trễ thấp |
| G3 | Dựng môi trường lâu (tải model, cài CUDA) | TB | TB | Network volume giữ model và venv; script dựng tự động |
| G4 | Chi phí GPU cho 15 giờ/ngày cao hơn doanh thu | TB | Cao | Lập mô hình chi phí ở M2; so sánh thuê dài hạn và mua máy |
| G5 | Laptop dev 4GB VRAM chạy lip-sync chậm (FPS thấp, độ trễ cao), có thể nóng máy | Cao | TB | Người dùng chấp nhận chậm (ADR-023); giảm FPS/độ phân giải, vẫn sinh realtime; benchmark trước; RunPod làm dự phòng (báo chi phí trước) |
| G6 | Độ trễ mạng từ region RunPod về Việt Nam | TB | TB | TODO: chọn region gần nhất có GPU; đo RTT |
| G7 | VieNeu chạy CPU tranh CPU với app và lip-sync trên laptop (spec 003): tiếng chậm, đứt hoặc lượt bị quá `TTS_TIMEOUT_S` | TB | TB | Giới hạn luồng bằng `VIENEU_CPU_THREADS`; nạp model trước phiên; đo khi chạy cùng 005 (SC-006); tăng `TTS_TIMEOUT_S` hoặc dùng Gemini nếu cần |

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
| Q12 | Giới hạn free tier của Gemini TTS (RPM/RPD) thấp hơn số câu của phiên 30 phút (mỗi câu một request; host nói liên tục theo ADR-026 nên có thể vài trăm request) | TB | TB | Lớp bọc nghỉ `TTS_QUOTA_COOLDOWN_S` sau 429, báo "hết hạn mức giọng nói"; VieNeu làm nguồn chạy không giới hạn. TODO: xem giới hạn thật trong AI Studio (spec 003, research R2) |
| Q13 | Giọng có sẵn không ra giọng miền Nam (Gemini) hoặc giọng VieNeu không đạt SC-002 (≥ 8/10) | TB | TB | Nghe thử cả hai nguồn ở SC-006 trước khi chốt; đổi giọng bằng cấu hình. Nếu cả hai không đạt thì báo người dùng trước khi xét gói trả phí (ADR-019) |

# PRD: AI Live Shopee

> Cập nhật lần cuối: 2026-10-30. Trạng thái: bản nháp cho giai đoạn Demo.

## 1. Vấn đề và mục tiêu

Shop trên Shopee muốn live nhiều giờ mỗi ngày nhưng thuê host người tốn chi phí và khó duy trì 15 giờ/ngày.
Dự án cung cấp **dịch vụ làm hộ**: một AI host (avatar nhép miệng, giọng tiếng Việt) giới thiệu sản phẩm theo kịch bản sinh realtime. Trả lời comment tạm hoãn (ADR-026).

- **Khách hàng:** chủ shop hoặc brand bán trên Shopee. Khách chỉ cung cấp dữ liệu sản phẩm.
- **Mình (nhà cung cấp dịch vụ):** dựng avatar và giọng, viết kịch bản, vận hành phiên live, xử lý sự cố.
- **Người xem:** người mua trên Shopee Live. Ở giai đoạn demo là khách hàng xem qua Google Meet hoặc YouTube.

Ngoài trách nhiệm của mình: xin whitelist live AI với Shopee (việc của khách); báo cáo doanh số (dùng thống kê có sẵn của Shopee).

## 2. Phạm vi Giai đoạn 1: DEMO (hiện tại)

**Bối cảnh:** 1 khách, 1 sản phẩm chính, 2–3 sản phẩm phụ. Chạy ngoài Shopee. Khách xem demo ổn mới trả tiền.

Trong phạm vi:
- [ ] Nhập dữ liệu sản phẩm từ file Word theo mẫu, gồm tên, giá (hoặc phân loại kèm giá), mô tả, thông số, FAQ, khuyến mãi,
      khẳng định bị cấm, bài giới thiệu và link. Định dạng lưu bên trong do plan quyết định.
- [ ] Một avatar đã có văn bản đồng ý của người mẫu, và một giọng tiếng Việt đã có văn bản đồng ý.
- ~~Nguồn comment mock rồi YouTube Live Chat API; hàng đợi comment có ưu tiên; trả lời comment.~~ **Tạm hoãn (ADR-026).**
  Code mock, hàng đợi và trả lời của 001 vẫn giữ, chỉ dùng làm công cụ thử.
- [ ] TTS tiếng Việt qua adapter (ít nhất 1 nhà cung cấp chạy được).
- [ ] Lip-sync realtime trên GPU thuê (RunPod) bằng fork LiveTalking.
- [ ] **Kịch bản giới thiệu sản phẩm** sinh realtime bằng Gemini API (free tier), chỉ dựa trên dữ liệu sản phẩm, streaming theo câu.
      Đây là nội dung chính của phiên live (ADR-026).
- [ ] Nhãn "AI" hiển thị trên hình.
- [ ] Đầu ra WebRTC xem trên Chrome, chia sẻ tab có âm thanh vào Google Meet.
- [ ] (Tùy chọn) Đẩy RTMP lên YouTube Live chế độ Unlisted.
- [ ] Trang điều khiển tối thiểu cho người vận hành: bắt đầu, tạm dừng hoặc bỏ qua câu đang nói.
- [ ] Log độ trễ từng khâu.
- [ ] Video dự phòng 2–3 phút để dùng nếu hệ thống lỗi trong buổi demo (chỉ cho demo, không bao giờ dùng trên Shopee).

## 3. Tiêu chí demo thành công

| # | Tiêu chí | Cách đo |
|---|----------|---------|
| 1 | Avatar nhép miệng khớp lời | Người vận hành và khách quan sát bằng mắt. TODO: có cần chấm theo thang 1–5 không? |
| 2 | Kịch bản host nói **tự nhiên và không bịa**: ≥ 8/10 phân đoạn chọn ngẫu nhiên được chấm "tự nhiên, đúng xưng hô"; 0 câu bịa giá, khẳng định cấm hay đọc link (thay bộ 10 câu hỏi mẫu, ADR-026; chốt 2026-11-01, spec 004 SC-009, SC-003) | Người vận hành nghe 10 phân đoạn ngẫu nhiên từ phiên 30 phút; bộ chặn kiểm toàn bộ lịch sử phụ đề. Bộ 10 câu hỏi của 001 giữ làm regression cho đường trả lời comment. |
| 3 | **Khoảng lặng** giữa hai câu liên tiếp p95 ≤ 1,5 giây, không lần nào quá 5 giây (thay độ trễ comment → avatar, ADR-026; chốt 2026-11-01, spec 004 SC-002) | Log mốc thời gian từng câu của phiên 30 phút, không tính lúc tạm dừng và lúc giả lập lỗi. Comment mock chen vào (004 US6) vẫn đo `comment_received` → `avatar_first_frame` (SC-011). |
| 4 | Chạy liên tục **30 phút** không lỗi | Phiên tổng duyệt 30 phút, không crash, không đứng hình, không mất tiếng. |
| 5 | Có **video dự phòng 2–3 phút** | File có sẵn trên máy demo, đã thử phát qua Meet. |

## 4. Phạm vi Giai đoạn 2: Pilot và Shopee thật

- [ ] Chạy Shopee Live qua OBS (virtual cam hoặc RTMP + Stream Key do khách cấp), khoảng 15 giờ/ngày.
- [ ] (Tạm hoãn, ADR-026) Nguồn comment Shopee: đọc từ Shopee Live PC. TODO: cách đọc cụ thể (DOM qua trình duyệt tự động hóa, hay cách khác?) cần khảo sát.
- [ ] Lưu phiên đăng nhập Shopee của khách ở dạng mã hóa, chỉ trên máy chạy.
- [ ] Ổn định nhiều giờ: tự khởi động lại, watchdog, cảnh báo cho người vận hành.
- [ ] Xoay vòng kịch bản để tránh lặp nội dung trong 15 giờ.
- [ ] Hoàn tất kiểm tra license trước khi thu tiền thương mại.
- [ ] Mô hình chi phí theo giờ live (GPU, LLM, TTS).
- [ ] Sau đó: nhiều khách, mỗi khách một AI host riêng (xem `ROADMAP.md`).

## 5. Ngoài phạm vi (cả hai giai đoạn, trừ khi có ADR mới)

- Phát video quay sẵn làm nội dung live trên Shopee.
- Tự đặt đơn, chốt đơn, nhắn tin riêng hay thao tác giỏ hàng trên tài khoản khách.
- Dashboard báo cáo doanh số riêng (dùng thống kê Shopee).
- Xin whitelist với Shopee thay khách.
- Vector DB / RAG phức tạp (chưa cần khi ít sản phẩm).
- Avatar toàn thân có cử chỉ phức tạp, hay nhiều host cùng lúc trong một phiên live.
- Ứng dụng tự phục vụ (self-service) cho khách.

## 6. Giả định và câu hỏi mở

- TODO: Avatar là người thật (người mẫu ký đồng ý) hay nhân vật tạo bằng AI? Nếu là người thật thì ai làm mẫu?
- TODO: Giọng clone từ người mẫu hay dùng giọng có sẵn của nhà cung cấp TTS?
- Dữ liệu sản phẩm (chốt 2026-10-30, xem `specs/001-local-reply-pipeline/spec.md` mục Làm rõ): khách gửi tài liệu, thường là file Word.
  Mình soạn lại thành file nội dung theo mẫu, gồm cả bài giới thiệu thu hút (dịch vụ hỗ trợ), hoặc khách tự soạn theo mẫu.
  Đổi nội dung thì tạo file mới và nạp lại vào app. Khách không cần duyệt; mình chịu trách nhiệm chỉ dùng thông tin khách gửi.
- TODO: Có giới hạn ngân sách cho mỗi buổi demo (GPU, API) không?
- Xưng hô (chốt 2026-10-30, spec 001): host xưng "em", gọi "bạn {tên}" khi trả lời một người, "anh chị" khi nói chung; từ ngữ miền Nam.

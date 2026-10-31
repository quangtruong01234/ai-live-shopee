# Ứng viên SDK / API theo từng khâu

> Danh sách **ứng viên**, chưa cài, chưa ký hợp đồng. Khi cần dùng một mục: viết adapter theo interface của khâu đó, ghi ADR vào
> `docs/DECISIONS.md` (bắt buộc theo CLAUDE.md), và báo chi phí trước khi khách đồng ý trả tiền (ADR-019).
> Số liệu free tier và giá lấy từ kết quả tìm kiếm ngày 2026-10-30, **chưa kiểm tra trên trang giá chính thức**.

## Avatar nhép miệng realtime (`AvatarRenderer`)

| Ứng viên | Kiểu | Chi phí | Ghi chú |
|----------|------|---------|---------|
| Simli | API audio → video nhép miệng realtime (WebRTC) | Trả phí theo phút. TODO: gói thử bao nhiêu phút? | Khớp nhất với luồng "TTS → audio → avatar" hiện tại |
| HeyGen LiveAvatar | API/SDK avatar realtime (WebRTC, có tích hợp LiveKit) | Trả phí. TODO: giá theo phút? | Thay cho Interactive Avatar API (ngừng 2026-03-31) |
| Tavus (CVI, Phoenix-4) | API hội thoại avatar realtime | Trả phí. TODO | Quảng cáo phản hồi < 600 ms |
| D-ID | API avatar realtime | Trả phí. TODO | |
| Anam, bitHuman, Beyond Presence | API avatar realtime | TODO | Có plugin sẵn trong LiveKit Agents |
| LiveTalking (Wav2Lip / MuseTalk), tự host | Mã nguồn mở, chạy trên GPU thuê (`docs/RUNPOD.md`) | Tiền thuê GPU theo giờ | Phương án hiện tại của feature 005; license yêu cầu watermark (`docs/RISKS.md`) |

Cần so sánh trước khi chọn: độ tự nhiên, độ trễ, **chi phí mỗi giờ live** (mục tiêu ~15 giờ/ngày), có cho dùng ảnh/giọng người mẫu riêng
không, và điều khoản xử lý dữ liệu người mẫu (phải nằm trong phạm vi văn bản đồng ý).

## Khung ráp pipeline

| Ứng viên | Kiểu | Chi phí | Ghi chú |
|----------|------|---------|---------|
| LiveKit Agents | Framework mã nguồn mở, có plugin cho 16 nhà cung cấp avatar, LLM, TTS | Tự host miễn phí; LiveKit Cloud trả phí | Chỉ cân nhắc nếu dùng avatar API bên ngoài. TODO: có đáng thay `ShowDirector` hiện tại không? |

## TTS tiếng Việt (`TTSEngine`)

| Ứng viên | Free tier (theo tìm kiếm) | Ghi chú |
|----------|---------------------------|---------|
| FPT.AI | 100.000 ký tự/tháng, hơn 20 giọng | Gói trả phí từ 500.000đ. TODO: có trả audio streaming theo chunk không? |
| Zalo AI | Có gói miễn phí | Độ trễ khoảng 100–150 ms. TODO: hạn mức và streaming? |
| Viettel AI | 50.000 ký tự trong tháng đầu | TODO: streaming? |
| ElevenLabs | TODO | Đã có trong ADR-006; trả phí, server ở nước ngoài |
| Model TTS mã nguồn mở | Miễn phí, cần máy chạy | ADR-006. TODO: chọn model cụ thể |

## LLM (`ReplyEngine`)

- Gemini API, free tier (ADR-018). Đang dùng.

## Nguồn comment (`CommentSource`)

- YouTube Live Chat API: miễn phí trong hạn mức quota. Dùng cho demo YouTube Unlisted.
- Shopee: chưa có API công khai cho comment live. TODO: cách đọc comment đã thỏa thuận với khách (không thao tác gì khác trên tài khoản).

## Nguồn

- https://www.veed.io/learn/best-live-avatar-api
- https://www.d-id.com/blog/best-tavus-alternatives-real-time-ai-avatars/
- https://docs.heygen.com/docs/streaming-api
- https://docs.heygen.com/docs/streaming-api-integration-with-livekit-v2
- https://docs.fpt.ai/docs/vi/speech/documentation/tts-pricing/
- https://viettelai.vn/en/tin-tuc/top-5-phan-mem-doc-van-ban-thanh-giong-noi-mien-phi
- https://alohub.vn/text-to-speech-api-tieng-viet-huong-dan/

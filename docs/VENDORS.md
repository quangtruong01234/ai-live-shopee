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
| LiveTalking + Wav2Lip (`wav2lip256`), tự host | Mã nguồn mở. **Đang dùng** (feature 005): fork chạy process riêng ngoài git trên laptop GTX 1650 Ti (ADR-023, ADR-042); RunPod chỉ là dự phòng (`docs/RUNPOD.md`) | Miễn phí trên laptop; tiền thuê GPU theo giờ nếu phải dùng RunPod | Đã cài theo ADR-048, chọn Wav2Lip thay MuseTalk vì VRAM 4 GB (ADR-041). Đo 2026-11-12: `render_fps` p50 ~24–25, VRAM 2,6 GB (quickstart 005 bước 9). License yêu cầu giữ watermark "LiveTalking" (ADR-044); license checkpoint `wav2lip256.pth` chưa rõ (`docs/RISKS.md`) |

Cần so sánh trước khi chọn: độ tự nhiên, độ trễ, **chi phí mỗi giờ live** (mục tiêu ~15 giờ/ngày), có cho dùng ảnh/giọng người mẫu riêng
không, và điều khoản xử lý dữ liệu người mẫu (phải nằm trong phạm vi văn bản đồng ý).

## Tạo nhân vật và clip nền offline (spec 005, ADR-036)

Chỉ dùng một lần cho mỗi nhân vật, không nằm trong pipeline live. Miệng vẫn sinh realtime bằng LiveTalking.

| Ứng viên | Kiểu | Chi phí | Ghi chú |
|----------|------|---------|---------|
| ComfyUI | Công cụ chạy workflow ảnh/video (GPL-3.0) | Miễn phí | Chạy không giao diện trong notebook Kaggle hoặc Colab (Colab free cấm web UI) |
| SDXL base 1.0 / FLUX.1-schnell | Model tạo ảnh gương mặt | Miễn phí | CreativeML Open RAIL++-M / Apache-2.0. Không dùng FLUX.1-dev (phi thương mại) |
| Wan 2.2 TI2V-5B (dự phòng: Wan 2.2 I2V A14B GGUF) | Model ảnh → video | Miễn phí | Apache-2.0. TODO: tốc độ thật trên T4 (không có bf16)? |
| Google Colab free (T4) | GPU cloud | Miễn phí | TODO: điều khoản có cho tạo tài sản dùng thương mại không? (RISKS G8) |
| Kaggle Notebooks | GPU cloud (T4/P100, ~30 giờ/tuần) | Miễn phí | Nơi chạy đầu tiên cho giai đoạn demo (ADR-036). Điều khoản phi thương mại: đọc lại trước khi khách trả tiền (RISKS G8) |
| RunPod | GPU thuê | Trả phí theo giờ | Dự phòng; báo chi phí cho người dùng trước khi bật pod |

## Khung ráp pipeline

| Ứng viên | Kiểu | Chi phí | Ghi chú |
|----------|------|---------|---------|
| LiveKit Agents | Framework mã nguồn mở, có plugin cho 16 nhà cung cấp avatar, LLM, TTS | Tự host miễn phí; LiveKit Cloud trả phí | Chỉ cân nhắc nếu dùng avatar API bên ngoài. TODO: có đáng thay `ShowDirector` hiện tại không? |

## TTS tiếng Việt (`TTSEngine`)

Đang dùng (ADR-024, spec 003): **VieNeu-TTS** chạy CPU trên máy (`TTS_PROVIDER=vieneu`, nguồn mặc định khi chạy phiên) và
**Gemini TTS** gói miễn phí (`TTS_PROVIDER=gemini`, 3 RPM / 10 RPD nên chỉ để thử và cầm cự vài câu). Các dòng dưới là ứng viên,
chưa có adapter.

| Ứng viên | Free tier (theo tìm kiếm) | Ghi chú |
|----------|---------------------------|---------|
| FPT.AI | 100.000 ký tự/tháng, hơn 20 giọng | Gói trả phí từ 500.000đ. TODO: có trả audio streaming theo chunk không? |
| Zalo AI | Có gói miễn phí | Độ trễ khoảng 100–150 ms. TODO: hạn mức và streaming? |
| Viettel AI | 50.000 ký tự trong tháng đầu | TODO: streaming? |
| ElevenLabs | TODO | Đã có trong ADR-006; trả phí, server ở nước ngoài. ADR-024 bỏ khỏi cấu hình, giữ làm ứng viên |
| Model TTS mã nguồn mở | Miễn phí, cần máy chạy | ADR-006; ADR-024 đã chọn VieNeu-TTS |

## LLM (`ReplyEngine`)

- Gemini API, free tier (ADR-018). Đang dùng trong code; theo ADR-035 xuống cuối chuỗi.
- freellmapi (ADR-034) làm cổng OpenAI-compatible cho các nhà cung cấp free. Chuỗi đã chốt ở ADR-035: SEA-LION v4 27B (Cloudflare
  Workers AI) → gpt-oss-120b (Groq) → Qwen3.8 27B (Groq hoặc IteraCompute) → Gemini. Đã loại: OpenRouter free, Llama 3.3 70B fp8-fast.
  ADR-040 bỏ gpt-oss-120b khỏi chuỗi mặc định (không đạt SC-001 ở T055 của 008): còn SEA-LION → Qwen3.8.

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

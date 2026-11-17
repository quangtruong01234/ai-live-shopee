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
| Ultralight-Digital-Human (anliyuan), tự host trong fork LiveTalking | Mã nguồn mở (README ghi Apache-2.0 nhưng repo không có file LICENSE). UNet nhẹ huấn luyện riêng cho từng nhân vật từ 3–5 phút video có tiếng; fork đã có `--model ultralight` | Miễn phí | **Chấp nhận để thử** (ADR-060): mã ở `vendor/ultralight/`, HuBERT ở `vendor/livetalking/models/` (ngoài git, 2026-11-17) |
| InfiniteTalk (MeiGen-AI) trên Kaggle | Mở nguồn Apache-2.0, dựa trên Wan2.1; tạo video nói dài từ ảnh hoặc video + tiếng. Chỉ dùng offline để tạo video huấn luyện Ultralight, không phát live | Miễn phí (GPU Kaggle) | **Chấp nhận** (ADR-060, 2026-11-17): notebook `scripts/avatar_clips/make_infinitetalk_video.ipynb`; chưa chạy |
| HeyGen Avatar IV | SaaS, phổ biến nhất ở VN cho video người AI nói tiếng Việt | Free: 720p, watermark, chỉ dùng phi thương mại; trả phí ~24 USD/tháng | Đã xét, không chọn (ADR-060) |

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

## Sản phẩm cùng loại trên thị trường (tra 2026-11-17)

Tra bằng tìm kiếm web ngày 2026-11-17 để biết một dịch vụ host AI bán được cần có gì. Thông tin lấy từ trang của chính nhà cung cấp
và từ báo chí, **chưa dùng thử sản phẩm nào**. Đây không phải danh sách ứng viên để cài.

| Sản phẩm | Thị trường | Điểm chính theo nguồn |
|----------|-----------|------------------------|
| AnyLive (AnyMind) | Đông Nam Á, Nhật | Live AI chi phí thấp, không giới hạn giờ; thống kê theo tài khoản, brand và từng phiên cho cả host người lẫn host AI. Một case study của chính nhà cung cấp nói host AI đã chạy hơn 300 giờ trên Shopee Live (chưa kiểm) |
| BytePlus Live SaaS (digital human) | Quốc tế | Điều khiển host bằng kịch bản (nội dung, nhịp, luồng); có tài liệu đẩy phiên live lên Shopee bằng RTMP |
| Tencent Cloud (digital human) | Trung Quốc, quốc tế | Bài giới thiệu người số live 24/7 |
| Ecomobi | Việt Nam | Tự lấy thông tin sản phẩm từ link Shopee, Lazada, TikTok Shop; theo dõi kịch bản theo quy định của TikTok |
| AiClip, Aeyes Global | Việt Nam | Báo chí nhắc là bên cung cấp host AI cho livestream bán hàng (Aeyes Global tại ngày hội mua sắm trực tuyến TP.HCM 2023) |

Báo chí Việt Nam và nước ngoài đều nêu **tương tác với người xem là điểm yếu chung** của host AI.

TODO: giá dịch vụ host AI ở Việt Nam là bao nhiêu? Không tìm thấy bảng giá công khai; hỏi báo giá trực tiếp khi làm mô hình giá bán
(ROADMAP M2).

So với dự án (2026-11-17):

| Tính năng các bên có | Dự án | Việc tiếp |
|----------------------|-------|-----------|
| Kịch bản điều khiển nội dung và nhịp show | Có (004 `ShowDirector`) | — |
| Nhân vật nhép miệng realtime | Có (005), miệng chưa tự nhiên (RISKS Q22) | 010, ADR-060 |
| Bày sản phẩm, thẻ tên và giá trong khung | Có (009) | Ảnh thật của khách |
| Đẩy lên Shopee bằng RTMP | Có qua OBS (006), chưa thử trong OBS thật | Gói duyệt 006 |
| Trả lời bình luận người xem | Tạm hoãn (ADR-026). Đo 2026-11-17 trên đường thử: bình luận thứ hai chờ 17 s vì các câu trả lời chạy nối tiếp | M2, sửa spec trước |
| Chạy 24/7 | Mới đo 30 phút; mục tiêu 15 giờ/ngày chưa thử | M2 "Chạy ổn định 4 giờ, rồi 8 giờ, rồi 15 giờ" |
| Lấy dữ liệu sản phẩm tự động từ link sàn | Không, dùng file Word (ADR-014); hợp với mô hình làm hộ | Chưa cần |
| Thống kê phiên live | Dùng thống kê của Shopee (PRD §1) | Chưa cần |
| License thương mại rõ ràng | Chưa: Wav2Lip gốc cấm thương mại (RISKS L2, L4, L11) | Trước M2 |

Điểm khác biệt có sẵn của dự án: bộ chặn đầu ra chỉ cho host nói theo dữ liệu sản phẩm (ràng buộc 7), hợp với xu hướng quy trách
nhiệm lời host AI cho người bán (RISKS P10).

## Nguồn

Sản phẩm cùng loại và quy định (tra 2026-11-17):

- https://docs.byteplus.com/en/docs/byteplus-livesaas/digital-human-overview
- https://docs.byteplus.com/docs/byteplus-livesaas/going-live-on-shopee-via-rtmp
- https://anymindgroup.com/jp/anylive/
- https://www.netinfluencer.com/anymind-group-updates-ai-live-commerce-platform-with-more-lifelike-avatars-deeper-analytics/
- https://www.tencentcloud.com/techpedia/143803
- https://ecomobi.com/vi/?p=35596
- https://znews.vn/nguoi-ao-livestream-ban-hang-o-viet-nam-post1451576.html
- https://plo.vn/su-dung-nguoi-ao-livestream-ban-hang-247-post776899.html
- https://help.shopee.sg/portal/4/article/185261 (Shopee AI Terms of Service, bản Singapore)
- https://help.shopee.sg/portal/10/article/201777 (Shopee Video AI-Generated Content Guidelines, bản Singapore)
- https://www2.yicaiglobal.com/news/china-steps-up-regulation-of-livestream-e-commerce-includes-ai-hosts-for-first-time

Ứng viên SDK / API (tra 2026-10-30):

- https://www.veed.io/learn/best-live-avatar-api
- https://www.d-id.com/blog/best-tavus-alternatives-real-time-ai-avatars/
- https://docs.heygen.com/docs/streaming-api
- https://docs.heygen.com/docs/streaming-api-integration-with-livekit-v2
- https://docs.fpt.ai/docs/vi/speech/documentation/tts-pricing/
- https://viettelai.vn/en/tin-tuc/top-5-phan-mem-doc-van-ban-thanh-giong-noi-mien-phi
- https://alohub.vn/text-to-speech-api-tieng-viet-huong-dan/

# Dựng môi trường GPU trên RunPod (cho test và demo)

> Mục tiêu: từ lúc bật pod đến lúc avatar nói được **dưới 15 phút**, và **tắt pod ngay khi xong**.
> Tài liệu này chưa được chạy thử. Các bước có `TODO:` cần xác minh trong lần dựng đầu tiên, rồi cập nhật lại tài liệu.
> Script tự động hóa sẽ nằm ở `scripts/runpod/` (chưa viết).

## 0. Chuẩn bị một lần

- [ ] Tài khoản RunPod và credit. TODO: ngân sách tối đa mỗi tháng cho giai đoạn demo?
- [ ] Thêm SSH public key vào RunPod (Settings → SSH Keys).
- [ ] Tạo các secret trên RunPod (thay vì để `.env` trên volume): `GEMINI_API_KEY` (LLM và Gemini TTS) và key cần thiết khác.
- [ ] Repo fork LiveTalking của mình (ADR-004). TODO: public hay private? Nếu private thì cần deploy key hoặc token.
- [ ] Bộ dữ liệu avatar đã có văn bản đồng ý, được chuẩn bị theo yêu cầu model, và lưu ở chỗ riêng (không trong git).

## 1. Network Volume (giữ model và môi trường giữa các lần bật)

- Tạo **Network Volume** ở region có RTX 3090/4090. TODO: chọn region nào (đo RTT về Việt Nam)? Dung lượng bao nhiêu GB?
- Volume mount vào `/workspace`. Bố cục đề xuất:

```
/workspace/
├── livetalking/        # fork LiveTalking (git clone)
├── ai-live/            # repo này (git clone)
├── venv/               # môi trường Python dùng lại giữa các lần bật
├── models/             # checkpoint Wav2Lip / MuseTalk / whisper / S3FD ...
└── avatars/            # dữ liệu avatar đã xử lý sẵn (của 1 khách)
```

- Lưu ý: volume **vẫn tính phí khi pod tắt**. Pod và volume phải cùng region.

## 2. Tạo pod

- GPU: **RTX 4090** (ưu tiên) hoặc **RTX 3090**, cả hai đều 24GB VRAM.
- Template: RunPod PyTorch có CUDA. TODO: phiên bản Python/PyTorch/CUDA nào khớp với yêu cầu của LiveTalking? Đọc README của fork.
- Gắn Network Volume ở trên.
- Mở cổng (Expose ports):
  - HTTP `8010`: web/WebRTC của LiveTalking. TODO: xác nhận cổng mặc định của fork.
  - HTTP `8000`: app FastAPI của mình (trang điều khiển, API).
  - TCP `22`: SSH.
- ⚠️ **WebRTC:** RunPod có thể không mở được cổng UDP cho WebRTC. TODO: thử ngay lần đầu. Nếu không được, các phương án là:
  (a) dựng TURN server (coturn) chạy TCP/TLS; (b) LiveTalking đẩy RTMP sang media server rồi phát WebRTC/HLS từ nơi khác;
  (c) chọn nhà cung cấp GPU có IP public và cổng UDP. Ghi kết quả vào `DECISIONS.md`.

## 3. Cài đặt lần đầu (chỉ làm một lần, lưu trên volume)

```bash
# TODO: kiểm chứng toàn bộ khối lệnh này rồi chuyển thành scripts/runpod/setup_once.sh
cd /workspace
git clone <URL_FORK_LIVETALKING> livetalking        # TODO: URL fork
git clone <URL_REPO_NAY> ai-live                    # TODO: URL repo
python -m venv /workspace/venv && source /workspace/venv/bin/activate
pip install -r livetalking/requirements.txt         # TODO: có cần cài thêm gói hệ thống như ffmpeg không?
# Tải model vào /workspace/models theo hướng dẫn của fork
# TODO: liệt kê chính xác checkpoint + nguồn tải + license (xem RISKS.md L1–L5)
# Chép dữ liệu avatar đã chuẩn bị vào /workspace/avatars
```

## 4. Mỗi lần test hoặc demo

```bash
# TODO: chuyển thành scripts/runpod/start_demo.sh
source /workspace/venv/bin/activate
cd /workspace/livetalking && <lệnh khởi động LiveTalking với model + avatar>   # TODO
cd /workspace/ai-live && AVATAR_MODE=livetalking uvicorn ai_live.app.main:app --host 0.0.0.0 --port 8000  # TODO
```

1. Bật pod (với volume đã có sẵn model) và chờ trạng thái Running.
2. Chạy script khởi động, rồi kiểm tra `/health` của app và trang của LiveTalking.
3. **Làm nóng:** gửi 2–3 comment mock để load model vào VRAM; lượt đầu thường chậm.
4. Trên laptop: mở trang xem avatar trong Chrome và kiểm tra hình, tiếng, nhãn "AI".
5. Google Meet: **Present → A tab → chọn tab avatar → bật "Share tab audio"**.
6. (Tùy chọn) YouTube: bật RTMP output tới YouTube Unlisted và cấu hình `YouTubeChatSource`.
7. Theo dõi log độ trễ trong suốt buổi.

### Chạy fork LiveTalking của feature 005 trên RunPod (thêm 2026-11-12, T077)

Trên laptop, fork được dựng và chạy bằng `scripts/livetalking/` (quickstart 005 bước 1, 3, 5):
- `setup.ps1` clone upstream vào `vendor/livetalking/` (ngoài git), ghim commit, tạo nhánh `ailive` và venv riêng Python 3.12;
  không tải model.
- `run.ps1` đọc `.env.example` rồi `.env` và truyền `LIVETALKING_BATCH_SIZE`, `LIVETALKING_LIP_EVERY_N`, nhãn AI… cho fork.
  App nói chuyện với fork chỉ qua `LIVETALKING_URL` (`/ailive/health`, `/ailive/ws`), không import code fork (ADR-042, ADR-043).

Khi phải dùng RunPod, làm cùng các bước đó trên pod: cài fork, tải model theo ADR-048, chép bộ clip đã `prepare` của đúng một khách,
rồi trỏ `LIVETALKING_URL` của app tới cổng fork trên pod.
- TODO: hai script là PowerShell cho Windows. Trên pod Linux, dùng `pwsh` hay viết bản bash (`scripts/runpod/`)?
- TODO: nhánh `ailive` của fork chỉ nằm trên laptop (chưa đẩy lên đâu). Đưa lên pod bằng cách nào: repo riêng private hay chép thư mục?
- TODO: bộ clip `prepare` gắn với commit fork (`avatar_prepared_with_other_fork`). Chép bộ đã chuẩn bị, hay chạy lại `prepare` trên pod?

## 5. Tắt máy (bắt buộc)

- [ ] **Stop pod** ngay khi xong. Nếu không cần nữa thì **Terminate**, vì volume vẫn giữ dữ liệu.
- [ ] Không để `.env` hay cookie trên volume. Xóa log có thể chứa dữ liệu khách nếu không cần.
- [ ] Ghi lại số giờ dùng GPU để tính chi phí.

## 6. Checklist trước buổi demo

**T-1 ngày**
- [ ] Bật pod, chạy tổng duyệt 30 phút, xem log độ trễ (< 5 giây) và kiểm tra bộ 10 câu hỏi
- [ ] Thử share tab qua Meet với một máy khác để kiểm tra âm thanh
- [ ] Video dự phòng 2–3 phút đã có trên laptop và đã thử phát qua Meet
- [ ] Kiểm tra credit RunPod, giới hạn tần suất Gemini API và Gemini TTS (AI Studio)

**T-2 giờ**
- [ ] Bật pod (nếu không có GPU thì chuyển region hoặc loại GPU dự phòng, hoặc dùng video dự phòng)
- [ ] Làm nóng model, kiểm tra hình, tiếng và nhãn AI
- [ ] Đóng các tab và ứng dụng không cần thiết trên laptop; cắm sạc; dùng mạng có dây nếu có

## 7. Xử lý sự cố nhanh

| Triệu chứng | Kiểm tra |
|-------------|----------|
| Trang avatar đen, WebRTC không kết nối | Cổng UDP / TURN (mục 2); thử mạng khác |
| Miệng lệch tiếng | Sample rate giữa TTS và lip-sync (ARCHITECTURE §3); tải GPU |
| Trả lời chậm > 5 giây | Log từng khâu: LLM, TTS hay lip-sync chậm? |
| Out of memory trên GPU | Độ phân giải avatar, batch size, có tiến trình khác chiếm VRAM không |
| Mọi thứ hỏng trong lúc demo | Chuyển sang video dự phòng và giải thích ngắn gọn với khách |

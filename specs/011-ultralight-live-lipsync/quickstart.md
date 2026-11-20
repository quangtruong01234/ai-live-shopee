# Quickstart: 011-ultralight-live-lipsync

- **Ngày:** 2026-11-19 · **Plan:** [plan.md](./plan.md)
- Ký hiệu: **[không GPU]** chạy trên máy nào cũng được · **[GPU laptop]** GTX 1650 Ti (ADR-023). Không dùng RunPod cho feature này.
- Lệnh fork chạy từ `vendor/livetalking` bằng `.venv/Scripts/python`; lệnh app chạy từ gốc repo bằng `uv run`.

## 0. Chuẩn bị (một lần, sau khi Kaggle xong)

1. **[không GPU]** Tải đầu ra notebook `ai-host-train-ultralight-demo-host-02` (version 3) vào một thư mục mới, xem `loss.png` và ảnh
   preview, kiểm `provenance_train.json` / `teacher_run.json` đọc được.
2. **[GPU laptop]** Cài model (công cụ sẵn có, ADR-064):
   ```powershell
   cd vendor/livetalking
   .venv/Scripts/python -m ailive_ext.ultralight install <thư mục tải>/ultralight_out/demo_host_02/musetalk --video <video thầy MuseTalk>
   ```
   Kết quả: `data/avatars/demo_host_02__ultralight_musetalk/` và `__w2l_musetalk/`, bằng chứng trong
   `assets/avatars/demo_host_02/ultralight/musetalk/` (có `ultralight_install.json`).
3. **[không GPU]** Đo `desk_top` của `demo_host_02` (research R9) và tạo `assets/avatars/demo_host_02/character.json` theo
   [data-model.md](./data-model.md) §2.
4. **[không GPU]** Mở 3 khung đầu trong `data/avatars/demo_host_02__ultralight_musetalk/full_imgs/`: miệng khép chưa (research R6)?
   Chưa thì cài lại với `--frames` khác và ghi vào research.

## US1 (P1): show kịch bản bằng model riêng của `demo_host_02`

1. **[không GPU]** `uv run pytest` xanh; với `.env` mặc định (`LIVETALKING_MODEL` không đặt) app vẫn chạy Wav2Lip + `demo_host_01`
   như trước (FR-002).
2. **[không GPU]** Trong `.env`: `AVATAR_MODE=livetalking`, `AVATAR_ID=demo_host_02`, `AVATAR_DIR=assets/avatars/demo_host_02`,
   `LIVETALKING_MODEL=ultralight`, `LIVETALKING_ULTRALIGHT_TEACHER=musetalk`. (Người dùng tự sửa `.env`.)
3. **[GPU laptop]** `scripts/livetalking/run.ps1`; log fork có dòng kiểm bản ghi cài đặt Đạt, `hello` có khối `lipsync` (xem
   `GET /ailive/health`).
4. **[GPU laptop]** `uv run uvicorn ai_live.app.main:app --port 8000`; `uv run python -m ai_live.ops readiness` → mục "Model nhép miệng"
   OK. Trang điều khiển hiện "Model: Ultralight · thầy MuseTalk · demo_host_02".
5. **[GPU laptop]** Chạy show kịch bản 10 phút (1 sản phẩm chính + 2 phụ, như tổng duyệt 007), xem trang `/host`:
   - nhãn "AI-GENERATED CONTENT" luôn hiện (FR-004);
   - lúc im lặng miệng khép, không giật (FR-005);
   - bàn trong ảnh, sản phẩm đứng trên mép bàn, không vẽ thêm bàn (FR-011).
   Rồi `uv run python -m ai_live.ops report <session_id>` → `render_fps` p50, lặng p95, câu đầu; ghi `infer_fps`, `vram_peak_mb` từ
   `/ailive/health` (research R7 TODO).

## US2 (P2): so sánh với Wav2Lip

1. **[GPU laptop]** Bộ đo khẩu hình trên cùng nhân vật:
   ```powershell
   cd vendor/livetalking
   .venv/Scripts/python -m ailive_ext.mouth_eval --methods w2l,ultralight --avatar demo_host_02__w2l_musetalk --idle-avatar none --ab ultralight --clips
   ```
2. **[GPU laptop]** Show A: `.env` cấu hình demo hiện tại (`LIVETALKING_MODEL=wav2lip`, `demo_host_01`, `LIVETALKING_MOUTH_METHOD=w2l`),
   show kịch bản 10 phút cùng sản phẩm. Show B: phiên US1 bước 5 (hoặc chạy lại).
3. **[không GPU]**
   ```bash
   uv run python -m ai_live.ops lipsync-compare --mouth out/mouth/runs/<ngày-giờ> --show-a <phiên A> --show-b <phiên B>
   ```
   Mở `out/011_compare/<ngày-giờ>/report.md`: dòng kết luận đầu, bảng ngưỡng ADR-060 mục 5, đường dẫn gói xem mù.
4. **Người dùng:** chấm gói xem mù `ab/PHIEU.md` (không mở `ab_key.json` trước khi chấm). Việc đánh giá này làm ngay khi model Kaggle
   xong (ADR-066 mục 2, sửa 2026-11-19).

## US3 (P3): đổi thầy và chặn model sai

1. **[không GPU]** Các ca test tự động (không cần model thật) phải xanh:
   - `LIVETALKING_ULTRALIGHT_TEACHER=infinitetalk` khi chưa cài → kiểm tra trước demo offline báo `install_missing`;
   - `AVATAR_ID=demo_host_01` + `LIVETALKING_MODEL=ultralight` → `model_not_supported`;
   - bản ghi cài đặt của nhân vật khác / file model bị đổi → `install_character_mismatch` / `checkpoint_mismatch`;
   - fork giả báo `model: wav2lip` khi cấu hình `ultralight` → `fork_model_mismatch`.
2. **[GPU laptop]** Sửa `.env` sang `infinitetalk` mà chưa cài model thầy đó, chạy `run.ps1` → fork thoát ngay với thông báo tiếng Việt
   (không nạp HuBERT). Đổi lại `musetalk`.
3. **[GPU laptop]** Đổi `.env` sang `wav2lip` mà **không** bật lại fork Ultralight đang chạy → `readiness` báo LỖI `fork_model_mismatch`,
   trang điều khiển báo đỏ (Q36). Bật lại fork → OK.
4. Thầy prod (InfiniteTalk) chỉ làm khi người dùng đồng ý chi GPU thuê (ADR-064, ADR-066): cài bằng lệnh bước 0.2 với thư mục
   `.../infinitetalk`, đổi biến, lặp US1.

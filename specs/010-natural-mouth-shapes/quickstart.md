# Quickstart: 010 Khẩu hình miệng host AI

> Chạy trên laptop dev. Bước 1–2 không cần GPU; bước 3–6 cần venv fork `vendor/livetalking/.venv` và GPU laptop (ADR-023).
> Không cần LLM, không RunPod. Mọi file đo, video, gói A/B nằm trong `out/` (ngoài git).

## 1. File cần có (ngoài git)

| File | Nguồn | ADR |
|---|---|---|
| `vendor/livetalking/models/wav2lip.pth` | như 005 | 005 |
| `vendor/livetalking/models/face_landmarker.task` | MediaPipe (Apache-2.0) | ADR-053 |
| `vendor/livetalking/models/syncnet_v2.model` | SyncNet (chỉ để đo) | ADR-054 |
| `vendor/livetalking/data/avatars/demo_host_01__{idle,talk}_0N/` | `python -m ai_live.avatar prepare` (005) | 005 |

Thiếu `face_landmarker.task` thì `prepare` vẫn chạy, chỉ bỏ bước góc đầu và báo "góc đầu: bỏ qua". Bộ đo thì cần đủ cả ba.

## 2. Đọc bộ câu mẫu thành tiếng (CPU)

```bash
TTS_PROVIDER=vieneu uv run python scripts/mouth/synth_sentences.py     # ra out/mouth/sentences/<id>.wav, bỏ qua câu đã có
```

Bộ câu `data/eval/mouth_sentences.json` có số phiên bản (`version`). Đổi bộ câu thì tăng `version`; chỉ so kết quả trong cùng phiên bản.

## 3. Đo khẩu hình (GPU laptop, contracts/mouth-eval.md)

```bash
cd vendor/livetalking
PYTHONIOENCODING=utf-8 .venv/Scripts/python.exe -m ailive_ext.mouth_eval --methods "w2l,s1@shift=-1" --out ../../out/mouth/runs/<tên>
# thêm --clips --ab s1 để xuất video đặt cạnh nhau và gói xem mù so s1 với w2l
```

- Kết quả: `out/mouth/runs/<tên>/report.md` (bảng chỉ số, ✓/✗ theo ngưỡng SC-002/003/005, dòng SC-001 so với `w2l`) và `report.json`.
- Một vòng 24–27 câu, 2 cách, có SyncNet mất khoảng 5–10 phút trên GTX 1650 Ti.
- `detected` phải ≥ 0,95, nếu thấp hơn thì mặt trong clip nói không đo được, số không tin được.
- Các lần đã chạy và kết luận: research R6 (r1), R7 (r2), R10 (r3), R12 (r4, đo lặp lại).

## 4. Chọn cách tạo miệng cho live

```bash
# trong .env của máy chạy live (không sửa .env.example trừ khi đổi mặc định bằng ADR)
LIVETALKING_MOUTH_METHOD=w2l              # mặc định (ADR-055), y hệt 005
LIVETALKING_MOUTH_METHOD=shift=-1         # ứng viên: hết lệch hình–tiếng 1 khung, chờ kết quả A/B (§7)
```

Cú pháp đủ ở contracts/mouth-method.md. Giá trị sai thì fork ghi lỗi và dùng `w2l`. Kiểm cách đang chạy: cột "Miệng" trong bảng độ trễ ở
trang điều khiển (`/api/latency`, FR-010) hoặc trường `mouth_method` trong `hello`/`stats` của fork.

## 5. Loại đoạn clip nói đầu nghiêng (US3)

```bash
uv run python -m ai_live.avatar prepare assets/avatars/demo_host_01
# mỗi clip nói in thêm: "góc đầu: dùng N khung, loại M đoạn" và từng đoạn bị loại kèm lý do
```

- Ngưỡng mặc định so với tư thế trung vị của clip idle: nghiêng (roll) 35°, ngửa/cúi (pitch) 20°, quay (yaw) 30° (ADR-056). Đổi bằng
  `--max-roll/--max-pitch/--max-yaw` của `prepare` trong fork (fork-protocol §5).
- Với `demo_host_01` ngưỡng mặc định không loại khung nào (research R11). Roll 20° sẽ loại gần hết `talk_02`.
- Còn dưới 4 giây dùng được thì `prepare` cảnh báo: nên quay lại clip nói nhìn thẳng hơn.
- Fork đọc `ailive_pose.json` lúc khởi động, phát mỗi đoạn dùng được như một clip `talk_NN~k`; file hỏng hoặc không còn đoạn nào thì phát
  cả clip và ghi chú trong log.

## 6. Show kiểm SC-005/SC-006 (chỉ khi đổi cách mặc định hoặc ngưỡng)

Như quickstart 005 §9, show kịch bản 10 phút với `LIVETALKING_MOUTH_METHOD` cần kiểm. Chạy được không cần LLM bằng `REPLY_ENGINE=fake`.
Bật recorder của fork (`AILIVE_RECORD_DIR`, `scripts/selfcheck/lipsync_check.py`): mỗi khung ghi `clip` và `idx`, đối chiếu với các đoạn
`excluded` trong `ailive_pose.json` để kiểm SC-006. Tiêu chí SC-005: `render_fps` trung vị ≥ 20, câu đầu chậm thêm ≤ 0,3 s, lặng p95 tăng
≤ 0,1 s so với 005.

## 7. Gói duyệt cuối (cần mắt người)

1. **A/B khẩu hình (SC-004):** mở `out/mouth/runs/r4/ab/`, xem từng cặp `<đoạn>_X.mp4` / `<đoạn>_Y.mp4` (4 đoạn ~20 giây), ghi lựa chọn
   vào `PHIEU.md`. Cần ít nhất 3 người xem, mỗi người một bản phiếu. Chấm xong mới mở `out/mouth/runs/r4/ab_key.json`.
   - Nếu ≥ 2/3 người chọn bản `s1` (`shift=-1`) ở đa số đoạn: đổi mặc định, ghi ADR mới thay ADR-055, chạy show §6.
   - Nếu không: giữ `w2l`.
2. **Xem kỹ thuật (không mù):** `out/mouth/runs/r4/side_by_side/*.mp4` đặt `w2l` và `s1` cạnh nhau để soi môi khép ở b/m/p.
3. **Ngưỡng góc đầu:** giữ mặc định 35/20/30 (không loại gì trên clip hiện có) hay siết lại. Siết thì chạy lại `prepare` (§5) và show §6.
4. **Hướng tiếp theo nếu khẩu hình vẫn chưa đủ giống người:** không núm hậu kỳ nào đạt SC-001 (research R10). Hai hướng còn lại:
   quay clip nói mới (mặt thẳng, ánh sáng đều, miệng mở rõ) hoặc model mạnh hơn trên GPU thuê (tốn tiền, cần hỏi trước, ADR mới).

## 8. Quay video huấn luyện Ultralight (ADR-060)

> **Không dùng lúc này:** ngày 2026-11-17 người dùng chốt dùng nhân vật AI, video huấn luyện tạo bằng InfiniteTalk (ADR-060 mục 1).
> Giữ mục này nếu sau này đổi sang người thật.

Ultralight học riêng cho người trong video, và khung hình live cũng lấy từ chính video này. **Người được quay sẽ là gương mặt của host**
khi chạy Ultralight.

**Trước khi quay:** người mẫu ký văn bản đồng ý cho dùng gương mặt (và giọng, nếu sau này nhái giọng bằng `VIENEU_REF_AUDIO`). Bản ký
lưu ngoài git (ràng buộc 4, RISKS S5). Không quay ai chưa ký. Không dùng gương mặt người nổi tiếng.

**Hình:**
- Dài 3–5 phút, **25 khung/giây** (HuBERT cần đúng 25 fps), 1080p là đủ. Điện thoại quay được, khóa fps ở 25 nếu máy cho chọn; nếu không
  thì quay 30 rồi đổi sang 25 bằng ffmpeg.
- Đặt máy trên chân máy, không cầm tay, không zoom. Khung hình giống live: nửa người, mặt ở giữa, nhìn thẳng ống kính.
- **Mặt thấy rõ ở mọi khung:** không đưa tay, tóc, micro hay sản phẩm che miệng; không quay nghiêng quá nhiều; không ra khỏi khung.
- Ánh sáng đều phía trước mặt (đèn vòng hoặc cửa sổ), không ngược sáng, không bóng đổ lên miệng.
- Nền đơn giản, đứng yên. Trang phục và tóc giống ngày live, vì đây là hình nền khi live.

**Tiếng:**
- Mic rời (mic cài áo) gần miệng; phòng yên, ít vang; tắt quạt và điều hòa nếu ồn.
- **20 giây đầu không nói:** ngồi tự nhiên, chớp mắt, cử động đầu nhẹ, miệng khép. Đây là khung lúc host im lặng.
- Sau đó đọc tiếng Việt với giọng live bình thường, rõ chữ, nhịp vừa: nội dung sản phẩm (file `.docx` của khách), các câu trong bộ câu
  v2 của 010 (`data/eval/mouth_sentences.json`) và nhiều tiếng có b/m/p (môi khép), o/u (môi tròn), a (miệng mở lớn).
- Giữa các câu có lúc nghỉ ngắn, miệng khép tự nhiên.

**Sau khi quay:**
- Chép file gốc vào `assets/avatars/<tên>/ultralight_src.mp4` (ngoài git, `.gitignore` đã chặn `assets/avatars/`). Không gửi lên dịch
  vụ ngoài. Nếu phải huấn luyện trên Kaggle thì dùng dataset riêng tư và xóa sau khi xong.
- Kiểm nhanh: `ffprobe` thấy `r_frame_rate=25/1` và có luồng âm thanh; mở xem lại đủ 20 giây im lặng đầu.
- Báo Claude để chạy `process.py` → `train.py` → `genavatar.py` và đo theo §3 (ADR-060 mục 2–4).

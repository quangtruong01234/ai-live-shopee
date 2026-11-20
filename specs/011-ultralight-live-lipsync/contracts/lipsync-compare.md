# Hợp đồng: lệnh so sánh Ultralight với Wav2Lip (US2)

- **Feature:** 011 · **Ngày:** 2026-11-19 · Liên quan: 010 `contracts/mouth-eval.md` (bộ đo, gói xem mù), 007 báo cáo tổng duyệt
  (`ops/rehearsal.py`), ADR-060 mục 5 (ngưỡng), [data-model.md](../data-model.md) §6.

## 1. Đầu vào

| Đầu vào | Tạo bằng | Cần GPU |
|---------|----------|---------|
| Thư mục bộ đo khẩu hình (`out/mouth/runs/<ngày-giờ>/report.json`) | `vendor/livetalking/.venv/Scripts/python -m ailive_ext.mouth_eval --methods w2l,ultralight --avatar demo_host_02__w2l_musetalk --idle-avatar none --ab ultralight` (010, không đổi) | Có |
| Phiên A (Wav2Lip) | show kịch bản 10 phút, `LIVETALKING_MODEL=wav2lip`, `demo_host_01` | Có |
| Phiên B (Ultralight) | show kịch bản 10 phút, `LIVETALKING_MODEL=ultralight`, `demo_host_02` | Có |

Lệnh so sánh **không** cần GPU: chỉ đọc file.

## 2. Lệnh

```bash
uv run python -m ai_live.ops lipsync-compare \
  --mouth out/mouth/runs/<YYYYMMDD-HHMMSS> \
  --show-a <session_id hoặc thư mục phiên>[:<show_id>] \
  --show-b <session_id hoặc thư mục phiên>[:<show_id>] \
  [--out out/011_compare]
```

- `--show-*` dùng lại `resolve_session_dir` và `last_show_id` của 007 (thiếu `:show_id` → show cuối của phiên).
- Mã thoát: 0 kết luận Đạt; 1 Chưa đạt; 2 Thiếu số; 3 đầu vào không đọc được (thông báo tiếng Việt, không viết báo cáo).
- Cảnh báo (vẫn viết báo cáo): phiên A không phải `wav2lip` hoặc phiên B không phải `ultralight` theo dòng `lipsync_connected`; show
  ngắn hơn 10 phút; bộ đo không chạy trên `demo_host_02`.

## 3. Ngưỡng (ADR-060 mục 5, không hạ)

| id | Tên | Ngưỡng | Nguồn |
|----|-----|--------|-------|
| `mouth_metrics` | Khẩu hình tốt hơn | ≥ 2/4 chỉ số hình miệng (`closure_recall`, `open_ratio`, `corr_open_loud`, `sharp_ratio`) của Ultralight tốt hơn Wav2Lip ≥ 15% | bộ đo: `summaries[method=ultralight].sc001.better` |
| `lse_c` | Khớp tiếng | LSE-C của Ultralight không thấp hơn Wav2Lip | bộ đo: `summaries[method=ultralight].sc001.sync_ok` |
| `render_fps` | Tốc độ khung | `render_fps` p50 phiên B ≥ 20 | `avatar.jsonl` dòng `render` (cách tính của báo cáo tổng duyệt) |
| `vram` | VRAM | `vram_peak_mb` lớn nhất phiên B ≤ 3584 | `avatar.jsonl` dòng health |
| `errors` | Không lỗi | phiên B 0 lỗi trong ≥ 10 phút, kết thúc bình thường | cảnh báo watchdog mức lỗi, `vram_oom`, `renderer_restarted` |
| `first_sentence` | Câu đầu | phiên B ≤ 5 s | báo cáo tổng duyệt |
| `gap_p95` | Lặng giữa câu | phiên B p95 ≤ 1,5 s **và** ≤ 1,1 × phiên A (SC-002) | báo cáo tổng duyệt |

Số nào không có trong đầu vào → dòng đó "Thiếu số", không đoán. Hai dòng đầu đọc nguyên kết quả `versus_baseline` của bộ đo 010
(`mouth_eval/report.py`, đường gốc `w2l`), không tính lại. Cột "đạt mục tiêu tuyệt đối" (`summaries[].pass`, các `TARGETS` của 010) chỉ
chép vào báo cáo để tham khảo, không vào kết luận (ADR-060 mục 5 so tương đối với Wav2Lip).

## 4. Đầu ra

`<--out>/<YYYY-MM-DD_HH-MM-SS>/`:

- `verdict.json`: data-model §6.
- `report.md` (tiếng Việt):
  1. Dòng kết luận đầu tiên: "**Kết luận: Đạt / Chưa đạt / Thiếu số**" + một câu "Theo ADR-066: đạt thì demo dùng Ultralight thầy
     MuseTalk; chưa đạt giữ Wav2Lip (ADR-062)".
  2. Bảng ngưỡng §3: id, tên, ngưỡng, A, B, kết quả.
  3. Điều kiện hai phiên (model, thầy, nhân vật, máy, thời lượng).
  4. Đường dẫn gói xem mù (`ab/PHIEU.md`) để người dùng chấm; lệnh không mở khóa đáp án.
- Không chép video, khung hình hay tiếng vào thư mục báo cáo (chỉ đường dẫn), để báo cáo nhỏ và không chứa dữ liệu nhân vật thừa.

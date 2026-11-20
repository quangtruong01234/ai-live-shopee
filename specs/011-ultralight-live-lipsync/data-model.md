# Mô hình dữ liệu: 011-ultralight-live-lipsync

- **Ngày:** 2026-11-19 · **Plan:** [plan.md](./plan.md) · **Nghiên cứu:** [research.md](./research.md)

## 1. `LipsyncSelection` (cấu hình, app và `run.ps1`)

| Trường | Biến môi trường | Kiểu | Mặc định | Kiểm hợp lệ |
|--------|-----------------|------|----------|-------------|
| `model` | `LIVETALKING_MODEL` | `Literal["wav2lip", "ultralight"]` | `wav2lip` | Giá trị khác → lỗi cấu hình lúc khởi động |
| `teacher` | `LIVETALKING_ULTRALIGHT_TEACHER` | `Literal["musetalk", "infinitetalk"]` | `musetalk` | Chỉ dùng khi `model=ultralight`; giá trị khác → lỗi cấu hình |
| `character_id` | (tên thư mục `AVATAR_DIR`) | `str` | – | Bằng `AVATAR_ID` (luật 005 giữ nguyên) |

- `avatar_id` của fork khi `model=ultralight` = `<character_id>__ultralight_<teacher>` (hàm `ultralight_avatar_id` sẵn có).
- Chỉ có tác dụng khi `AVATAR_MODE=livetalking`; với `static` hai biến bị bỏ qua (test không GPU không cần chúng).

## 2. `character.json` (mở rộng, vẫn `schema_version: 1`)

Trường mới, đều tùy chọn để `demo_host_01` không phải sửa:

| Trường | Kiểu | Mặc định | Luật |
|--------|------|----------|------|
| `lipsync_models` | `list[Literal["wav2lip", "ultralight"]]` | `["wav2lip"]` | Không rỗng, không lặp. `"wav2lip"` có trong danh sách → bắt buộc ≥1 clip idle + ≥1 clip talk (`kind_missing`) và `prepare.status == "ready"` như 005. Không có → `clips` được rỗng, `prepare` được thiếu |
| `scene.desk_in_image` | `bool` | `false` | `true` → cảnh 009 không vẽ lớp bàn |
| `scene.desk_top` | `float \| null` | `null` | Bắt buộc khi `desk_in_image=true`; trong [0,55; 0,92] (giới hạn của `layout.compute_layout`) |

Ví dụ `assets/avatars/demo_host_02/character.json` (ngoài git; cùng khách `demo_customer_01` với `demo_host_01` vì ADR-066 cho
`demo_host_02` thay `demo_host_01` của khách demo):

```json
{
  "schema_version": 1,
  "character_id": "demo_host_02",
  "customer_id": "demo_customer_01",
  "face": "face.png",
  "provenance": "provenance.json",
  "clips": [],
  "lipsync_models": ["ultralight"],
  "scene": {"desk_in_image": true, "desk_top": null}
}
```

- `provenance` trỏ `provenance.json` sẵn có (đã có `character_id: demo_host_02`, `kind: ai_generated_fictional_face`, `models`), qua
  `_check_provenance` như 005; không có clip nên phần đối chiếu clip trong `provenance.json` không áp dụng.
- `desk_top: null` ở ví dụ chỉ vì chưa đo (research R9 TODO); `load_character` báo lỗi cho tới khi điền số đo.

## 3. `UltralightInstall` (đọc, do `ailive_ext.ultralight install` viết)

File `ultralight_install.json`, hai bản giống nhau: `vendor/livetalking/data/avatars/<avatar_id>/` và
`assets/avatars/<character_id>/ultralight/<teacher>/`.

| Trường | Kiểu | Dùng để kiểm |
|--------|------|--------------|
| `character_id` | `str` | Bằng nhân vật đang chọn |
| `teacher` | `str` | Bằng `LIVETALKING_ULTRALIGHT_TEACHER` |
| `checkpoint.file` | `str` | Tên file model trong thư mục bằng chứng |
| `checkpoint.sha256` | `str` (64 hex) | Bằng sha256 file model (fork: `ultralight.pth` trong `data/avatars`; app: file trong thư mục bằng chứng) và bằng `lipsync.checkpoint_sha256` fork báo |
| `fork_commit` | `str` | Chỉ ghi vào báo cáo (cảnh báo nếu khác commit fork đang chạy, như 005) |
| `frames`, `video.sha256`, `installed_at`, `epochs_done` | | Chỉ hiển thị |

App và fork **chỉ đọc** bản ghi; 011 không đổi `install`.

## 4. `LipsyncReport` (fork → app, trong `hello` và `/ailive/health`)

| Trường | Kiểu | Wav2Lip | Ultralight |
|--------|------|---------|------------|
| `model` | `"wav2lip" \| "ultralight"` | `wav2lip` | `ultralight` |
| `teacher` | `str \| null` | `null` | `musetalk` / `infinitetalk` |
| `character_id` | `str \| null` | tên thư mục nhân vật (`--ailive_character`), `null` nếu không dùng | tên thư mục nhân vật |
| `avatar_id` | `str` | avatar đầu tiên của thư viện clip | `<character_id>__ultralight_<teacher>` |
| `checkpoint_sha256` | `str \| null` | `null` | sha256 `ultralight.pth` đã kiểm lúc bật |

App lưu bản sao mới nhất trong `LipsyncHealth` (thêm trường `lipsync: dict | None`), ghi vào `avatar.jsonl` dòng `lipsync_connected`, và
hiện trên trang điều khiển. Thiếu khối (fork cũ) → `None`; kiểm tra trước demo coi là `fork_model_mismatch` khi `LIVETALKING_MODEL=ultralight`,
và bỏ qua khi `wav2lip` (tương thích fork cũ).

## 5. `LipsyncCheck` (kiểm tra trước demo, 007)

Một mục mới "Model nhép miệng" trong `ReadinessReport`, trạng thái OK / LỖI, cùng kiểu với các mục hiện có.

| Mã | Khi nào | Thông báo (tiếng Việt, gợi ý) |
|----|---------|-------------------------------|
| `model_not_supported` | `LIVETALKING_MODEL` không có trong `lipsync_models` của nhân vật | "Nhân vật demo_host_01 không có model ultralight" |
| `install_missing` | Thiếu `ultralight_install.json` hoặc file model trong thư mục bằng chứng | "Chưa cài model Ultralight thầy infinitetalk cho demo_host_02" |
| `install_character_mismatch` | `character_id` của bản ghi khác nhân vật | "Model cài cho nhân vật khác (…)" |
| `install_teacher_mismatch` | `teacher` của bản ghi khác cấu hình | "Model cài là thầy musetalk, cấu hình là infinitetalk" |
| `checkpoint_mismatch` | sha256 file model khác bản ghi | "File model đã bị đổi sau khi cài" |
| `fork_model_mismatch` | Khối `lipsync` của fork khác cấu hình (model, thầy, nhân vật hoặc sha256), hoặc thiếu khi cần | "Phần nhép miệng đang chạy wav2lip, cấu hình là ultralight: bật lại fork" |

Với `model=wav2lip` mục này chỉ kiểm `model_not_supported` và `fork_model_mismatch` (model); phần clip giữ nguyên mục "Nhân vật" của 005.

## 6. `CompareReport` (US2, `out/011_compare/<ngày-giờ>/verdict.json`)

| Trường | Kiểu | Nguồn |
|--------|------|-------|
| `created_at` | ISO 8601 | – |
| `inputs` | `{mouth_dir, show_a: {session_id, show_id}, show_b: {...}}` | tham số lệnh |
| `conditions` | `{a: {model, teacher, character_id, mouth_method}, b: {...}}` | dòng `lipsync_connected` / `render` của mỗi phiên |
| `mouth` | `{metrics: {tên: {a, b, gain}}, lse_c: {a, b}, better: int, sync_ok: bool \| null}` | `report.json` của bộ đo 010 (`summaries`, khối `sc001` của `ultralight`) |
| `show` | `{a: ShowFigures, b: ShowFigures}` | báo cáo tổng duyệt 007 (`load_show_logs`, `build_report`) + `avatar.jsonl` |
| `criteria` | `list[Criterion]` | tính ở lệnh |
| `verdict` | `"Đạt" \| "Chưa đạt" \| "Thiếu số"` | Đạt khi mọi `criteria` Đạt; có dòng Thiếu số mà không dòng nào Chưa đạt → Thiếu số |
| `ab_pack` | `str \| null` | đường dẫn `ab/PHIEU.md` của bộ đo nếu có |

`ShowFigures`: `duration_s`, `first_sentence_s`, `gap_p95_s`, `render_fps_p50`, `vram_peak_mb`, `errors` (số cảnh báo mức lỗi của watchdog
+ dòng `vram_oom`/`renderer_restarted`), `ended_normally`.

`Criterion`: `{id, name, threshold, a, b, result: "Đạt" | "Chưa đạt" | "Thiếu số"}`. Danh sách cố định ở
[contracts/lipsync-compare.md](./contracts/lipsync-compare.md) §3.

## Chuyển trạng thái

```
cấu hình (.env) ──run.ps1──▶ fork bật ──verify_live──▶ (sai) thoát, thông báo tiếng Việt
                                   │ (đúng)
                                   ▼
                       hello{lipsync} ──▶ app so với cấu hình ──▶ khớp: show chạy được
                                                               └▶ lệch: kiểm tra trước demo LỖI, trang điều khiển báo đỏ
```

Không có chuyển trạng thái giữa show: đổi model = dừng show, sửa `.env`, bật lại fork (FR-014).

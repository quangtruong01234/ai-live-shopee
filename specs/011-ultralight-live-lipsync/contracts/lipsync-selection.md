# Hợp đồng: chọn model nhép miệng và báo cáo model đang chạy

- **Feature:** 011 · **Ngày:** 2026-11-19 · Liên quan: 005 `contracts/fork-protocol.md` §1 (`hello`), §5 (`/ailive/health`);
  007 `contracts/readiness.md`; [data-model.md](../data-model.md) §1–§5.

## 1. Biến môi trường (`.env.example`, khối LiveTalking)

```dotenv
# Model nhép miệng của fork (011, ADR-067): wav2lip = thư viện clip 005 (mặc định); ultralight = model riêng của nhân vật.
LIVETALKING_MODEL=wav2lip
# Thầy của model Ultralight (ADR-064): musetalk = dev (mặc định, ADR-066), infinitetalk = prod. Chỉ dùng khi LIVETALKING_MODEL=ultralight.
LIVETALKING_ULTRALIGHT_TEACHER=musetalk
```

App đọc qua `Settings.livetalking_model`, `Settings.livetalking_ultralight_teacher`. `run.ps1` đọc cùng hai khóa từ `.env`.

## 2. `scripts/livetalking/run.ps1` → tham số fork

| `LIVETALKING_MODEL` | Tham số fork | Biến fork khác |
|---------------------|--------------|----------------|
| `wav2lip` | `--model wav2lip --ailive_character <AVATAR_DIR> ...` (như hiện tại) | như hiện tại |
| `ultralight` | `--model ultralight --ailive_character <AVATAR_DIR> --ailive_teacher <thầy> --batch_size <LIVETALKING_BATCH_SIZE> ...` | Không truyền `LIVETALKING_MOUTH_METHOD`, `LIVETALKING_LIP_EVERY_N`, `LIVETALKING_TRANSITION_S`, `LIVETALKING_HOLD_S`; in "bỏ qua cho ultralight: <tên>" nếu chúng khác mặc định (research R8) |
| khác | `run.ps1` dừng với "LIVETALKING_MODEL phải là wav2lip hoặc ultralight" | – |

Nhãn AI (`AI_LABEL_TEXT`, `AI_LABEL_POSITION`) và ghi hình (`AILIVE_RECORD_*`) truyền như cũ cho mọi model (FR-004).

## 3. Fork lúc bật (`app.py`, `ailive_ext/ultralight.verify_live`)

Với `--model ultralight --ailive_character <dir> --ailive_teacher <t>`:

1. `character_id = basename(<dir>)`; `t` phải thuộc `TEACHERS`.
2. `avatar_id = ultralight_avatar_id(character_id, t)`; thư mục `data/avatars/<avatar_id>/` phải có `full_imgs/`, `face_imgs/`,
   `coords.pkl`, `ultralight.pth`, `ultralight_install.json`.
3. Bản ghi: `character_id == character_id`, `teacher == t`, `checkpoint.sha256 == sha256(ultralight.pth)`.
4. Sai bất kỳ bước nào → thoát mã khác 0, một dòng `[ailive] ...` tiếng Việt nêu bước sai và lệnh sửa
   (`python -m ailive_ext.ultralight install ...`). Không nạp HuBERT trước khi kiểm xong (đỡ chờ 1,26 GB khi cấu hình sai).
5. Đúng → `load_model`, `load_avatar(avatar_id)`, `warm_up` như đường gốc; ghi `opt.ailive_lipsync` (khối §4) để `ingest` gửi.

`--ailive_teacher` không có `--ailive_character`, hoặc `--ailive_character` với model khác `wav2lip`/`ultralight` → thoát như dòng 146
hiện tại.

## 4. Khối `lipsync` trong `hello` và `/ailive/health`

Thêm vào cả hai (tùy chọn; app bỏ qua khóa lạ, app cũ bỏ qua khối):

```json
"lipsync": {
  "model": "ultralight",
  "teacher": "musetalk",
  "character_id": "demo_host_02",
  "avatar_id": "demo_host_02__ultralight_musetalk",
  "checkpoint_sha256": "<64 hex>"
}
```

Với Wav2Lip: `{"model": "wav2lip", "teacher": null, "character_id": "demo_host_01", "avatar_id": "<avatar clip đầu>",
"checkpoint_sha256": null}`.

`hello.mouth_method` (010) = `"ultralight"` với `LightReal`; dòng `stats`/`render` mang `mouth_method: "ultralight"` như wav2lip mang
tên phương pháp 010. Không đổi khóa nào khác của `hello`, `stats`, `health`; `scene` (009) vẫn gửi khi cảnh bật.

## 5. App khi nhận `hello`

- `LivetalkingRenderer._on_hello` lưu `lipsync` vào `LipsyncHealth.lipsync`, ghi `avatar.jsonl` dòng `lipsync_connected` có thêm khối
  `lipsync`, phát lên trang điều khiển.
- So với cấu hình: lệch (model, thầy, nhân vật, hoặc sha256 khác bản ghi bằng chứng) → log `lipsync_model_mismatch` mức WARNING và cờ
  `model_mismatch=True` trong health. Không tự ngắt kết nối (show đang chạy không bị cắt; FR-014), nhưng kiểm tra trước demo báo LỖI và
  trang điều khiển hiện băng đỏ "Model nhép miệng không khớp cấu hình".

## 6. Kiểm tra trước demo (007, `ops/readiness.py`)

Mục mới **"Model nhép miệng"** ngay sau mục "Nhân vật":

| Bước | Khi `wav2lip` | Khi `ultralight` |
|------|---------------|------------------|
| Model có trong `lipsync_models` | ✔ | ✔ |
| Bản ghi cài đặt + sha256 trong `<AVATAR_DIR>/ultralight/<thầy>/` | – | ✔ (băm trong thread) |
| Fork đang chạy báo `lipsync` khớp | ✔ (chỉ `model`) | ✔ (model, thầy, nhân vật, sha256) |

Mã lỗi và thông báo: data-model §5. Chế độ offline (`run_offline`, fork tắt) kiểm hai bước đầu và ghi "chưa kiểm fork". Mục "Nhân vật"
của 005 với nhân vật không có clip: không báo thiếu clip khi `"wav2lip"` không có trong `lipsync_models`.

## 7. Trang điều khiển

Dòng trạng thái nhép miệng thêm "Model: Ultralight · thầy MuseTalk · demo_host_02" (hoặc "Model: Wav2Lip · demo_host_01"), lấy từ
`LipsyncHealth.lipsync`; thiếu khối → "Model: không rõ (fork cũ)".

## Khác với `docs/ARCHITECTURE.md` §3

Không đổi interface `AvatarRenderer`; chỉ thêm khối tùy chọn `lipsync` vào `hello`/health của fork và trường `lipsync` trong
`LipsyncHealth`. Ghi vào ARCHITECTURE khi triển khai (mục LiveTalking).

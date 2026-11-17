# Contract: `LIVETALKING_MOUTH_METHOD` (fork đọc)

- **Feature:** 010 · Thêm vào giao thức fork của 005 (`specs/005-lipsync-livetalking/contracts/fork-protocol.md`, `events.md`).

## 1. Cú pháp

```
LIVETALKING_MOUTH_METHOD = <preset> | <khóa>=<giá trị>[;<khóa>=<giá trị>...]
```

| Khóa | Giá trị | Mặc định |
|---|---|---|
| `ref` | `same` · `offset:N` (N nguyên) · `closed:W` (W ≥ 1) | `same` |
| `paste` | `rect` · `feather` | `rect` |
| `color` | `0` · `1` | `0` |
| `sharpen` | số thực ≥ 0 | `0` |
| `gain_db` | số thực | `0` |
| `shift` | số nguyên (khung 40 ms; âm = cửa sổ tiếng sớm hơn) | `0` |

- Khóa không ghi thì lấy mặc định. Chuỗi rỗng = `w2l`.
- Preset: `w2l` (= mọi mặc định, gọi model y hệt upstream) và các preset khác khai trong `PRESETS` của `ailive_ext/mouth.py`. Giá trị
  mặc định của dự án ghi ở `.env.example` (plan §Quyết định).
- `ref=closed:W` chỉ chạy trong bộ đo (bộ đo tự đo độ mở môi từng khung của clip). Lần đo r3 không đạt SC-001 (research R10) nên
  `prepare` **không** viết độ mở môi cho live; ở live, `ref=closed:W` chạy như `ref=same`. Muốn dùng ở live phải làm thêm (ghi ở plan).

## 2. Hành vi lỗi (FR-005)

| Tình huống | Fork làm gì |
|---|---|
| Chuỗi sai cú pháp / khóa lạ | `ERROR` log, dùng `w2l`; `stats.mouth_method` = `w2l` |
| Dán mềm lỗi ở một khung | khung đó dán hộp cứng như upstream; `ERROR` log **một lần** mỗi phiên |
| Hết bộ nhớ GPU | như 005: fork chết → app tự về ảnh tĩnh (ADR-046), trang điều khiển báo |

## 3. Báo cáo

- Tin `stats` mỗi câu (fork → app) có thêm `mouth_method: str` (tên cách đang chạy). App ghi vào `avatar.jsonl`, `/api/latency` và cột
  "Miệng" trên trang điều khiển (FR-010). Fork cũ không gửi → `null`, hiện `—`.
- `hello` của `/ailive/ws` có `mouth_method` cùng giá trị.

## 4. Bất biến

- Mọi núm chỉ đổi điểm ảnh **trong hộp mặt** của khung; cảnh (009), watermark và nhãn "AI" vẽ sau (ADR-044, ADR-052), không bị ảnh hưởng
  (FR-013).
- Không dựng trước: mel và ảnh tham chiếu lấy theo từng batch lúc phát (FR-001). `shift` âm chỉ đọc phần tiếng đã nằm trong bộ đệm 200 ms
  có sẵn của fork (`-l 10`), không thêm độ trễ.

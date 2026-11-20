# Tasks: Host AI nhép miệng bằng model riêng của nhân vật (Ultralight) trong show live

- **Feature ID:** `011-ultralight-live-lipsync` · **Đầu vào:** [spec.md](./spec.md), [plan.md](./plan.md), [research.md](./research.md),
  [data-model.md](./data-model.md), [contracts/](./contracts/), [quickstart.md](./quickstart.md)
- **Ngày:** 2026-11-19 · ADR-067, ADR-068, ADR-069 người dùng duyệt 2026-11-19 ("ok run đi").
- **Thời điểm đánh giá (sửa ADR-066 mục 2, 2026-11-19):** so sánh US2 chạy **ngay khi model Kaggle xong**, không chờ cả project xong.
  Demo luôn chạy trên laptop, miễn phí, share qua Meet (`OUTPUT_MODE=meet`). Không RunPod, không thầy InfiniteTalk cho demo.

## Định dạng: `- [ ] T### [P?] [GPU?] [US#?] Mô tả kèm đường dẫn file`

- **[P]**: chạy song song được (khác file, không phụ thuộc task chưa xong)
- **[GPU]**: cần GPU; chạy trên GPU laptop GTX 1650 Ti (ADR-023). Feature này không dùng RunPod. Gom vào đợt GPU (xem cuối file)
- **[US#]**: thuộc user story nào (US1, US2, US3). Phase Setup, Foundational và Hoàn thiện không gắn nhãn này.
- Lệnh fork chạy từ `vendor/livetalking` bằng `.venv/Scripts/python`; lệnh app chạy từ gốc repo bằng `uv run`.

## Phase 1: Setup

- [x] T001 [P] Thêm khối hai biến `LIVETALKING_MODEL=wav2lip` và `LIVETALKING_ULTRALIGHT_TEACHER=musetalk` kèm chú thích tiếng Việt
  vào khối LiveTalking của `.env.example` (contracts/lipsync-selection.md §1)
- [x] T002 [P] Tạo `assets/avatars/demo_host_02/character.json` theo data-model §2 (`customer_id: demo_customer_01`,
  `lipsync_models: ["ultralight"]`, `clips: []`, `provenance: provenance.json`, `scene.desk_in_image: true`, `desk_top: null` chờ T038);
  kiểm `git check-ignore` cho file này vẫn nằm ngoài git. Tới T038, `load_character` báo lỗi cho `demo_host_02` (đúng thiết kế,
  data-model §2): không chọn nhân vật này trước T038; test dùng file nhân vật giả, không đọc file này
- [x] T003 Khi notebook `jintran0501/ai-host-train-ultralight-demo-host-02` version 3 xong: tải đầu ra vào một thư mục mới, đọc bằng
  `python -I`, xem `loss.png`, ảnh preview, `provenance_train.json`, `teacher_run.json` (quickstart §0.1). Ghi kết quả vào `progress/LOG.md`

## Phase 2: Foundational (chặn mọi user story)

**⚠️ Không bắt đầu user story nào khi phase này chưa xong.**

- [x] T004 [P] Test cấu hình trong `tests/unit/test_config.py`: không đặt hai biến → `livetalking_model == "wav2lip"`,
  `livetalking_ultralight_teacher == "musetalk"` (FR-002); đặt `ultralight`/`infinitetalk` đọc đúng; giá trị khác báo lỗi kiểm hợp lệ
- [x] T005 [P] Test `character.json` mở rộng trong `tests/unit/test_character.py`: thiếu `lipsync_models` → `["wav2lip"]` và
  `demo_host_01` nạp như cũ (SC-008); danh sách rỗng hoặc lặp → lỗi; không có `"wav2lip"` → `clips` rỗng và thiếu `prepare` hợp lệ;
  có `"wav2lip"` mà thiếu clip → `kind_missing` như 005; `scene.desk_in_image: true` mà `desk_top` null hoặc ngoài [0,55; 0,92] → lỗi;
  `validate_for_session` với `LIVETALKING_MODEL` không có trong `lipsync_models` → `model_not_supported`; `demo_host_02` gắn đúng một
  khách, khách khác → lỗi như 005 (FR-016)
- [x] T006 Thêm `livetalking_model: Literal["wav2lip", "ultralight"] = "wav2lip"` và
  `livetalking_ultralight_teacher: Literal["musetalk", "infinitetalk"] = "musetalk"` vào `Settings` trong
  `src/ai_live/core/config.py` (T004 xanh)
- [x] T007 Mở rộng `src/ai_live/avatar/character.py`: trường `lipsync_models` và khối `scene` (`desk_in_image`, `desk_top`) trên
  `AvatarCharacter`; chỉ bắt clip và `prepare` khi có `"wav2lip"`; `validate_for_session` báo `model_not_supported` (phụ thuộc T006;
  T005 xanh)
- [x] T008 [P] Thêm trường `lipsync: dict | None = None` và `model_mismatch: bool = False` vào `LipsyncHealth` trong
  `src/ai_live/core/models.py`, và đưa hai trường vào payload của `lipsync_health_event` trong `src/ai_live/core/events.py`
- [x] T009 [P] Cho fork giả gửi khối `lipsync` trong `hello` và health trong `tests/fixtures/fake_fork.py` (chọn model, thầy, nhân vật,
  sha256; có tùy chọn bỏ khối để giả fork cũ)

**Checkpoint:** nền tảng sẵn sàng; `uv run pytest` xanh với cấu hình mặc định; các story bắt đầu được.

---

## Phase 3: User Story 1: show kịch bản bằng model riêng của `demo_host_02` (P1) 🎯 MVP

**Mục tiêu:** đặt `LIVETALKING_MODEL=ultralight` là show kịch bản chạy bằng model Ultralight thầy MuseTalk của `demo_host_02`, có nhãn AI,
miệng khép lúc im lặng, sản phẩm đứng trên bàn trong ảnh; trang điều khiển và bản ghi phiên ghi model đang chạy.
**Kiểm thử độc lập:** quickstart US1: test không GPU xanh, rồi show 10 phút trên laptop đạt SC-001, SC-002, SC-003.

### Test cho US1 (viết trước, phải FAIL trước khi implement)

- [x] T010 [P] [US1] Test fork trong `vendor/livetalking/ailive_ext/tests/test_ultralight.py`: `verify_live` với thư mục avatar giả đủ
  `full_imgs/`, `face_imgs/`, `coords.pkl`, `ultralight.pth`, `ultralight_install.json` khớp → trả `avatar_id`
  `demo_host_02__ultralight_musetalk` và khối `lipsync`; thiếu từng file → lỗi nêu đúng bước và lệnh `ailive_ext.ultralight install`;
  `character_id`, `teacher` hoặc sha256 khác → lỗi; thầy ngoài `TEACHERS` → lỗi; `check_live_args`: `--ailive_teacher` không có
  `--ailive_character`, hoặc `--ailive_character` với model khác `wav2lip`/`ultralight` → lỗi; không import torch/HuBERT khi kiểm
- [x] T011 [P] [US1] Test fork trong `vendor/livetalking/ailive_ext/tests/test_ingest.py`: (đọc bằng `ast`, không import torch) class
  `LightReal` trong `avatars/ultralight_avatar.py` kế thừa `BaseAvatar` và không tự định nghĩa `process_frames`, nên nhãn AI vẽ trong
  `BaseAvatar.process_frames` áp cho Ultralight (FR-004); `hello` và `/ailive/health` có khối `lipsync`
  (contracts/lipsync-selection.md §4) khi `opt.ailive_lipsync` đặt, kể cả khối Wav2Lip (`teacher: null`, `checkpoint_sha256: null`);
  `mouth_method_name()` trả `"ultralight"` với avatar giả kiểu `LightReal`; dòng `stats`/`render` mang `mouth_method: "ultralight"`
  (FR-010); các khóa khác của `hello` không đổi
- [x] T012 [P] [US1] Test fork trong `vendor/livetalking/ailive_ext/tests/test_scene.py`: `avatar_geometry` và `state_of` chạy được với avatar
  giả kiểu `LightReal` (chỉ `frame_list_cycle`, `coord_list_cycle`, không thư viện clip) (research R9)
- [x] T013 [P] [US1] Test app trong `tests/unit/test_character.py`: đọc bản ghi cài đặt `<AVATAR_DIR>/ultralight/<thầy>/ultralight_install.json`
  và băm file model (bản ghi đúng → trả `character_id`, `teacher`, sha256; thiếu bản ghi hoặc file model → `None` kèm lý do)
- [x] T014 [P] [US1] Test renderer trong `tests/unit/test_livetalking_renderer.py`: `_on_hello` lưu khối `lipsync` vào `LipsyncHealth.lipsync`,
  dòng `lipsync_connected` trong `avatar.jsonl` có khối; khối lệch cấu hình → log WARNING `lipsync_model_mismatch`, `model_mismatch=True`,
  **không** ngắt kết nối, không đổi model (FR-014); thiếu khối (fork cũ) → `lipsync=None`, không lỗi
- [x] T015 [P] [US1] Test kiểm tra trước demo trong `tests/unit/test_readiness.py`: mục "Model nhép miệng" đứng ngay sau "Nhân vật";
  cấu hình mặc định Wav2Lip + fork báo `wav2lip` → OK; `ultralight` + bản ghi khớp + fork khớp → OK, có dòng "Model: Ultralight · thầy
  MuseTalk · demo_host_02" (FR-009); `model_not_supported` và `install_missing` → LỖI tiếng Việt nói cách sửa; offline → kiểm hai bước đầu,
  ghi "chưa kiểm fork"; nhân vật không có `"wav2lip"` → mục "Nhân vật" không báo thiếu clip
- [x] T016 [P] [US1] Test bố cục trong `tests/unit/test_scene_layout.py`: `desk_top` của nhân vật thay `layout.desk_top` của `scene.json`;
  thẻ sản phẩm đứng trên mép đó; kiểm "bàn không chạm mặt" vẫn chặn khi `desk_top` chạm vùng mặt (FR-011)
- [x] T017 [P] [US1] Test vẽ cảnh trong `tests/unit/test_scene_render.py`: `desk_in_image: true` → không có điểm ảnh lớp bàn, vẫn có thẻ
  sản phẩm và vùng làm nổi sản phẩm (FR-011)
- [x] T018 [P] [US1] Test controller trong `tests/unit/test_scene_controller.py`: controller đọc khối `scene` của nhân vật đang dùng và
  truyền `desk_in_image`/`desk_top` cho bố cục và vẽ; nhân vật không khai khối → hành vi 009 như cũ
- [x] T019 [P] [US1] Test tích hợp trong `tests/integration/test_api.py`: fork giả báo khối `lipsync` Ultralight → payload `lipsync` của API
  trạng thái avatar có khối và `model_mismatch`; fork giả cũ không gửi khối → `lipsync: null`, app vẫn chạy (SC-008);
  `/static/control.js` đọc `lipsync`, `model_mismatch` và có chuỗi "Model nhép miệng không khớp cấu hình" (kiểm tĩnh như
  `tests/integration/test_show_api.py`, cho T031)
- [x] T020 [P] [US1] Test báo cáo tổng duyệt trong `tests/unit/test_rehearsal.py`: báo cáo của phiên có dòng `lipsync_connected` ghi model,
  thầy, nhân vật (FR-009); phiên cũ không có khối → ghi "không rõ"

### Implement US1

- [x] T021 [US1] Viết `verify_live(character_dir, teacher, avatars_dir)` và `check_live_args(opt)` trong
  `vendor/livetalking/ailive_ext/ultralight.py` theo contracts/lipsync-selection.md §3 (thông báo `[ailive] ...` tiếng Việt, không nạp
  torch trước khi kiểm xong) (T010 xanh)
- [x] T022 [US1] Thêm tham số `--ailive_teacher` (choices `TEACHERS`, mặc định `musetalk`) có chú thích `# ailive:` trong
  `vendor/livetalking/config.py`
- [x] T023 [US1] Sửa khối chọn model trước `load_model` trong `vendor/livetalking/app.py`: thay dòng chặn "needs --model wav2lip" bằng
  `check_live_args`; nhánh
  `ultralight` + `--ailive_character` gọi `verify_live` **trước** `load_model`, dùng `avatar_id` suy ra, đặt `opt.ailive_lipsync`; nhánh
  wav2lip đặt khối `{model: wav2lip, teacher: null, ...}` (phụ thuộc T021, T022)
- [x] T024 [US1] Gửi khối `lipsync` trong `hello` và `/ailive/health`, cho `mouth_method_name()` trả `"ultralight"` với `LightReal` trong
  `vendor/livetalking/ailive_ext/ingest.py` (T011 xanh)
- [x] T025 [US1] Chỉ khi T012 đỏ: sửa `avatar_geometry` cho avatar kiểu `LightReal` trong `vendor/livetalking/ailive_ext/scene.py`
- [x] T026 [US1] Thêm nhánh model vào `scripts/livetalking/run.ps1` theo contracts/lipsync-selection.md §2: đọc hai biến (mặc định như
  `.env.example`), `ultralight` truyền `--model ultralight --ailive_character <AVATAR_DIR> --ailive_teacher <thầy> --batch_size
  <LIVETALKING_BATCH_SIZE>` (như nhánh Wav2Lip; số 16 của ADR-041 chọn cho Wav2Lip, T040 ghi lại số dùng cho Ultralight), bỏ
  `LIVETALKING_MOUTH_METHOD`, `LIVETALKING_LIP_EVERY_N`, `LIVETALKING_TRANSITION_S`, `LIVETALKING_HOLD_S` và in "bỏ qua cho ultralight:
  <tên>" khi chúng khác mặc định (research R8); giá trị khác dừng với "LIVETALKING_MODEL phải là wav2lip hoặc ultralight"; nhãn AI và
  ghi hình truyền như cũ (FR-004)
- [x] T027 [US1] Thêm hàm đọc bản ghi cài đặt và băm file model (gọi qua `asyncio.to_thread` ở nơi dùng) trong
  `src/ai_live/avatar/character.py` (T013 xanh; phụ thuộc T007)
- [x] T028 [US1] Trong `src/ai_live/avatar/livetalking_renderer.py` `_on_hello`: lưu khối `lipsync`, ghi vào dòng `lipsync_connected`, so với
  cấu hình và bản ghi cài đặt (T027), lệch → WARNING `lipsync_model_mismatch` + `model_mismatch=True`, không ngắt kết nối (T014 xanh;
  phụ thuộc T008)
- [x] T029 [US1] Thêm mục "Model nhép miệng" vào `src/ai_live/ops/readiness.py` ngay sau `check_character`: bước `model_not_supported`,
  `install_missing` (băm trong thread), so `model` với fork; chế độ `run_offline` ghi "chưa kiểm fork"; `check_character` bỏ kiểm clip khi
  nhân vật không có `"wav2lip"` (T015 xanh; phụ thuộc T027)
- [x] T030 [US1] Đưa `lipsync` và `model_mismatch` vào payload trạng thái avatar trong `src/ai_live/app/routes.py` (chỗ dùng
  `_lipsync_health`) (T019 xanh; phụ thuộc T008)
- [x] T031 [US1] Hiện dòng "Model: Ultralight · thầy MuseTalk · demo_host_02" / "Model: Wav2Lip · demo_host_01" / "Model: không rõ (fork cũ)"
  và băng đỏ "Model nhép miệng không khớp cấu hình" khi `model_mismatch` trong `src/ai_live/app/static/control.js` (thêm phần tử ở
  `src/ai_live/app/static/control.html` nếu cần) (contracts §7) (T019 xanh)
- [x] T032 [US1] Nhận `desk_top` ghi đè từ nhân vật trong `compute_layout` của `src/ai_live/scene/layout.py` (T016 xanh)
- [x] T033 [US1] Bỏ `_draw_desk` khi `desk_in_image` trong `src/ai_live/scene/render.py` (T017 xanh)
- [x] T034 [US1] Đọc khối `scene` của nhân vật đang dùng và truyền cho bố cục, vẽ trong `src/ai_live/scene/controller.py` (T018 xanh;
  phụ thuộc T007, T032, T033)
- [x] T035 [US1] Đọc khối `lipsync` từ dòng `lipsync_connected` và in model, thầy, nhân vật trong báo cáo tổng duyệt
  `src/ai_live/ops/rehearsal.py` (dùng phần đọc của `src/ai_live/director/session_log.py`) (T020 xanh)

### Chạy thật US1 (cần model Kaggle, T003)

- [x] T036 [GPU] [US1] Cài model: `.venv/Scripts/python -m ailive_ext.ultralight install <thư mục tải>/ultralight_out/demo_host_02/musetalk
  --video <video thầy MuseTalk>` → `vendor/livetalking/data/avatars/demo_host_02__ultralight_musetalk/` và `__w2l_musetalk/`, bằng chứng
  ở `assets/avatars/demo_host_02/ultralight/musetalk/` (quickstart §0.2)
- [x] T037 [US1] Mở 3 khung đầu trong `vendor/livetalking/data/avatars/demo_host_02__ultralight_musetalk/full_imgs/`: miệng khép chưa
  (research R6, FR-005)? Chưa thì cài lại với `--frames` nhỏ hơn; ghi kết quả vào mục R6 của `research.md`. Nếu chỉ `--start` mới sửa
  được thì dừng, báo người dùng (việc ngoài plan)
- [x] T038 [US1] Đo mép bàn trên khung gốc đã dựng, điền `scene.desk_top` vào `assets/avatars/demo_host_02/character.json`, ghi số vào mục R9
  của `research.md` (phụ thuộc T036)
- [x] T039 [GPU] [US1] Người dùng sửa `.env` (quickstart US1 bước 2), chạy `scripts/livetalking/run.ps1`: log fork có dòng kiểm bản ghi Đạt,
  `GET /ailive/health` có khối `lipsync`; chạy app, `uv run python -m ai_live.ops readiness` → mục "Model nhép miệng" OK; trang điều khiển
  hiện đúng dòng model (FR-001, FR-003, FR-009). Xong 2026-11-19: `/ailive/health` có khối `lipsync` (ultralight, thầy musetalk,
  `demo_host_02__ultralight_musetalk`, sha256 8276636d…), VRAM 2116 MB; readiness "Model nhép miệng" ĐẠT; trang điều khiển
  "Model: Ultralight · thầy MuseTalk · demo_host_02", không băng lệch. Log fork không có dòng "Đạt" riêng: kiểm bản ghi qua
  thì fork in `ailive_lipsync={...}` trong Namespace (sai thì fork thoát); sửa câu chữ ở T061
- [~] T040 [GPU] [US1] Show kịch bản 10 phút (1 sản phẩm chính + 2 phụ) trên `/host`: chụp ≥ 10 ảnh lúc chờ và lúc nói, đếm ảnh có nhãn
  "AI-GENERATED CONTENT" và ảnh có cảnh che mặt (SC-003, FR-004, FR-011); xem miệng khép lúc im lặng, không giật ở chỗ nối vòng khung
  (FR-005); `uv run python -m ai_live.ops report <session_id>` lấy `render_fps` p50 (chỉ số của SC-001), lặng p95, câu đầu, `avatar_first_frame`
  p50/p95 (so với ước tính +0,2 s của plan); ghi các số đó, `infer_fps`, `vram_peak_mb` từ `/ailive/health` và `LIVETALKING_BATCH_SIZE`
  đang dùng vào mục R7 của `research.md` (SC-001, SC-002). Phiên này là show B của US2. Chạy 2026-11-19 (show
  `073307fd…`, phiên `20261119-213243`, 621,5 s, chuỗi LLM + cảnh live): 14/14 ảnh có nhãn "AI-GENERATED CONTENT", 0/14 ảnh che
  mặt (thẻ sản phẩm chỉ che tay, phụ đề nằm dưới cằm), ảnh lúc nghỉ miệng khép; render_fps p50 25,13 (min 24,38), lặng p95
  0,047 s, câu đầu 2,36 s, 0 lỗi; số đầy đủ ở R7. **Còn lại:** người dùng xem bằng mắt chỗ nối vòng khung có giật không (FR-005);
  ảnh chụp không thấy được và show không có bản ghi video. Ảnh: `out/011_t040/`
- [ ] T041 [GPU] [US1] Với `.env` mặc định (Wav2Lip, `demo_host_01`, `LIVETALKING_MODEL` không đặt): show 2 phút, so câu đầu, lặng, nhãn với
  báo cáo tổng duyệt 007 trước feature (SC-008)

**Checkpoint:** US1 chạy và test độc lập được. Dừng lại, báo người dùng số SC-001/SC-002/SC-003, demo qua Meet.

---

## Phase 4: User Story 2: so sánh model riêng với Wav2Lip (P2)

**Mục tiêu:** một báo cáo có dòng kết luận theo từng ngưỡng ADR-060 mục 5 (không hạ ngưỡng) và gói xem mù, để người dùng quyết định model
cho buổi demo. Chạy ngay khi có model Kaggle (sửa ADR-066 mục 2, 2026-11-19).
**Kiểm thử độc lập:** quickstart US2: `lipsync-compare` trên dữ liệu giả cho đủ ba kết luận; trên số thật cho báo cáo chạy lại được.

### Test cho US2 (viết trước, phải FAIL trước khi implement)

- [x] T042 [P] [US2] Test trong `tests/unit/test_lipsync_compare.py` với `report.json` bộ đo giả (`summaries`, khối `sc001` của `ultralight`) và
  hai thư mục phiên giả: mọi ngưỡng đạt → "Đạt", mã thoát 0; `sc001.better` < 2, `sync_ok` false, `render_fps` p50 < 20, VRAM > 3584 MB,
  có lỗi, câu đầu > 5 s, lặng p95 > 1,5 s hoặc > 1,1 × A → "Chưa đạt", mã 1; thiếu số (VRAM, phiên < 10 phút) → "Thiếu số", mã 2; thư mục
  sai → mã 3; `conditions` lấy từ dòng `lipsync_connected`; `report.md` dòng đầu là kết luận, có đường dẫn `ab/PHIEU.md`; chạy hai lần cho
  cùng `mouth` (SC-004) (contracts/lipsync-compare.md §1–§4)
- [x] T043 [P] [US2] Test lệnh con `lipsync-compare` trong `tests/unit/test_ops_cli.py`: tham số `--mouth`, `--show-a`, `--show-b`, `--out` mặc
  định `out/011_compare`, nhận `session_id` hoặc thư mục phiên như lệnh `report` của 007

### Implement US2

- [x] T044 [US2] Viết `src/ai_live/ops/lipsync_compare.py`: đọc `report.json` của bộ đo 010, đọc hai phiên bằng `resolve_session_dir`,
  `last_show_id`, `load_show_logs`, `build_report` của 007 và `avatar.jsonl`; dựng `CompareReport` (data-model §6), danh sách ngưỡng cố
  định (contracts §3); ghi `out/011_compare/<ngày-giờ>/report.md` và `verdict.json` (T042 xanh)
- [x] T045 [US2] Thêm lệnh con `lipsync-compare` và mã thoát 0/1/2/3 vào `src/ai_live/ops/__main__.py` (T043 xanh; phụ thuộc T044).
  Xong 2026-11-19 (T042–T045): 50 test mới + 6 test CLI xanh, toàn bộ 2620 test xanh, ruff sạch. Cách hiểu đã chọn: VRAM lấy
  `vram_peak_mb` lớn nhất, không có thì `vram_used_mb` lớn nhất trong khung giờ của show (dòng health thật chỉ có `vram_used_mb`);
  "lỗi" = cảnh báo watchdog mức `operator` hoặc loại mất hình/tiếng + dòng `errors.jsonl` `vram_oom`/`renderer_restarted`;
  `--show-*` thử cả chuỗi làm đường dẫn trước rồi mới tách `:show_id` (đường dẫn Windows có dấu hai chấm); `verdict.json` có thêm
  `warnings`. Chạy thử trên dữ liệu thật (bộ đo `011_t046_r1`, phiên B làm cả A): Chưa đạt, mã 1, cảnh báo phiên A không phải wav2lip

### Chạy thật US2

- [x] T046 [GPU] [US2] Chạy bộ đo: `.venv/Scripts/python -m ailive_ext.mouth_eval --methods w2l,ultralight --avatar demo_host_02__w2l_musetalk
  --idle-avatar none --ab ultralight --clips` (≥ 27 câu bộ v2, FR-012, FR-013); chạy lại lần hai, so chỉ số hình miệng của hai lần (SC-004)
  (phụ thuộc T036). Xong 2026-11-19: `out/mouth/runs/011_t046_r1` (có `ab/PHIEU.md`), `011_t046_r2`; 27 câu. Hai lần trùng hết chỉ
  số hình miệng (SC-004 đạt; chỉ `render_fps` lệch ≤ 1,4). `sc001` của ultralight: **chưa đạt** (1/4 chỉ số tốt hơn: open_ratio +21 %;
  closure_recall −40 %, corr_open_loud −47 %, sharp_ratio −23 %; LSE-C 2,90 so với 5,91 của w2l, `sync_ok` false). render_fps 81
  so với 33, gpu_mb 1937 so với 2133. Lệnh trong bản viết thiếu `--clips` (không có thì `--ab` không làm gói xem mù), đã sửa
  quickstart/research/tasks
- [x] T047 [GPU] [US2] Show A: người dùng đặt `.env` cấu hình demo hiện tại (`LIVETALKING_MODEL=wav2lip`, `demo_host_01`,
  `LIVETALKING_MOUTH_METHOD=w2l`), show kịch bản 10 phút cùng sản phẩm, cùng máy với T040.
  Xong 2026-11-19: người dùng đồng ý đổi `.env` (bản cũ ở scratchpad), app chạy như T040 (`REPLY_ENGINE=chain`,
  `SCENE_ENABLED=true`). Show đầu bắt đầu trước khi tab `/host` nối fork 8 s nên bỏ, chạy lại: phiên `20261119-231008` show
  `2bb8807d…` 11,0 phút, kết thúc bình thường, 0 lỗi, VRAM 2656 MB, câu đầu 1,36 s, lặng p95 0,322 s. Log `out/011_t047/`
- [x] T048 [US2] Chạy `uv run python -m ai_live.ops lipsync-compare --mouth out/mouth/runs/<ngày-giờ> --show-a <phiên T047> --show-b <phiên
  T040>`; ghi kết luận và đường dẫn báo cáo vào `progress/LOG.md` và thẻ 011 trong `progress/FEATURES.md`, báo người dùng (phụ thuộc
  T040, T045, T046, T047). Xong 2026-11-19: **Chưa đạt** (mã 1), `out/011_compare/2026-11-19_23-22-39/`. Trượt
  `mouth_metrics` (1/4) và `lse_c` (2,896 so với 5,907); render_fps 25,13, VRAM 2120, 0 lỗi, câu đầu 2,36 s, lặng p95 0,047 s
  (≤ 1,1 × 0,322) đều Đạt. Phiên A không có `render_fps`/`mouth_method` trong khối health của Wav2Lip (bảng hiện —)
- [ ] T049 [US2] Người dùng: tìm ≥ 3 người chấm gói `ab/PHIEU.md` (không mở `ab_key.json` trước), ghi tỉ lệ chọn model riêng tự nhiên hơn
  (SC-005)
- [ ] T050 [US2] Chỉ khi T048 "Đạt" và người dùng đồng ý (FR-015, ADR-062): ghi ADR mới đổi cấu hình demo sang Ultralight thầy MuseTalk +
  `demo_host_02` trong `docs/DECISIONS.md`, sửa hướng dẫn `.env` demo trong `docs/RUNBOOK.md`; `demo_host_01` không lên live cùng tài
  khoản (FR-016). Chưa đạt → giữ Wav2Lip, ghi số vào ADR-066

**Checkpoint:** có báo cáo so sánh và gói xem mù; người dùng quyết định model cho buổi demo.

---

## Phase 5: User Story 3: đổi thầy dev / prod và chặn model sai (P3)

**Mục tiêu:** đổi thầy bằng một biến; mọi trường hợp sai (thiếu model, sai bằng chứng, sai nhân vật, thầy chưa cài, fork chạy model khác)
bị chặn trước show bằng lỗi tiếng Việt.
**Kiểm thử độc lập:** quickstart US3: các ca test không GPU xanh (SC-007), rồi hai ca thật trên laptop.

### Test cho US3 (viết trước, phải FAIL trước khi implement)

- [ ] T051 [P] [US3] Test trong `tests/unit/test_readiness.py`: `install_character_mismatch` (bản ghi của nhân vật khác, FR-008),
  `install_teacher_mismatch`, `checkpoint_mismatch` (file model bị đổi), `fork_model_mismatch` (fork báo `wav2lip` khi cấu hình `ultralight`;
  khác thầy, nhân vật hoặc sha256; thiếu khối khi cần); `infinitetalk` chưa cài → `install_missing` ở chế độ offline; `AVATAR_ID=demo_host_01`
  + `ultralight` → `model_not_supported`; cấu hình đúng → không báo lỗi nhầm (SC-007, FR-007)
- [ ] T052 [P] [US3] Test fork trong `vendor/livetalking/ailive_ext/tests/test_ultralight.py`: hai thầy cài song song (`__ultralight_musetalk`,
  `__ultralight_infinitetalk`) → `verify_live` chọn đúng theo thầy, không ghi đè nhau (FR-006); bản ghi của nhân vật khác đặt trong thư mục
  `demo_host_02` → từ chối (FR-008)
- [ ] T053 [P] [US3] Test tích hợp trong `tests/integration/test_readiness_api.py`: app chạy với fork giả báo model khác cấu hình → API kiểm tra
  trước demo trả LỖI `fork_model_mismatch` và payload trạng thái avatar có `model_mismatch: true`

### Implement US3

- [ ] T054 [US3] Thêm các bước `install_character_mismatch`, `install_teacher_mismatch`, `checkpoint_mismatch` và so đủ model, thầy, nhân vật,
  sha256 cho `fork_model_mismatch` vào mục "Model nhép miệng" trong `src/ai_live/ops/readiness.py`, thông báo theo data-model §5 (T051, T053
  xanh; phụ thuộc T029)
- [ ] T055 [US3] Chỉ khi T052 đỏ: sửa `verify_live` trong `vendor/livetalking/ailive_ext/ultralight.py`

### Chạy thật US3

- [ ] T056 [GPU] [US3] `.env` đổi `LIVETALKING_ULTRALIGHT_TEACHER=infinitetalk` (chưa cài), chạy `scripts/livetalking/run.ps1` → fork thoát
  ngay với thông báo tiếng Việt, không nạp HuBERT; đổi lại `musetalk`
- [ ] T057 [GPU] [US3] Đổi `.env` sang `wav2lip` mà không bật lại fork Ultralight → `readiness` báo LỖI `fork_model_mismatch`, trang điều khiển
  băng đỏ (Q36); bật lại fork → OK. Bấm giờ đổi Wav2Lip ↔ Ultralight cả hai chiều: ≤ 2 phút, không sửa code (SC-006). Đổi thầy dev ↔ prod chưa bấm giờ được vì chưa
  có model thầy prod (ADR-066); ghi "chờ model prod" vào thẻ 011

**Checkpoint:** mọi trường hợp sai bị chặn; đổi model trong ≤ 2 phút.

---

## Phase 6: Hoàn thiện và việc chung

- [ ] T058 [P] Thêm mục "Đổi model nhép miệng" vào `docs/RUNBOOK.md`: đổi Wav2Lip ↔ Ultralight và thầy, bật lại fork, mục "Model nhép miệng"
  của kiểm tra trước demo; Ultralight chậm hoặc lỗi giữa show → bật lại fork với `LIVETALKING_MODEL=wav2lip`, không tự đổi (FR-014,
  research R11)
- [ ] T059 [P] Ghi khối `lipsync` trong `hello`/health, trường `LipsyncHealth.lipsync`, `model_mismatch` và `LIVETALKING_MODEL` chọn model trong
  fork vào mục LiveTalking của `docs/ARCHITECTURE.md` (contracts/lipsync-selection.md "Khác với ARCHITECTURE")
- [ ] T060 [P] Ghi khối `lipsync` tùy chọn của `hello` vào `specs/005-lipsync-livetalking/contracts/fork-protocol.md` §1 (dạng "thêm bởi 011,
  ADR-067")
- [ ] T061 Sửa `quickstart.md` nếu các bước chạy thật (T036–T057) khác bản viết; xóa các `TODO:` đã trả lời trong mục "Câu còn mở" của
  `research.md`
- [ ] T062 `uv run pytest`, `uv run ruff check .`, `uv run ruff format --check .` và `.venv/Scripts/python -m pytest ailive_ext/tests` (trong
  `vendor/livetalking`) đều sạch (SC-007, SC-008)
- [ ] T063 Chạy `/update-context`

## Phụ thuộc và thứ tự

- Setup → Foundational → US1 → US2 → US3 → Hoàn thiện. US3 (phần test và T054) làm được ngay sau T029, song song với phần chạy thật của US1.
- Phần code của US1, US2, US3 không cần model; phần "Chạy thật" chờ T003 (Kaggle xong) và T036.
- T007 → T027 → T028, T029; T008 → T028, T030; T021 + T022 → T023; T032 + T033 → T034; T044 → T045; T029 → T054.
- T036 → T037, T038 → T039 → T040; T040 + T046 + T047 + T045 → T048 → T049, T050.
- T025, T055 chỉ làm khi test tương ứng đỏ; T050 chỉ làm khi người dùng đồng ý.

## Chạy song song

- Setup: T001, T002.
- Foundational: T004, T005, T008, T009 (rồi T006 → T007).
- Test US1: T010–T020 (mỗi task một file; T013 và T005 cùng `test_character.py` nên T013 sau T005).
- Fork và app của US1: nhóm fork (T021–T025) song song với nhóm app (T027–T035) và T026.
- Test US2 (T042, T043) và test US3 (T051–T053) làm cùng lúc với phần chạy thật của US1.

## Đợt GPU

Tất cả chạy trên GPU laptop GTX 1650 Ti (ADR-023). Không dùng RunPod, không chi tiền. Gom thành hai buổi để tránh nạp lại model nhiều lần:

- **Buổi 1 (khi Kaggle xong):** T036 → (T037, T038 không GPU) → T039 → T040 → T046.
- **Buổi 2:** T047 (show A Wav2Lip), T041 (show 2 phút mặc định), T056, T057.

## Chiến lược MVP

1. Setup + Foundational → 2. US1 (code + test không GPU, rồi Buổi 1 GPU) → **dừng, báo số SC-001/002/003, demo qua Meet** →
3. US2 ngay sau đó (không chờ cả project xong) → người dùng quyết định model demo → 4. US3, Hoàn thiện.

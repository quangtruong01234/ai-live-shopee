# Nghiên cứu (Phase 0): 011-ultralight-live-lipsync

- **Ngày:** 2026-11-19 · **Plan:** [plan.md](./plan.md)
- Nguồn chính là mã fork đã ghim (`vendor/livetalking`, ADR-060) và mã app hiện có; không cần tài liệu ngoài.

## R1. Chọn model nhép miệng bằng biến môi trường

- **Decision:** hai biến mới, đọc ở cả app (`core/config.py`) và `scripts/livetalking/run.ps1`:
  - `LIVETALKING_MODEL=wav2lip|ultralight`, mặc định `wav2lip`.
  - `LIVETALKING_ULTRALIGHT_TEACHER=musetalk|infinitetalk`, mặc định `musetalk` (ADR-066). Chỉ có nghĩa khi model là `ultralight`.
  - Nhân vật vẫn chọn bằng `CUSTOMER_ID` / `AVATAR_ID` / `AVATAR_DIR` như 005; không thêm biến nhân vật mới.
  - App từ chối bật với giá trị lạ (lỗi cấu hình tiếng Việt khi khởi động, như các biến khác của `pydantic-settings`).
- **Rationale:** ADR-064 mục 4 đã định "chọn model khi live bằng biến môi trường". `run.ps1` đã đọc `.env` để ghép tham số fork
  (`LIVETALKING_MOUTH_METHOD`, `LIVETALKING_BATCH_SIZE`...), nên app và fork dùng chung một nguồn cấu hình. Mặc định giữ Wav2Lip đúng
  FR-002 và ADR-062.
- **Alternatives considered:**
  - Một biến gộp `LIVETALKING_MODEL=ultralight_musetalk`: ít biến hơn nhưng phải tách chuỗi, và khó thêm thầy khác.
  - Ghi model vào `character.json`: model là lựa chọn lúc chạy, còn `character.json` mô tả nhân vật; đổi model không được phải sửa
    dữ liệu nhân vật. `character.json` chỉ khai model **dùng được** (R4).
  - Chọn trên trang điều khiển: đổi giữa show bị loại bởi FR-014, và fork phải bật lại để nạp model khác.

## R2. Cách fork bật Ultralight cho một nhân vật

- **Decision:**
  - `run.ps1` với `LIVETALKING_MODEL=ultralight` chạy `app.py --model ultralight --ailive_character <AVATAR_DIR> --ailive_teacher <thầy>`.
  - `app.py` dòng 146 hiện từ chối `--ailive_character` nếu không phải `wav2lip`. Đổi thành:
    - `wav2lip`: như cũ (thư viện clip của 005).
    - `ultralight`: không dựng thư viện clip. Đọc `character_id` là tên thư mục nhân vật, suy ra
      `avatar_id = ailive_ext.ultralight.ultralight_avatar_id(character_id, teacher)` (đã có: `<nhân vật>__ultralight_<thầy>`), gọi
      `verify_live()` (R5) rồi mới `load_avatar(avatar_id)`.
    - Model khác (`musetalk`...) với `--ailive_character`: vẫn từ chối như cũ.
  - Tham số `--ailive_teacher` thêm vào `config.py` của fork bằng một móc `# ailive:` như `--ailive_character`.
- **Rationale:** đường `--model ultralight` gốc (`app.py` dòng 182–185) đã nạp model, avatar và chạy `warm_up`; chỉ cần đặt đúng
  `avatar_id` và chặn trước khi nạp. Tên avatar suy từ nhân vật + thầy nên người vận hành không gõ tay tên thư mục (US3, chặn nhầm).
- **Alternatives considered:**
  - Truyền thẳng `--avatar_id demo_host_02__ultralight_musetalk`: dễ gõ nhầm, fork không biết nhân vật/thầy để kiểm.
  - Làm thư viện clip cho Ultralight: ngoài phạm vi spec; Ultralight chỉ có một vòng khung gốc.

## R3. Báo cáo model đang chạy

- **Decision:**
  - `hello` (005 fork-protocol §1) và `GET /ailive/health` của fork thêm khối tùy chọn
    `lipsync: {model, teacher, character_id, avatar_id, checkpoint_sha256}`; với Wav2Lip `teacher` và `checkpoint_sha256` là `null`.
  - `ingest.mouth_method_name()` trả `"ultralight"` cho avatar `LightReal` (hiện trả `None` vì chỉ avatar wav2lip có
    `ailive_infer_faces`). Nhờ vậy cột "Miệng" trong `/api/latency`, `avatar.jsonl` và trang điều khiển hiện đúng (FR-009, FR-010) mà
    không đổi định dạng.
  - App ghi khối `lipsync` vào bản ghi phiên (sự kiện `avatar_connected` sẵn có) và hiện "Model: Ultralight (thầy MuseTalk) ·
    demo_host_02" trên trang điều khiển.
- **Rationale:** kiểm tra trước demo cần biết fork **thật sự** chạy gì, không chỉ app cấu hình gì (FR-007, Q36). Khối tùy chọn nên app
  cũ và fork cũ vẫn nói chuyện được (tương thích ngược).
- **Alternatives considered:** endpoint riêng `/ailive/lipsync` (thêm một lần gọi, không có gì hơn health); đọc log fork (không có cấu trúc).

## R4. `character.json` cho nhân vật không có thư viện clip

- **Decision:**
  - Thêm trường tùy chọn `lipsync_models: list[str]`, mặc định `["wav2lip"]` khi thiếu (giữ nguyên `demo_host_01`).
  - Yêu cầu "ít nhất một clip idle và một clip talk" (`kind_missing`) và `prepare.status == "ready"` chỉ áp dụng khi `"wav2lip"` có trong
    danh sách. Nhân vật chỉ Ultralight được để `clips: []` và không có `prepare`.
  - `validate_for_session` thêm kiểm: `LIVETALKING_MODEL` phải nằm trong `lipsync_models`, nếu không thì lỗi
    `model_not_supported` (vd. `demo_host_01` + `ultralight`, FR-008). Kiểm khách (`customer_id`) và tên nhân vật giữ nguyên.
  - Tạo `assets/avatars/demo_host_02/character.json` khi triển khai: `customer_id` của khách demo (ADR-066), `face` trỏ `face.png`,
    `clips: []`, `lipsync_models: ["ultralight"]`, `provenance` lấy từ `provenance.json` sẵn có, `scene` theo R9.
- **Rationale:** dùng lại `load_character` / `validate_for_session` đang gắn vào `avatar/factory.py` thay vì làm đường đọc thứ hai.
  Mặc định `["wav2lip"]` không đổi hành vi nhân vật cũ.
- **Alternatives considered:** bỏ `character.json` cho Ultralight, chỉ đọc bản ghi cài đặt: mất kiểm khách / một host một tài khoản
  (ràng buộc 3) mà 005 đã có.

## R5. Kiểm bản ghi cài đặt (app và fork)

- **Decision:**
  - Bản ghi do `ailive_ext.ultralight install` viết (`ultralight_install.json`): `character_id`, `teacher`, `checkpoint.{file,sha256}`,
    `fork_commit`, `frames`, `avatars`, `video.sha256`, `installed_at`. Một bản trong `vendor/livetalking/data/avatars/<avatar_id>/`, một bản
    trong `assets/avatars/<nhân vật>/ultralight/<thầy>/` cùng file model và bằng chứng (`provenance_train.json`, `teacher_run.json`,
    `loss.png`, ...).
  - **Fork** (`verify_live`, lúc bật): bản ghi trong `data/avatars/<avatar_id>/` tồn tại; `character_id`, `teacher` khớp tham số;
    `sha256(data/avatars/<avatar_id>/ultralight.pth)` bằng `checkpoint.sha256`. Sai thì `SystemExit` với thông báo tiếng Việt nêu rõ
    thiếu gì (FR-007).
  - **App** (kiểm tra trước demo và lúc bắt đầu phiên): bản ghi trong `<AVATAR_DIR>/ultralight/<thầy>/` tồn tại; `character_id`, `teacher`
    khớp; file model trong thư mục bằng chứng có sha256 bằng bản ghi (băm trong thread, ~49 MB, một lần mỗi lần kiểm); khối `lipsync` fork
    báo (R3) có `model`, `teacher`, `character_id`, `checkpoint_sha256` khớp. Sai bất kỳ mục nào là **LỖI** (SC-007).
  - Mã lỗi: `install_missing`, `install_character_mismatch`, `install_teacher_mismatch`, `checkpoint_mismatch`, `fork_model_mismatch`,
    `model_not_supported` (chi tiết ở [contracts/lipsync-selection.md](./contracts/lipsync-selection.md)).
- **Rationale:** app chỉ thấy `assets/`, fork chỉ thấy `data/avatars/`; mỗi bên chặn phần của mình (xem "Theo dõi độ phức tạp" trong
  plan). Sha256 của file model là bằng chứng không nhầm thầy dev/prod (US3).
- **Alternatives considered:** chỉ so tên file model (`best.pth`): hai thầy có thể cùng tên; so `installed_at`: không chứng minh nội dung.

## R6. Hình lúc im lặng (FR-005)

- **Decision:** lúc im lặng fork phát vòng khung gốc tới–lùi (`frame_list_cycle`, `mirror_index`) như mọi avatar LiveTalking; 011 không
  thêm clip nền. Quickstart US1 kiểm bằng mắt và bằng điểm `silence_closed` của bộ đo 010 rằng miệng khép lúc im lặng.
- **Rationale:** `install` lấy N khung đầu của video thầy (`inputs.frames` của `teacher_run.json`); video thầy dựng từ bộ câu nên đoạn đầu
  có thể đang nói.
- **Đo (2026-11-19, T037):** cài từ video thầy `demo_host_02_musetalk_train_v1.mp4` với N = 81 (`teacher_run.json` `inputs.frames`).
  Khung 0, 1, 2 (và 3) miệng khép, môi chạm nhau, cười nhẹ; khung 20 và 80 cũng khép, khung 40 hé, khung 60 nhắm mắt (chớp mắt của khung
  gốc). Không cần `--frames` nhỏ hơn hay `--start`. Điểm `silence_closed` đo ở T046.

## R7. Tốc độ và VRAM trên GTX 1650 Ti

- **Decision:** đo, không đoán. Cổng đo là show kịch bản 10 phút (SC-001): `infer_fps` và `vram_peak_mb` trong `/ailive/health`
  (đã có từ 005/010), `render_fps` của bộ đo 010. Chưa đạt thì giữ Wav2Lip (ADR-062) và ghi số vào báo cáo so sánh.
  Các nút có thể vặn nếu thiếu tốc độ, **không làm trong 011 trừ khi đo thấy cần**: `LIVETALKING_BATCH_SIZE`, HuBERT `.half()` (đang tắt
  trong `ultralight_avatar.py`), trích đặc trưng HuBERT trên CPU.
- **Rationale:** ADR-060 chỉ đo tiền xử lý trên laptop (HuBERT ~12 s cho 13 s tiếng ở chế độ một lần), không phải chạy luồng; HuBERT
  luồng chạy theo khối nhỏ `[4,4]` nên số đó không suy ra được tốc độ live.
- **Kết quả đo (T040, 2026-11-19, GTX 1650 Ti 4 GB, `LIVETALKING_BATCH_SIZE=16` mặc định của `.env.example`, HuBERT fp32):**
  show kịch bản 621,5 s (show `073307fd…`, phiên `20261119-213243`), 155 câu, 0 lỗi giọng/hình, 0 lần rơi về ảnh tĩnh.
  - `render_fps` p50 25,13, min 24,38 (155 lượt): đủ 25 fps, SC-001 đạt cho 10 phút.
  - `infer_fps` (`/ailive/health`, 63 mẫu mỗi 10 s): min 97,1, p50 109,0, max 118,5, dư khoảng 4 lần so với 25 fps.
  - VRAM: 2116 MB lúc khởi động, đỉnh 2120 MB, không tăng trong suốt show.
  - Lặng giữa câu: p50 0,016 s, p95 0,047 s, max 0,109 s (154 khoảng), 0 khoảng > 5 s. Câu đầu của show 2,36 s
    (`llm_first_sentence` 0,875 s, `tts_first_chunk` 1,188 s, `avatar_first_frame` 2,36 s).
  - `avatar_first_frame` theo từng câu (tính từ `segment_requested`): p50 30,3 s, p95 44,1 s. Số này **không so được** với ước tính
    +0,2 s của plan, vì đạo diễn xin đoạn trước nên số gồm cả thời gian xếp hàng chờ câu trước nói xong (từ `tts_first_chunk` đến
    khung đầu p50 9,5 s cũng là thời gian chờ). Số so được là câu đầu của show (2,36 s, hàng đợi trống).
  - Kết luận: không cần vặn nút nào (batch, `.half()`, HuBERT trên CPU); giữ mặc định.

## R8. Các biến fork chỉ dành cho Wav2Lip

- **Decision:** với `LIVETALKING_MODEL=ultralight`, `run.ps1` không truyền `LIVETALKING_MOUTH_METHOD`, `LIVETALKING_LIP_EVERY_N`,
  `LIVETALKING_TRANSITION_S`, `LIVETALKING_HOLD_S` (đều gắn với wav2lip hoặc thư viện clip) và in một dòng "bỏ qua cho ultralight" nếu
  chúng khác mặc định. Kiểm tra trước demo không đổi.
- **Rationale:** đã kiểm mã: `ailive_lip_every_n` đọc trong `base_avatar` nhưng chỉ `wav2lip_avatar.py` dùng (`infer_every_n`); phương
  pháp miệng 010 gắn vào `ailive_infer_faces` chỉ avatar wav2lip có; thời gian chuyển clip thuộc bộ lập lịch clip. Không có tác dụng với
  `LightReal`, nên báo rõ thay vì để người vận hành tưởng đang dùng.
- **Alternatives considered:** làm lip-skip cho Ultralight: chưa cần trước khi có số R7.

## R9. Cảnh live cho nhân vật có sẵn bàn (FR-011)

- **Decision:**
  - `character.json` thêm khối tùy chọn `scene: {desk_in_image: bool = false, desk_top: float | null}`. `desk_top` là tỉ lệ chiều cao
    khung (0,55–0,92 như `layout.compute_layout`) của mép trên mặt bàn trong ảnh.
  - Khi `desk_in_image` là true, cảnh 009 không vẽ lớp bàn (`render._draw_desk` bỏ qua), dùng `desk_top` của nhân vật thay
    `scene.json` `layout.desk_top`, thẻ sản phẩm vẫn đứng trên mép đó; kiểm "bàn không chạm mặt" giữ nguyên.
  - Đo khung của fork: `ailive_ext.scene.avatar_geometry` đã có nhánh không thư viện clip đọc `frame_list_cycle` và `coord_list_cycle`;
    `LightReal` có đúng hai thuộc tính này (`ultralight_avatar.py` dòng 138), nên `state_of` chạy được. Test fork thêm một ca avatar giả
    kiểu `LightReal`.
- **Rationale:** `demo_host_02/provenance.json` ghi ảnh có sẵn bàn; vẽ thêm bàn sẽ chồng hai bàn. Khai trên nhân vật vì bàn thuộc ảnh
  nhân vật, không thuộc cảnh.
- **Alternatives considered:** tự dò mép bàn bằng xử lý ảnh (thừa cho một nhân vật, dễ sai); sửa `scene.json` của demo (cảnh dùng chung
  cho nhân vật khác).
- **Đo (2026-11-19, T038):** khung gốc `full_imgs/00000000.png` 480×832. Mép trên mặt bàn gỗ ở dòng ≈ 647–650 (đáy dải bóng tối ngay
  trên mặt bàn, đo theo độ sáng cột x 70–110 và 340–380; khung 40, 80 trùng vì nền đứng yên). `desk_top = 0.78` (649 px), nằm trong
  [0,55; 0,92] và xa vùng mặt (cằm ≈ 330 px); `load_character` nhận số này.

## R10. So sánh với Wav2Lip và kết luận (US2)

- **Decision:**
  - **Khẩu hình:** dùng nguyên bộ đo 010 trong venv fork:
    `python -m ailive_ext.mouth_eval --methods w2l,ultralight --avatar demo_host_02__w2l_musetalk --idle-avatar none --ab ultralight --clips`.
    Bộ đo đã suy `__ultralight_musetalk`, đã tính khối `sc001` so với đường gốc `w2l` (`better` = số chỉ số hình miệng tốt hơn ≥ 15%,
    `sync_ok` = LSE-C không thấp hơn) vào `out/mouth/runs/<ngày-giờ>/report.json`, và làm gói xem mù (`ab/PHIEU.md`, `ab_key.json`).
    So trên **cùng nhân vật** (`demo_host_02__w2l_*` dựng từ cùng khung) để chỉ khác model.
  - **Show:** hai show kịch bản 10 phút cùng sản phẩm, cùng máy, một `LIVETALKING_MODEL=wav2lip` (`demo_host_01`, cấu hình demo hiện tại
    ADR-062) và một `ultralight` (`demo_host_02`).
  - **Gộp:** lệnh mới ở app `uv run python -m ai_live.ops lipsync-compare --mouth <thư mục bộ đo> --show-a <phiên wav2lip> --show-b <phiên
    ultralight>` đọc `report.json` của bộ đo và bản ghi hai phiên (dùng lại phần đọc của báo cáo tổng duyệt 007), viết
    `out/011_compare/<ngày-giờ>/report.md` + `verdict.json`. Mỗi ngưỡng ADR-060 mục 5 một dòng Đạt/Chưa đạt/Thiếu số; kết luận chung
    "Đạt" chỉ khi mọi dòng Đạt. Chi tiết ở [contracts/lipsync-compare.md](./contracts/lipsync-compare.md).
- **Rationale:** không làm lại bộ đo; số show nằm trong bản ghi phiên của app. Người dùng muốn đánh giá ngay khi model Kaggle xong (ADR-066 mục 2, sửa 2026-11-19), nên
  báo cáo phải tự đứng được, chạy lại được.
- **Alternatives considered:** so `demo_host_02` Wav2Lip với `demo_host_02` Ultralight trong show: `demo_host_02` không có thư viện clip,
  show Wav2Lip của nó không phải cấu hình demo thật; khẩu hình đã so cùng nhân vật ở bộ đo.

## R11. Canh show và nối lại (FR-013, FR-014)

- **Decision:** không đổi. Watchdog 007 và nối lại 005 đọc `hello`/health như cũ; Ultralight lỗi giữa show thì báo động và theo
  RUNBOOK (về Wav2Lip là bật lại fork với `LIVETALKING_MODEL=wav2lip`, không tự đổi). Nối lại sau khi fork bật lại kiểm lại khối `lipsync`.
- **Rationale:** FR-014 cấm tự đổi model giữa show; giao thức không đổi.
- **Alternatives considered:** tự rơi về Wav2Lip khi Ultralight lỗi: hai model khác nhân vật (`demo_host_01` vs `demo_host_02`) nên tự
  đổi sẽ đổi mặt host giữa show (P2, ràng buộc 3).

## Câu còn mở (TODO)

| # | Câu hỏi | Trả lời khi |
|---|---------|-------------|
| R7 | `infer_fps` p50 và VRAM đỉnh của Ultralight trong show 10 phút trên laptop? | Quickstart US1 bước 5 |

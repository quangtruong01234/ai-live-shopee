# Kế hoạch triển khai: Host AI nhép miệng bằng model riêng của nhân vật (Ultralight) trong show live

- **Feature ID:** `011-ultralight-live-lipsync` · **Ngày:** 2026-11-19 · **Spec:** [spec.md](./spec.md)
- **Đầu vào:** spec đã làm rõ (Clarified 2026-11-19, ADR-066)
- **Ghi chú:** model dev (thầy MuseTalk) đang huấn luyện trên Kaggle (`ai-host-train-ultralight-demo-host-02` version 3). Phần chạy được
  không cần model (test, cấu hình, kiểm tra trước demo) làm trước; phần cần model và GPU (show 10 phút, so sánh) làm khi tải model về.

## Tóm tắt

Fork LiveTalking đã có đường suy luận `--model ultralight` (class `LightReal`, HuBERT + UNet 160 px), và công cụ
`python -m ailive_ext.ultralight install` đã dựng avatar `demo_host_02__ultralight_<thầy>` kèm bản ghi `ultralight_install.json`. Còn
thiếu ba thứ để chạy trong show thật:

1. **Chọn model bằng biến môi trường** `LIVETALKING_MODEL=wav2lip|ultralight` (mặc định `wav2lip`) và
   `LIVETALKING_ULTRALIGHT_TEACHER=musetalk|infinitetalk` (mặc định `musetalk`). App và `scripts/livetalking/run.ps1` đọc cùng hai biến.
   Fork nhận `--ailive_character <thư mục nhân vật> --ailive_teacher <thầy>`, tự suy ra tên avatar và **từ chối bật** nếu bản ghi cài đặt
   không khớp nhân vật, thầy hoặc mã kiểm tra file model.
2. **Báo cáo và chặn sai:** `hello` và `/ailive/health` của fork thêm khối `lipsync` (model, thầy, nhân vật, sha256 model). App ghi khối này
   vào bản ghi phiên và trang điều khiển; kiểm tra trước demo (007) báo **LỖI** khi model thiếu, sai bằng chứng, sai nhân vật, thầy chưa
   cài, hoặc fork đang chạy model khác cấu hình của app. `character.json` khai các model nhân vật dùng được (`lipsync_models`), nên
   `demo_host_02` không cần thư viện clip của 005.
3. **Cảnh live cho nhân vật có sẵn bàn:** `character.json` khai `scene.desk_in_image` và `scene.desk_top`; cảnh 009 bỏ lớp bàn, sản phẩm
   đứng trên mép bàn trong ảnh.

US2 dùng lại bộ đo 010 (`mouth_eval --methods w2l,ultralight`, đã có phép so với đường gốc `sc001` và gói xem mù) và thêm lệnh
`uv run python -m ai_live.ops lipsync-compare` gộp số bộ đo với số hai show 10 phút (tốc độ khung, VRAM đỉnh, lỗi, câu đầu, lặng p95)
thành một báo cáo có dòng kết luận theo từng ngưỡng ADR-060 mục 5. Không đổi giao thức WebSocket nói câu, không đổi Protocol nào của app.

## Bối cảnh kỹ thuật

- **Ngôn ngữ / phiên bản:** Python 3.12 (app, uv). Fork dùng venv riêng `vendor/livetalking/.venv` (Python 3.12, torch 2.9.1+cu128,
  torchaudio 2.9.1 ghim theo ADR-060).
- **Phụ thuộc chính:** như 005/010. HuBERT `facebook/hubert-large-ls960-ft` (đã tải 2026-11-17, ADR-060) và mã Ultralight ghim
  `ff0454d` đã có trong fork. **Phụ thuộc MỚI cần duyệt: không có.** Không tải model mới (model dev là đầu ra Kaggle của chính dự án).
- **Lưu trữ (ngoài git):** model và bằng chứng ở `assets/avatars/demo_host_02/ultralight/<thầy>/`; avatar của fork ở
  `vendor/livetalking/data/avatars/demo_host_02__ultralight_<thầy>/`; báo cáo so sánh ở `out/011_compare/<ngày-giờ>/`.
  `assets/avatars/demo_host_02/character.json` mới (theo `.gitignore` hiện tại của `assets/avatars/`).
- **Kiểm thử:** pytest app (không GPU: fork giả gửi khối `lipsync`, thư mục nhân vật và bản ghi cài đặt dựng trong `tmp_path`); pytest
  fork (`ailive_ext/tests`, không GPU: bản ghi cài đặt và file model giả, không gọi `LightReal.inference_batch`). Show 10 phút và bộ đo
  chạy trên GPU laptop, không nằm trong pytest.
- **Nơi chạy:** GPU laptop GTX 1650 Ti 4 GB (ADR-023). Không RunPod.
- **Adapter liên quan:** `AvatarRenderer` LiveTalking chỉ đọc thêm khối `lipsync` từ `hello`. `LIVETALKING_MODEL` chọn model **bên trong
  fork**, không phải adapter mới của app (Điều IV: không đổi lõi pipeline).
- **Mục tiêu hiệu năng:** `render_fps` p50 ≥ 20 (cổng của SC-001, contracts/lipsync-compare.md §3; `infer_fps` chỉ ghi để chẩn
  đoán), VRAM đỉnh ≤ 3,5 GB, 0 lỗi trong show 10 phút (SC-001); câu đầu ≤ 5 s, lặng
  p95 không quá +10% so với Wav2Lip cùng máy (SC-002).
- **Ràng buộc khác:** nhãn AI vẽ trong `base_avatar` cho mọi model (FR-004); không tự đổi model giữa show (FR-014); mặc định giữ Wav2Lip +
  `demo_host_01` (FR-002, ADR-062, ADR-066).

## Kiểm tra Constitution (cổng)

| Điều | Kết quả | Ghi chú |
|------|---------|---------|
| I. Realtime, nhãn AI, 1 host 1 tài khoản | Đạt | Miệng sinh lúc phát từ tiếng TTS từng câu; video thầy chỉ là dữ liệu huấn luyện, nền là vòng khung gốc chạy tới–lùi như clip nền của 005. Nhãn AI và watermark vẽ trong `base_avatar` sau cảnh, chung mọi model. Fork từ chối model của nhân vật khác (bản ghi cài đặt), app từ chối nhân vật của khách khác (`validate_for_session` như 005) |
| II. Đồng ý và bảo mật | Đạt | `demo_host_02` là mặt AI (ADR-060), giọng VieNeu có sẵn; model, khung hình, video thầy, báo cáo ngoài git |
| III. Trả lời có căn cứ | N/A | Không đổi nội dung câu nói |
| IV. Adapter trước | Đạt | Model chọn bằng env; mặc định `wav2lip` đi đúng đường cũ; không đổi Protocol, không đổi lõi pipeline |
| V. Test trước | Đạt | Test không GPU cho cấu hình, `character.json` mới, kiểm bản ghi cài đặt (app và fork), kiểm tra trước demo, cảnh không bàn, lệnh so sánh |
| VI. Ngân sách độ trễ | Đạt có điều kiện | Không thêm bước trên đường tiếng. Tốc độ HuBERT-large + UNet trên GPU 4 GB **chưa đo trong live** (research R7); show 10 phút là cổng đo, chưa đạt thì giữ Wav2Lip (ADR-062) |
| VII. Đơn giản trước | Đạt | Không phụ thuộc mới; không làm thư viện clip cho Ultralight (ngoài phạm vi); lệnh so sánh dùng lại bộ đo 010 và đọc bản ghi phiên có sẵn |
| VIII. Quan sát được | Đạt | Khối `lipsync` trong `hello`, `/ailive/health`, bản ghi phiên, `/api/latency` (`mouth_method=ultralight`), trang điều khiển, kiểm tra trước demo |
| IX. Ngôn ngữ và tài liệu | Đạt | Code tiếng Anh; thông báo lỗi, báo cáo, tài liệu tiếng Việt |

Kiểm lại sau Phase 1 (thiết kế xong): vẫn Đạt; Điều VI giữ "Đạt có điều kiện" tới khi có số show 10 phút.

## Ảnh hưởng ngân sách độ trễ

| Khâu | Ngân sách (ARCHITECTURE §4) | Feature này thay đổi gì | Cách đo |
|------|-----------------------------|-------------------------|---------|
| Tạo hình mỗi khung | ~40 ms/khung (25 fps) | Thay wav2lip256 bằng HuBERT-large (đặc trưng tiếng, GPU) + UNet 160 px; dán ảnh 160→hộp mặt. Chưa đo trong live (R7) | `infer_fps` trong `/ailive/health`, `render_fps` của bộ đo, show 10 phút |
| Khung đầu sau câu (`avatar_first_frame`) | trong 5 s câu đầu | HuBERT cần ngữ cảnh `audio_feat_length=[4,4]` (8 khung đặc trưng) trước khung đầu; dự kiến ≤ +0,2 s, chưa đo | `avatar_first_frame` p50/p95 trong bảng độ trễ của show 10 phút (T040) |
| Câu đầu show kịch bản | ≤ 5 s | Không đổi đường LLM/TTS | `/api/latency`, show 10 phút |
| Lặng giữa câu | p95 ≤ 1,5 s | Không đổi `LIVETALKING_LEAD_S`; giới hạn SC-002 ≤ +10% so với Wav2Lip | show 10 phút mỗi model, lệnh `lipsync-compare` |
| Bật fork | ngoài show | Nạp HuBERT 1,26 GB + avatar; kiểm sha256 model (~49 MB) một lần | log fork, kiểm tra trước demo |

## Cấu trúc mã nguồn

### Tài liệu của feature
```
specs/011-ultralight-live-lipsync/
├── spec.md · plan.md · research.md · data-model.md · quickstart.md
└── contracts/
    ├── lipsync-selection.md   # biến env, tham số fork, khối `lipsync` trong hello/health, mã lỗi, kiểm tra trước demo
    └── lipsync-compare.md     # lệnh so sánh, đầu vào, báo cáo, kết luận theo ngưỡng
```

### Mã nguồn
```
vendor/livetalking/app.py                              # nhận --ailive_teacher; ultralight + --ailive_character → kiểm bản ghi, không nạp thư viện clip
vendor/livetalking/ailive_ext/ultralight.py            # verify_live(): đọc bản ghi cài đặt, so nhân vật/thầy/sha256; tên avatar
vendor/livetalking/ailive_ext/ingest.py                # khối `lipsync` trong hello và health; mouth_method "ultralight"
vendor/livetalking/ailive_ext/scene.py                 # (nếu cần) đo khung cho LightReal (research R9)
vendor/livetalking/ailive_ext/tests/test_{ultralight,ingest,scene}.py
scripts/livetalking/run.ps1                            # đọc LIVETALKING_MODEL, LIVETALKING_ULTRALIGHT_TEACHER, ghép tham số fork
.env.example                                           # hai biến mới
src/ai_live/core/config.py                             # livetalking_model, livetalking_ultralight_teacher + kiểm hợp lệ
src/ai_live/avatar/character.py                        # lipsync_models, scene.desk_in_image/desk_top, đọc bản ghi cài đặt, validate_for_session theo model
src/ai_live/avatar/livetalking_renderer.py             # đọc khối `lipsync` của hello, so với cấu hình
src/ai_live/ops/readiness.py                           # mục "Model nhép miệng" (LỖI/OK) và so fork ↔ cấu hình
src/ai_live/scene/{controller,layout,render}.py        # bỏ lớp bàn khi nhân vật có bàn; desk_top của nhân vật
src/ai_live/director/session_log.py, app/static/control.js   # ghi và hiện model/thầy/nhân vật (FR-009)
src/ai_live/ops/lipsync_compare.py, ops/__main__.py    # US2: lệnh lipsync-compare
tests/unit/test_{config,character,readiness,scene_layout,scene_render,scene_controller,livetalking_renderer,rehearsal,ops_cli,
  lipsync_compare}.py, tests/integration/test_{api,readiness_api}.py, tests/fixtures/fake_fork.py
docs/RUNBOOK.md, docs/ARCHITECTURE.md                  # đổi model, kiểm tra trước demo
```

## Phase 0: Nghiên cứu → `research.md`

R1 biến chọn model · R2 cách fork bật Ultralight · R3 báo cáo `lipsync` · R4 `character.json` cho nhân vật không có clip · R5 kiểm bản ghi
cài đặt (app và fork) · R6 hình lúc im lặng · R7 tốc độ và VRAM trên laptop · R8 các biến fork chỉ dành cho wav2lip · R9 cảnh nhân vật có
bàn · R10 lệnh so sánh và kết luận · R11 canh show và nối lại.

## Phase 1: Thiết kế

- [data-model.md](./data-model.md): `LipsyncSelection`, `character.json` v1 mở rộng, `UltralightInstall` (đọc), `LipsyncReport`,
  `CompareReport`.
- [contracts/lipsync-selection.md](./contracts/lipsync-selection.md), [contracts/lipsync-compare.md](./contracts/lipsync-compare.md).
- [quickstart.md](./quickstart.md): mỗi user story một mục, ghi rõ bước nào cần GPU.
- Khác với `docs/ARCHITECTURE.md` §3: không đổi interface `AvatarRenderer`; `hello` của fork (005 fork-protocol §1) thêm khối `lipsync`
  tùy chọn, app cũ bỏ qua được.

## ADR cần ghi (đã thêm vào `docs/DECISIONS.md`; Chấp nhận 2026-11-19, người dùng duyệt "ok run đi")

- **ADR-067:** chọn model nhép miệng bằng `LIVETALKING_MODEL` và `LIVETALKING_ULTRALIGHT_TEACHER`; fork nhận `--ailive_teacher`, tự suy
  tên avatar, từ chối bật khi bản ghi cài đặt không khớp; `character.json` khai `lipsync_models`; báo cáo khối `lipsync`.
- **ADR-068:** nhân vật có sẵn bàn trong ảnh: `character.json` `scene.desk_in_image` + `scene.desk_top`, cảnh 009 bỏ lớp bàn.
- **ADR-069:** lệnh `ai_live.ops lipsync-compare` gộp bộ đo 010 với hai show 10 phút, kết luận theo ngưỡng ADR-060 mục 5, không hạ ngưỡng.

## Rủi ro mới (đã vào `docs/RISKS.md`: Q33–Q36)

- HuBERT-large + UNet không kịp 20 khung/giây hoặc vượt 3,5 GB VRAM trên GTX 1650 Ti trong live → Q33.
- Vòng khung nền ngắn của Ultralight lộ lặp hoặc có khung miệng hé lúc im lặng → Q34.
- Mép bàn trong ảnh không khớp `desk_top` khai báo: sản phẩm lơ lửng hoặc che tay host → Q35.
- Đổi `.env` mà quên bật lại fork: app và fork chạy model khác nhau → Q36 (kiểm tra trước demo báo LỖI).

## Theo dõi độ phức tạp

| Vi phạm / phức tạp thêm | Vì sao cần | Phương án đơn giản hơn đã loại vì |
|-------------------------|-----------|-----------------------------------|
| Kiểm bản ghi cài đặt ở cả app và fork | App chỉ thấy thư mục bằng chứng trong `assets/`, fork chỉ thấy bản dựng trong `data/avatars/`; sai ở bên nào cũng phải chặn (FR-007, FR-008) | Chỉ kiểm ở app: fork vẫn có thể nạp model cũ trong `data/avatars/`; chỉ kiểm ở fork: kiểm tra trước demo không chạy được khi fork tắt |
| Lệnh so sánh mới ở app thay vì mở rộng `mouth_eval` | Số show (lặng p95, câu đầu, lỗi) nằm trong bản ghi phiên của app, bộ đo 010 chạy trong venv fork | Gộp vào `mouth_eval`: fork phải đọc bản ghi phiên của app, trộn hai venv |

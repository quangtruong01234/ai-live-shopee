# Tasks: Khẩu hình miệng host AI giống người thật

- **Feature ID:** `010-natural-mouth-shapes` · **Đầu vào:** [spec.md](./spec.md), [plan.md](./plan.md), [research.md](./research.md),
  [data-model.md](./data-model.md), [contracts/](./contracts/)
- **Ghi chú:** feature chạy liên tục theo ủy quyền 2026-11-13; bộ đo (US2) dựng trước vì hướng kỹ thuật US1 phụ thuộc số đo (plan §Ghi chú
  quy trình). Danh sách dưới đây ghi lại đúng thứ tự đã làm, đánh dấu cái đã xong.

## Định dạng: `- [ ] T### [P?] [GPU?] [US#?] Mô tả kèm đường dẫn file`

- **[P]**: chạy song song được · **[GPU]**: cần GPU laptop (ADR-023) · **[US#]**: thuộc user story nào

## Phase 1: Setup

- [x] T001 ADR-053: `mediapipe` 1.2.3 + `models/face_landmarker.task` vào venv fork (chỉ bộ đo và `prepare`, không vào đường live)
- [x] T002 ADR-054: `python_speech_features` 0.6 + `models/syncnet_v2.model` vào venv fork (chỉ bộ đo)
- [x] T003 [P] Bộ câu `data/eval/mouth_sentences.json` (v1: 24 câu theo nhóm `a`, `i`, `u`, `o`, `bilabial`, `ph`, `tu_nhien`; v2 thêm
  nhóm `number` 3 câu m1–m3, chỉ để đo)
- [x] T004 [P] `scripts/mouth/synth_sentences.py`: đọc bộ câu bằng VieNeu ra `out/mouth/sentences/*.wav` (bỏ qua câu đã có)

## Phase 2: Foundational

- [x] T005 `vendor/livetalking/ailive_ext/mouth.py`: `MouthMethod`, `parse` (khóa `ref`, `paste`, `color`, `sharpen`, `gain_db`,
  `shift`; lỗi → `w2l` kèm ghi chú), `reference_faces`, `mel_window_start`, `apply_gain`, `paste` (contracts/mouth-method.md)
- [x] T006 Test `ailive_ext/tests/test_mouth.py`: parse đủ khóa, giá trị sai về `w2l`, `shift` không đọc quá phần tiếng đã có, dán lỗi
  một khung dùng hộp cứng và chỉ log một lần
- [x] T007 Móc `# ailive:` trong `avatars/base_avatar.py`, `avatars/wav2lip_avatar.py`, `avatars/audio_features/mel.py`; `mouth_method`
  trong `hello` và `stats` (`ailive_ext/ingest.py`); test `ailive_ext/tests/test_wav2lip_mouth.py`, `test_ingest.py`

**Checkpoint:** fork chạy được với mọi chuỗi cấu hình; `w2l` gọi model y hệt 005.

---

## Phase 3: User Story 2: Bộ đo khẩu hình khách quan (P2, làm trước vì US1 cần số)

- [x] T008 [P] [US2] Test `ailive_ext/tests/test_mouth_eval.py`: hàm chấm độ mở, rộng/cao, khép môi, tương quan, độ nét, so baseline
  (SC-001/002/003) bằng điểm mốc giả
- [x] T009 [US2] `ailive_ext/mouth_eval/{__main__,render,score,syncnet,report}.py` (contracts/mouth-eval.md): dựng như live, chấm
  MediaPipe + SyncNet, `report.md`/`report.json`, `--clips` (video từng đoạn, đặt cạnh nhau), `--ab` (gói xem mù, phiếu, khóa)
- [x] T010 [GPU] [US2] r1: so các núm hậu kỳ (`paste`, `color`, `sharpen`, `gain_db`, `ref=offset`) với `w2l` (research R6)
- [x] T011 [GPU] [US2] r2: cửa sổ tiếng lệch `shift=-1/-2` (research R7)
- [x] T012 [GPU] [US2] r3: ảnh tham chiếu môi khép `ref=closed:W` (research R10, chỉ để đo)
- [x] T013 [GPU] [US2] r4: đo lặp lại `w2l`/`s1` + gói A/B `out/mouth/runs/r4/ab/` (research R12, SC-007 đạt: lệch 0%)
- [x] T014 [GPU] [US2] r5: đo nền bộ câu v2 (27 câu, gồm nhóm số) cho `w2l` và `s1`, để lần sau so trên cùng phiên bản bộ câu

**Checkpoint:** có số đo cho mọi cách và gói xem mù cho người duyệt.

---

## Phase 4: User Story 1: Host nói với khẩu hình giống người hơn (P1)

- [x] T015 [US1] Chọn cách mặc định theo số đo: giữ `w2l` (ADR-055); ứng viên `shift=-1` chờ người xem gói A/B (SC-004)
- [x] T016 [P] [US1] FR-010: cột "Miệng" trong bảng độ trễ: `src/ai_live/avatar/livetalking_renderer.py`, `src/ai_live/core/models.py`,
  `src/ai_live/director/{latency,render_report,session_log}.py`, `src/ai_live/app/static/control.js`; test
  `tests/unit/test_livetalking_renderer.py`, `tests/unit/test_session_log_avatar.py`, `tests/integration/test_avatar_api.py`
- [x] T017 [US1] `LIVETALKING_MOUTH_METHOD` trong `.env.example` và `scripts/livetalking/run.ps1`; contracts fork-protocol §4
- [ ] T018 [US1] Người dùng chấm gói A/B r4 (≥ 3 người); nếu `shift=-1` thắng thì ghi ADR mới thay ADR-055, đổi mặc định trong
  `.env.example` và `docs/ARCHITECTURE.md` (**chờ người dùng**)
- [ ] T019 [GPU] [US1] Show kịch bản 10 phút với cách được chọn: fps trung vị ≥ 20, khung đầu và lặng p95 so với 005 (SC-005). Với
  mặc định `w2l` thì dùng số show 30 phút của 005 (quickstart 005 §9: `render_fps` p50 25,14); chỉ chạy lại nếu đổi sang `shift=-1`
  (**chờ T018**)

---

## Phase 5: User Story 3: Clip nói chỉ dùng đoạn mặt nhìn thẳng (P3)

- [x] T020 [P] [US3] Test `ailive_ext/tests/test_pose.py`: góc đầu từ ma trận, đoạn dùng được, đoạn ngắn bị bỏ, file JSON
- [x] T021 [US3] `ailive_ext/pose.py` (data-model §4): đo góc đầu bằng Face Landmarker, so trung vị idle, ghi `ailive_pose.json`
- [x] T022 [US3] `ailive_ext/prepare.py`: bước góc đầu sau genavatar, cờ `--max-roll/--max-pitch/--max-yaw`; thiếu model thì bỏ qua và báo;
  test `ailive_ext/tests/test_prepare.py`
- [x] T023 [US3] `ailive_ext/clips.py`: cắt clip nói thành `talk_NN~k` theo đoạn dùng được; không còn khung nào hoặc file hỏng thì phát
  cả clip kèm ghi chú; test `ailive_ext/tests/test_clips.py`
- [x] T024 [P] [US3] `src/ai_live/avatar/__main__.py`: in góc đầu từng clip nói sau `prepare`; test `tests/unit/test_avatar_cli.py`
- [x] T025 [GPU] [US3] Chạy bước góc đầu trên `demo_host_01` thật: ngưỡng mặc định không loại khung nào (research R11, ADR-056)
- [x] T026 [GPU] [US3] SC-006 trong show: recorder ghi `clip` + `idx` từng khung; với ngưỡng mặc định không có đoạn bị loại nên SC-006
  đạt hiển nhiên; kiểm thật chỉ cần khi người dùng chọn ngưỡng chặt hơn (người dùng chốt 2026-11-16: giữ ngưỡng mặc định 35/20/30)

---

## Phase 6: Hoàn thiện

- [x] T027 [P] ADR-055, ADR-056; ghi chú "Sửa bởi ADR-056" trong ADR-053
- [x] T028 [P] research R1–R12, data-model §4, contracts mouth-method/mouth-eval, fork-protocol §4–§5
- [x] T029 [P] quickstart.md (cách đo lại, gói duyệt cuối §7)
- [x] T030 [P] `docs/RISKS.md`: `mediapipe` kéo `opencv-python-headless`; số đo chỉ so được trên cùng nhân vật; clip nói quá ngắn sau
  khi loại đoạn nghiêng
- [x] T031 `progress/` (FEATURES, STATUS, LOG, OPEN), `/update-context`
- [x] T032 ruff, pytest app, pytest fork

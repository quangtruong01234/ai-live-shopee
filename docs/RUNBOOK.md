# Runbook buổi demo (Google Meet)

> Bản nháp 2026-11-13, soạn từ các quickstart 004, 005, 007, 008, 009, 010 và số đo đã có. Feature 007 thêm lệnh kiểm trước demo
> (§2, §3), banner cảnh báo của bộ canh show (§4), quy trình làm video dự phòng (§5) và báo cáo tổng duyệt (§7). Chưa chạy thử trọn
> vẹn theo đúng thứ tự này (ROADMAP M1d). Chỗ nào chưa chốt ghi `TODO:`. Phạm vi: demo ngoài Shopee, chia sẻ tab Chrome có tiếng vào Google Meet (PRD §2).
> Feature 006 thêm §8: phát qua OBS (nguồn Browser Source `/obs`), chuẩn bị cho Shopee Live sau này.
> Không dùng cho Shopee Live: ở đó cấm phát video quay sẵn, kể cả video dự phòng ở §5.

## 1. Vai trò

| Vai trò | Việc | Ai |
|---|---|---|
| Người vận hành | Chạy máy demo, bấm trang điều khiển, xử lý sự cố theo §4 | TODO: ai? |
| Người dẫn | Nói chuyện với khách trên Meet, giới thiệu dịch vụ, ghi phản hồi | TODO: ai? Có cần tách khỏi người vận hành không? |

Máy demo: laptop GTX 1650 Ti 4 GB (ADR-023), nhép miệng chạy trên GPU laptop, RunPod chỉ là dự phòng và phải hỏi chi phí trước
(`docs/RUNPOD.md`). TODO: Meet chạy trên chính máy demo hay máy thứ hai (máy demo đã nặng GPU + CPU cho VieNeu)?
Đề xuất 2026-11-17 (chờ người dùng): chia sẻ tab từ chính máy demo, người dẫn vào Meet bằng máy hoặc điện thoại khác. Chưa đo tải
khi Meet chia sẻ tab trên máy demo.

Kiểm máy demo 2026-11-17: đã đủ phần mềm cho demo qua Meet, **không cần cài thêm** (Chrome 157, `ffmpeg`, `uv`, fork nhép miệng,
giọng VieNeu; driver GPU 565.90; RAM 24 GB; ổ C còn 163 GB). OBS chỉ cần cho §8 (bản portable đã có ở `%LOCALAPPDATA%\ai-live\obs`).
Lần chạy thử 2 phút cùng ngày (nhép miệng + VieNeu, `REPLY_ENGINE=fake`): 25,3 khung/giây, VRAM 2,66 / 4 GB, lặng giữa câu p95 0,40 s.

## 2. Checklist T-1 ngày

- [ ] Văn bản đồng ý (hình + giọng) của người mẫu đã ký, bản ký lưu ngoài git (ràng buộc 4). Chưa có thì **không demo bằng nhân vật này**.
- [ ] Nội dung sản phẩm của khách đã nạp và kiểm: `validate` file Word không lỗi; giá, khuyến mãi, khẳng định cấm khớp bản gốc khách gửi (Q6).
- [ ] Bộ cảnh (009): ảnh thật của khách, `check` không còn cảnh báo `placeholder` (Q20); ảnh gốc đặt cạnh ảnh đã chỉnh đã được duyệt.
- [ ] Nhân vật: `uv run python -m ai_live.avatar check assets/avatars/<nhân vật>` báo "Hồ sơ hợp lệ"; đã `prepare` (005 quickstart §4).
- [ ] Test tự động: `uv run pytest` và test fork (`cd vendor/livetalking && .venv/Scripts/python.exe -m pytest -q ailive_ext/tests`) đều qua.
- [ ] `.env` của máy demo (xem §6): `REPLY_ENGINE=chain`, `TTS_PROVIDER=vieneu`, `AVATAR_MODE=livetalking`, `SCENE_ENABLED` theo bộ cảnh đã duyệt,
      `LIVETALKING_*` theo các giá trị đã duyệt ở gói duyệt 005/010 (`LIVETALKING_LEAD_S=2.5`, `LIVETALKING_BATCH_SIZE=16` đã chốt;
      TODO: `LIVETALKING_MOUTH_METHOD` `w2l` hay `shift=-1` theo chấm A/B 010; xem `progress/OPEN.md` §4).
- [ ] Chạy thử một show ngắn 5–10 phút với LLM thật để chắc chuỗi model trả lời được. **Không chạy bộ tự kiểm, `qa_eval` hay benchmark
      trong ngày demo và ngày trước đó** nếu hạn mức free thấp (Q11, Q14: SEA-LION bị `rate_limited` sau khoảng 194 request trong một ngày).
- [ ] Video dự phòng 2–3 phút (PRD tiêu chí 5) đã làm theo §5, phiếu kiểm `Đạt`, đúng khách, nhân vật và bản nội dung hiện tại; đã chép
      sang máy chia sẻ Meet và thử phát qua Meet có tiếng.
- [ ] Tổng duyệt 30 phút với cấu hình thật (§7 lệnh `report`): tiêu chí 3 và 4 đều `ĐẠT`, không có báo cáo nào ghi "chưa phải tổng
      duyệt thật". **Tổng duyệt dùng LLM thật nên tốn hạn mức free; làm trước T-1 ngày, không làm trong ngày demo.**
- [ ] Chạy `uv run python -m ai_live.ops readiness` trên máy demo (đủ fork + app như §3 bước 2–4): mọi mục máy kiểm được `ĐẠT`, các mục
      `CHÚ Ý` đã đọc và chấp nhận. Lệnh trả mã 0 khi sẵn sàng, 1 khi còn mục `LỖI`.
- [ ] Thử chia sẻ tab Chrome có âm thanh vào Meet từ máy khác (ROADMAP M1d): người bên kia thấy nhân vật, nhãn "AI", nghe tiếng khớp miệng.
- [ ] Không có RunPod nào đang bật (nếu đã dùng thử).
- [ ] Không cập nhật driver GPU hay Windows từ T-2 ngày tới hết buổi demo (cấu hình đã đo: driver 565.90). Nếu máy đã tự cập nhật thì
      chạy lại show thử ở §3 bước 7 trước khi vào Meet.

## 3. Checklist T-1 giờ

1. Cắm sạc laptop (số đo 2026-11-12 không ghi được nguồn điện; chạy pin có thể giảm fps). Đóng ứng dụng nặng GPU/CPU khác.
   Chế độ nguồn Windows đặt "Best performance" (kiểm 2026-11-17 máy đang ở "Balanced"); Screen và Sleep đặt "Never".
2. Terminal 1, bật fork: `powershell scripts/livetalking/run.ps1`. Chờ báo nghe ở `127.0.0.1:8010` (khoảng 6 s tới `/ailive/health` = `ok`).
3. Terminal 2, bật app: `uv run uvicorn ai_live.app.main:app --port 8000`. Nếu app dừng ngay và báo nhân vật thuộc khách khác thì
   `CUSTOMER_ID`/`AVATAR_ID` trong `.env` sai (ràng buộc 3), sửa rồi bật lại.
4. Chrome mở `http://127.0.0.1:8000/host`, bấm **Bắt đầu** (mở khóa âm thanh, Q10). Mở tab thứ hai `http://127.0.0.1:8000/` (trang điều khiển).
5. Trang điều khiển phải có: Server "đang chạy", Host "đã sẵn sàng", ô "Nhép miệng" màu xanh (đã nối fork); khu **Model LLM** không có
   banner đỏ "Không có model nào sẵn sàng". Bấm **Kiểm tra trước demo** (hoặc chạy `uv run python -m ai_live.ops readiness` ở terminal
   3): bảng phải ghi "SẴN SÀNG"; còn dòng `LỖI` thì làm theo cột "Việc cần làm" (dòng `→` ở terminal) rồi kiểm lại. Ba mục máy không kiểm được (văn bản
   đồng ý, thử chia sẻ Meet, không có RunPod) phải tự tích tay. Lệnh kiểm **không gọi LLM** (mục chuỗi model chỉ đọc trạng thái có sẵn).
6. Nhìn `/host`: nhân vật chạy clip chờ, miệng khép, nhãn "AI-GENERATED CONTENT" (ADR-065) trong khung (không được che hay tắt), watermark LiveTalking ở góc
   (license yêu cầu, ràng buộc 5); có cảnh thì thấy bàn và sản phẩm.
7. Bấm **Bắt đầu show**, nghe 2–3 câu: câu đầu ≤ 5 s, tiếng khớp miệng. Bấm **Kết thúc**. Mỗi lần bấm Bắt đầu là một `show_id` mới.
   Show thử này cũng làm ấm fork: show đầu tiên sau khi bật fork thỉnh thoảng nói câu đầu chậm tới ~5 s và hiện banner "Host im lặng"
   (007 quickstart §T056); các show sau ~1,6–2,3 s.
8. Vào Meet, chia sẻ **tab** `/host` và tích "chia sẻ âm thanh của tab". Nhờ người bên kia xác nhận nghe và thấy.
9. Mở sẵn video dự phòng ở một tab/cửa sổ khác, chưa phát.

## 4. Trong buổi demo: xử lý sự cố

Nút trên trang điều khiển: **Tạm dừng** (nói hết câu đang nói rồi dừng), **Tiếp tục**, **Bỏ qua câu đang nói**, **Kết thúc**,
**Phân đoạn kế tiếp → Chọn** (chọn sản phẩm/chủ đề nói tiếp).

Bộ canh show (007, bật khi `WATCHDOG_ENABLED=true`) tự theo dõi tiếng, hình và kết nối khi show chạy, rồi hiện banner ở đầu trang
điều khiển: **vàng** là cảnh báo, hệ thống còn tự xử lý được; **đỏ** là cần người vận hành. Banner không kêu tiếng, tự tắt khi hết lỗi;
mỗi lần mở và tắt được ghi vào `alerts.jsonl` của phiên. Mỗi banner ghi sẵn việc cần làm:

| Banner | Màu | Làm gì (đúng chữ trên banner) |
|---|---|---|
| "Host im lặng N giây" | vàng, thành đỏ nếu vẫn im sau khi tự bỏ câu | Đợi vài giây; quá `WATCHDOG_AUTOSKIP_S` (15) giây hệ thống tự bỏ câu đang kẹt. Sau khi tự bỏ: đợi câu kế tiếp; nếu vẫn im thì bấm **Bỏ qua câu đang nói** hoặc **Tạm dừng** |
| "Hình trên tab host đứng N giây" | vàng | Xem terminal fork; fork còn chạy thì tải lại `/host`, bấm "Bắt đầu" rồi chia sẻ lại tab vào Meet |
| "Có thể mất tiếng ở tab host: …" | vàng | Bấm "Bắt đầu" trên `/host`; kiểm Meet đang chia sẻ tab kèm âm thanh |
| "Mất kết nối tới fork nhép miệng (N giây)" | đỏ | Xem terminal fork; fork chết thì chạy lại `run.ps1`, đợi banner này tắt rồi bấm **Bật lại nhân vật nhép miệng** (bấm sớm hơn thì app chưa thấy fork mới, lại rơi về ảnh tĩnh; khi đó bấm lại). Show vẫn chạy bằng ảnh tĩnh trong lúc chờ (fork bật lại mất khoảng 30 giây) |
| "Màn hình host đã đóng" | đỏ | Mở lại `/host`, bấm "Bắt đầu" rồi chia sẻ lại tab vào Meet |
| "Show đang ở chế độ dự phòng: dịch vụ viết kịch bản đang lỗi" | vàng | Để show chạy chế độ dự phòng; nếu kéo dài thì chuyển sang video dự phòng (§5) |
| "Nhân vật nhép miệng lỗi, đang dùng ảnh tĩnh" | vàng | Xem terminal fork; fork còn chạy thì bấm **Bật lại nhân vật nhép miệng** |

Banner đỏ kèm dòng chung: "Cần người vận hành: xem terminal app và mục Lỗi của show; không cứu được trong khoảng 1 phút thì người dẫn
báo khách và phát video dự phòng (runbook §5)". Bộ canh chỉ tự làm một việc là bỏ câu kẹt; không tự bật lại fork, không tự đổi cấu hình.
Tab `/host` để ở nền vẫn chạy (Meet đang chia sẻ nó), nhưng **không thu nhỏ cửa sổ Chrome có tab `/host`**: Chrome có thể làm chậm
đồng hồ của tab ẩn và bộ canh sẽ báo hình đứng.

Các dấu hiệu khác (không có banner riêng hoặc có từ trước 007):

| Dấu hiệu | Nguyên nhân hay gặp | Làm gì |
|---|---|---|
| Khách không nghe tiếng | Chưa bấm "Bắt đầu" ở `/host`, hoặc Meet chia sẻ không kèm âm thanh tab | Bấm "Bắt đầu" trên `/host`; chia sẻ lại tab, tích âm thanh |
| Host "chưa mở" (banner "Chưa mở màn hình host") | Tab `/host` bị đóng hoặc tải lại | Mở lại `/host`, bấm "Bắt đầu", chia sẻ lại tab vào Meet |
| Banner "Đang dùng model dự phòng" ở khu Model LLM | Model đầu chuỗi lỗi hoặc hết hạn mức, chuỗi đã tự chuyển (008, ADR-040) | Không cần làm gì, show vẫn chạy; giọng văn có thể khác đôi chút (Q19) |
| Banner đỏ "Không có model nào sẵn sàng" hoặc "Đang ở chế độ dự phòng" | Mọi model trong chuỗi lỗi; sau `SCRIPT_FALLBACK_AFTER` lần lỗi show đọc phần giới thiệu có sẵn trong file sản phẩm | Để show chạy chế độ dự phòng (vẫn realtime, vẫn qua guard); nếu kéo dài, chuyển sang video dự phòng (§5) |
| Banner "Nhân vật nhép miệng lỗi 2 lượt liền, đang dùng ảnh tĩnh" | Fork lỗi nhiều lần liên tiếp, app tự chuyển về `static` (FR-022) | Xem terminal 1; fork còn sống thì bấm **Bật lại nhân vật nhép miệng**; fork chết thì bật lại `run.ps1` rồi bấm nút đó |
| Hình giật, miệng chậm | GPU/CPU quá tải (VieNeu và Wav2Lip cùng chạy; lượt bình luận đo được `render_fps` ~18) | Đóng ứng dụng khác, kiểm sạc; không đổi cấu hình giữa buổi |
| Host nói sai thông tin | Không nên xảy ra (guard), nhưng nếu có | Bấm **Bỏ qua câu đang nói**, người dẫn đính chính; sau buổi ghi lại câu và `show_id` để sửa guard |
| Bấm "Áp dụng" ảnh mới mà live không đổi | Cảnh đang tắt (trang báo "cảnh đang tắt, ảnh chưa hiện trên live"), ảnh chưa xác nhận quyền dùng, hoặc sổ `uploads/images.json` hỏng | Đọc dòng chữ cạnh nút "Áp dụng"; xem log `scene_image_changed` (`result`, `to_frame_ms`) trong phiên; kiểm trước demo báo `missing_confirmation` / `bad_uploads` thì xác nhận lại hoặc "Gỡ ảnh" (§9) |
| Mọi cách trên không cứu được trong khoảng 1 phút | — | Người dẫn báo khách, phát video dự phòng (§5) |

TODO: ngưỡng "1 phút" trước khi chuyển sang video dự phòng là đề xuất, người dùng chốt.

## 5. Video dự phòng

- Chỉ dùng cho demo qua Meet/YouTube, **không bao giờ** trên Shopee Live (CLAUDE.md DO NOT). App không có đường nào phát file này;
  người vận hành mở nó bằng trình phát video ngoài app.
- Người dẫn nói rõ với khách đây là bản ghi để minh họa trong lúc xử lý lỗi, không trình bày như live.
- Nội dung: cùng nhân vật, cùng khách, đọc nguyên văn phần giới thiệu và mô tả trong file sản phẩm của khách (`verbatim`, không gọi LLM,
  vẫn qua guard). Video chứa mặt và giọng người mẫu: chỉ làm khi đã có văn bản đồng ý, không commit, không gửi ra ngoài.
  TODO: người dùng duyệt video đầu tiên và chốt ADR-057 (`progress/OPEN.md` §4).

Cách làm (làm ở T-1 ngày, khi nội dung sản phẩm đã chốt; đổi nội dung thì làm lại vì lệnh kiểm trước demo so `bản nội dung`):

1. Trong `.env` đặt `AILIVE_RECORD_DIR=out/recordings` (để `AILIVE_RECORD_MAX_S` ≥ 180, mặc định 600), rồi bật fork như §3 bước 2.
   Terminal fork báo "Ghi luồng tự kiểm: bật".
2. Bật app, mở `/host`, bấm "Bắt đầu" như §3 bước 3–4. Không bấm Bắt đầu show: lệnh tự làm.
3. Terminal 3: `uv run python -m ai_live.ops backup-video --seconds 150 --content verbatim`. Lệnh kiểm app đang dùng nhân vật nhép miệng,
   có `CUSTOMER_ID`/`AVATAR_ID`, host đã mở, chưa có show; rồi bật ghi ở fork, mở show `verbatim`, chạy đủ thời lượng (in tiến độ mỗi
   10 giây), kết thúc show, dừng ghi và chấm bản ghi. Ctrl+C giữa chừng thì lệnh tự kết thúc show và dừng ghi.
4. Kết quả ở `BACKUP_VIDEO_DIR` (mặc định `out/backup_video/`): `backup_<ngày-giờ>_<khách>.mp4` cùng phiếu `.sheet.md` và `.sheet.json`.
   Phiếu `Đạt` khi dài 120–180 giây, có tiếng, nhãn "AI" có ở mọi khung hình. Mã thoát: 0 đạt, 1 không đạt, 2 lệnh từ chối chạy (làm theo
   dòng `→` in ra ngay dưới dòng `LỖI`).
5. Xem lại video bằng mắt (miệng khớp tiếng, đúng sản phẩm, nhãn "AI" rõ).
6. **Tắt ghi**: xóa `AILIVE_RECORD_DIR` khỏi `.env`, tắt rồi bật lại fork (fork tự đọc `.env` của repo, nên bỏ biến ở terminal là chưa đủ). Lệnh kiểm trước demo báo `LỖI` ở mục "Ghi luồng thử" nếu quên.
7. Chép file `.mp4` sang máy chia sẻ Meet (nếu khác máy demo), thử phát qua Meet có tiếng.

## 6. Biến môi trường cần soát trước buổi demo

| Biến | Giá trị demo | Ghi chú |
|---|---|---|
| `APP_ENV` | `demo` | `dev` mở thêm route debug và `/docs`, không cần cho buổi demo |
| `REPLY_ENGINE` | `chain` | `fake` chỉ để thử luồng, câu nói vô nghĩa |
| `TTS_PROVIDER` | `vieneu` | Gemini TTS free chỉ đủ vài câu (Q12) |
| `AVATAR_MODE` | `livetalking` | |
| `CUSTOMER_ID`, `AVATAR_ID` | của khách demo | một nhân vật cho một khách (ràng buộc 3) |
| `SCENE_ENABLED`, `SCENE_DIR` | theo bộ cảnh đã duyệt | |
| `LIVETALKING_LEAD_S`, `LIVETALKING_PREBUFFER_S`, `LIVETALKING_BATCH_SIZE`, `LIVETALKING_MOUTH_METHOD`, `LIVETALKING_HOLD_S` | `2.5`, `0.6`, `16`, theo chấm A/B 010, `2.5` | `LEAD_S` và batch chốt 2026-11-16; TODO: `MOUTH_METHOD` chờ chấm A/B 010 |
| `AILIVE_RECORD_DIR` | trống | chỉ đặt khi làm video dự phòng (§5); bật ghi luồng tốn đĩa và có mặt, giọng người mẫu |
| `WATCHDOG_ENABLED` | `true` | bộ canh show và banner §4 |
| `WATCHDOG_SILENCE_S`, `WATCHDOG_FROZEN_S`, `WATCHDOG_AUTOSKIP_S`, `WATCHDOG_AUDIO_ACK_S`, `WATCHDOG_AUDIO_ACK_LIPSYNC_S` | 5, 3, 15, 3, 6 (mặc định) | ngưỡng giây của banner im lặng, hình đứng, tự bỏ câu, mất tiếng (ảnh tĩnh / nhép miệng) |
| `OUTPUT_MODE` | `meet` | `obs` khi phát qua OBS (§8); giá trị cũ `webrtc` vẫn chạy như `meet` và log cảnh báo |
| `WATCHDOG_HOST_STALE_S` | 10 (mặc định) | chỉ khi `OUTPUT_MODE=obs`: nguồn OBS còn nối mà không gửi nhịp quá ngần này giây thì báo "Nguồn OBS đã ngắt" |
| `BACKUP_VIDEO_DIR` | `out/backup_video` | nơi lệnh `backup-video` ghi video và phiếu, nơi lệnh kiểm trước demo tìm video |

## 7. Sau buổi demo

- Bấm **Kết thúc** show, tắt app (Ctrl+C terminal 2) rồi fork (Ctrl+C terminal 1).
- Giữ log phiên (`data/sessions/<phiên>/`, cùng số liệu ở `GET /api/show`, `GET /api/latency`) để đối chiếu nếu khách hỏi; không gửi ra
  ngoài.
- Báo cáo show: `uv run python -m ai_live.ops report <phiên>` (thêm `--show <show_id>` nếu phiên có nhiều show; mặc định show cuối).
  Lệnh đọc log phiên, không cần app đang chạy, ghi `rehearsal_<show_id>.md` và `.json` cạnh log: tiêu chí 3 (khoảng lặng giữa câu,
  p95 ≤ 1,5 s và không khoảng nào > 5 s), tiêu chí 4 (≥ 30 phút, không hình đứng, mất tiếng, mất fork, đóng host hay câu lỗi), danh sách
  banner đã hiện. Mã thoát 0 khi cả hai tiêu chí `ĐẠT`.
- Ghi phản hồi của khách vào `docs/DECISIONS.md` (ADR nếu đổi hướng) và `docs/ROADMAP.md` (M1d "Demo với khách").
- Kiểm không còn RunPod nào chạy.

## 8. Phát qua OBS

Dùng khi đầu ra là OBS (sau này lên Shopee Live bằng OBS, hoặc thử ghi bằng OBS). Buổi demo qua Meet không cần phần này. OBS Studio miễn
phí, cài trên máy chạy live. Spec: `specs/006-obs-output/`.

**Trước phiên:**

1. Trong `.env` đặt `OUTPUT_MODE=obs`. Tắt chế độ ngủ và tắt màn hình của Windows (Settings → System → Power: Screen và Sleep đặt
   "Never") trước phiên dài; máy ngủ là mất hình và tiếng.
2. **Bật app trước, OBS sau.** Thứ tự bật: fork (nếu nhép miệng) → app → OBS. Nếu OBS mở trước, nguồn tự nối lại khi app lên (trang
   `/obs` thử lại mỗi giây rồi tự tải lại), nhưng dễ nhầm khi kiểm.
3. Trong OBS, ở cảnh dùng cho live: **Sources → + → Browser** (Nguồn trình duyệt), đặt tên `AI host`, rồi điền:
   - **URL:** `http://127.0.0.1:<APP_PORT>/obs` (mặc định `http://127.0.0.1:8000/obs`). Không thêm gì sau `/obs`: trang bỏ qua mọi
     tham số, nhãn "AI" luôn hiện.
   - **Width** `720`, **Height** `1248` (khung dọc 9:16 của cảnh 009).
   - Bật **Control audio via OBS** để tiếng của host đi vào mixer OBS.
   - Bỏ chọn **Shutdown source when not visible**: chuyển cảnh không làm rớt kết nối. Nếu lỡ bật, ẩn nguồn là mất tiếng và trang điều
     khiển báo "Nguồn OBS đã ngắt"; hiện lại thì nguồn tự nối.
   - Bỏ chọn **Refresh browser when scene becomes active**.
   - Bấm OK.
4. Mixer OBS → bánh răng của `AI host` → **Advanced Audio Properties**: giữ **Audio Monitoring** ở **Monitor Off** (mặc định). Bật
   nghe thử trên cùng loa với micro hoặc với trang khác đang phát dễ gây vọng tiếng.
5. Trang điều khiển phải hiện **Đầu ra: OBS (đã nối)**. Chạy kiểm tra trước demo (§2, §3): mục "Màn hình host" phải `ĐẠT` "Nguồn OBS đã
   nối, âm thanh sẵn sàng".
6. Xem thử hình trong cửa sổ preview của OBS. Trên laptop, khâu nhép miệng chỉ chạy một phiên hình nên không có trang xem thử thứ hai.

**Trong phiên, đừng:**

- Mở `/obs` trên Chrome thường: trang đó cướp quyền phát của nguồn OBS (nguồn mới thắng), còn Chrome cần bấm mới có tiếng. Muốn thử
  trang `/obs` ngoài OBS thì làm trước phiên.
- Mở `/host` khi OBS đang phát: trang đó chỉ hiện "Đang phát qua OBS, xem trong cửa sổ OBS" và không phát tiếng, nhưng không có lý do để mở.
- Thêm hai nguồn `/obs` cùng lúc (hai cảnh, hai nguồn): nguồn nối sau thắng, nguồn trước im.

**Khi lỗi** (banner trên trang điều khiển, xem thêm §4):

| Banner | Việc cần làm |
|---|---|
| Nguồn OBS đã ngắt | Kiểm OBS còn chạy; chuột phải nguồn `AI host` → **Refresh**; đừng để trang `/host` trên Chrome phát thay |
| Nguồn OBS đã ngắt: không gửi nhịp trạng thái N giây | Nguồn còn nối nhưng đứng: chuột phải nguồn → **Refresh** |
| Hình trong nguồn OBS đứng N giây | Xem terminal fork; fork còn chạy thì chuột phải nguồn → **Refresh** |
| Có thể mất tiếng ở nguồn OBS | Kiểm **Control audio via OBS** và thanh âm lượng nguồn trong mixer OBS (không bị tắt tiếng, không kéo về 0) |

Video dự phòng (§5) **không bao giờ** phát qua OBS: OBS là đường lên live, mà Shopee cấm phát video quay sẵn.

## 9. Đổi ảnh và bộ sản phẩm giữa live (feature 012)

Mọi thao tác ở khối **Ảnh sản phẩm** trên trang điều khiển; show không phải dừng. Chi tiết: `specs/012-product-image-upload/quickstart.md`.

1. **Thay ảnh một món:** chọn món → chọn file (PNG/WebP/JPEG; nên dùng PNG nền trong suốt, ảnh còn nền vẫn áp được nhưng trang cảnh báo)
   → **Xem trước** (khung tĩnh cạnh ảnh live, live chưa đổi) → tích ô xác nhận quyền dùng → **Áp dụng**. Chỉ tích ô khi ảnh đúng là ảnh
   khách cung cấp, chụp thật sản phẩm, không logo/người của bên thứ ba, không do AI tạo (ràng buộc 8).
2. **Đổi cả bộ sản phẩm:** **Chuẩn bị bộ mới** → tải file nội dung mới (live vẫn chạy bộ cũ) → gán ảnh từng món (món đã từng có ảnh
   tự dùng lại) → **Xem trước bộ mới** → **Áp dụng bộ mới**. Còn món thiếu ảnh thì trang hỏi lại; đồng ý thì món đó chỉ hiện thẻ tên/giá.
   Trang báo "bộ đang live đã đổi" nghĩa là ai đó vừa sửa nội dung live: xem lại trước khi áp. **Hủy chuẩn bị** không đổi gì trên live.
3. **Hoàn tác / gỡ:** **Về ảnh trước** lùi một bước (ảnh trước đó, rồi ảnh bộ cảnh), nút khóa khi hết bước. **Gỡ ảnh** hỏi lại rồi để món
   chỉ còn thẻ tên/giá; **Về ảnh trước** lấy lại ảnh vừa gỡ. Phần chi tiết ghi lúc tải, lúc áp, lúc xác nhận và mọi ảnh đã tải của món.
4. **Xem AI vừa nói:** khối **AI vừa nói** liệt kê câu kịch bản gần nhất (giờ, món, chủ đề); bấm tên món để xem đủ dữ liệu món đó và so.
5. **Dọn tay `uploads/`:** app không tự xóa ảnh đã tải (dung lượng hiện ở phần chi tiết). Muốn bỏ hẳn ảnh của một món: **tắt app**, xóa
   `SCENE_DIR/uploads/<product_id>/` và mục `<product_id>` trong `uploads/images.json` (hoặc xóa cả `uploads/` để về bộ cảnh gốc), rồi
   chạy `uv run python -m ai_live.scene check` (012 contracts/scene-set.md §6). Không sửa tay khi app đang chạy.

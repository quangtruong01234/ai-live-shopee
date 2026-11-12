# Nghiên cứu (Phase 0): 005-lipsync-livetalking

- **Ngày:** 2026-11-06 · **Plan:** [plan.md](./plan.md) · **Spec:** [spec.md](./spec.md)
- Mã LiveTalking đọc ở nhánh mặc định của `github.com/lipku/LiveTalking` ngày 2026-11-06 (lần push gần nhất 2026-10-20). Commit chính
  xác ghim lúc dựng fork (TODO ở R2). Số dòng dẫn chứng có thể lệch khi upstream đổi.

## R1. Model nhép miệng trên laptop 4 GB: Wav2Lip (`wav2lip256` của LiveTalking)

- **Quyết định:** dùng model `wav2lip` của LiveTalking với checkpoint `wav2lip256.pth` (đổi tên thành `models/wav2lip.pth` như README
  hướng dẫn). Không dùng MuseTalk ở giai đoạn laptop. Chốt phần "chọn model" còn mở của ADR-004 cho giai đoạn laptop (ADR-041 đề xuất);
  chọn lại khi có GPU mạnh hơn (RunPod, M2).
- **Lý do:**
  - README LiveTalking: wav2lip256 đạt 60 fps trên RTX 3060 và 120 fps trên 3080Ti; MuseTalk 42 fps trên 3080Ti, 45 trên 3090, 72 trên
    4090. GPU khuyến nghị: RTX 3060 trở lên cho wav2lip, 3080Ti trở lên cho MuseTalk. GTX 1650 Ti 4 GB yếu hơn 3060 nhiều, nên MuseTalk
    gần như chắc chắn không chạy realtime; Wav2Lip là lựa chọn duy nhất có cơ hội (ADR-023 đã nói "MuseTalk nhiều khả năng không đủ").
  - Wav2Lip chỉ sửa vùng miệng trên khung hình clip nền, đúng mô hình "clip nền chuyển động + miệng tạo realtime" của spec (FR-002, FR-006).
- **Phương án đã cân nhắc:** MuseTalk (đẹp hơn, nặng hơn, cần VAE + whisper, nhiều license, RISKS L3); `ultralight` của LiveTalking
  (nhẹ, chất lượng thấp hơn, phải tự huấn luyện theo từng nhân vật); Wav2Lip gốc 96×96 của Rudrabha (license phi thương mại, RISKS L2;
  giữ làm phương án khi wav2lip256 quá chậm, xem R8).
- **Nguồn:** README / readme_en của LiveTalking (bảng hiệu năng, mục tải model); ADR-023.
- **TODO:**
  - Đo trên laptop: `inferfps` và `finalfps` (log của LiveTalking, README yêu cầu cả hai ≥ 25 để realtime) và VRAM dùng thật. Ghi số vào
    ADR-041 và SC-006.
  - Checkpoint `wav2lip256.pth` tải từ Google Drive / Quark của tác giả LiveTalking; chưa rõ nguồn gốc huấn luyện và license (RISKS L11).

## R2. Cách tích hợp: fork LiveTalking chạy process riêng, venv riêng; app đẩy PCM vào fork

- **Quyết định:**
  - Chọn cách (b) của ARCHITECTURE §3: TTS của mình làm ra PCM, đẩy vào LiveTalking; LiveTalking chỉ làm nhép miệng và xuất hình.
    Không dùng TTS, LLM hay ASR sẵn có của LiveTalking.
  - LiveTalking chạy **process riêng** với **venv riêng** (torch + CUDA). App `ai_live` không import torch; `pyproject.toml` không thêm
    torch. Người vận hành tự bật process LiveTalking trước khi mở app (script `scripts/livetalking/run.ps1`); app không tự sinh process.
  - Mã fork để ngoài kho mã này: clone vào `vendor/livetalking/` (đã gitignore), nhánh `ailive` chứa các thay đổi của mình, commit
    upstream ghim trong `scripts/livetalking/setup.ps1`. Thay đổi của fork gom vào một gói mới `ailive_ext/` trong fork và vài chỗ móc
    nhỏ vào file gốc, để rebase upstream dễ. Trả lời TODO của ADR-004 (ADR-042 đề xuất).
- **Lý do:**
  - Hiến pháp (CLAUDE.md "Async-first"): việc GPU nặng chạy ở executor hoặc process riêng. Process riêng còn cô lập lỗi: hết VRAM hay
    treo chỉ làm hỏng lượt (FR-017), app vẫn sống để tự về ảnh tĩnh (FR-022).
  - LiveTalking yêu cầu torch 2.9.1 bản CUDA 12.8 và hàng chục gói (aiortc, opencv, transformers, diffusers...). Để chung venv sẽ kéo
    toàn bộ vào `uv sync` và test của app, trái Điều V (test chạy không cần GPU) và Điều VII.
  - LiveTalking không có endpoint nhận PCM dạng stream (xem R3), nên dù sao cũng phải sửa code; một fork là cần thiết.
  - Clone ngoài git thay vì submodule: không vướng submodule khi làm thẳng trên `main` (ADR-027) và khi sub-agent chạy song song.
- **Phương án đã cân nhắc:**
  - Cách (a): viết TTS của mình thành plugin trong fork, gửi chữ qua HTTP. Loại: TTS (003) phải chạy trong venv GPU, tranh VRAM, và
    mất adapter `TTSEngine` độc lập.
  - Dùng LiveTalking nguyên bản qua `POST /humanaudio` (gửi file âm thanh từng câu): không stream được, không có nhãn AI trong khung,
    không xoay clip. Vẫn phải fork.
  - Git submodule trong `vendor/`: ghim commit bằng git, nhưng thêm bước `git submodule update` cho mọi người và sub-agent. Giữ làm
    phương án nếu người dùng muốn.
  - Import LiveTalking như thư viện trong process của app: kéo torch vào app, một lỗi CUDA làm chết cả app.
- **Nguồn:** `requirements.txt`, `app.py`, `docs/api.md` của LiveTalking; ARCHITECTURE §3 ghi chú tích hợp; ADR-004.
- **TODO:**
  - Ghi SHA commit upstream khi dựng fork lần đầu.
  - Fork có đẩy lên đâu không (repo GitHub riêng tư của người dùng?) hay chỉ giữ local. Fork công khai từ repo công khai sẽ công khai
    mọi thay đổi; cần người dùng quyết định trước khi đẩy.

## R3. Đường đưa tiếng vào fork: WebSocket PCM mới, ack đi ngược cùng kết nối

- **Quyết định:** thêm vào fork endpoint WebSocket `GET /ailive/ws?sessionid=<id>` (aiohttp, cùng server cổng 8010). App gửi
  `sentence_start` (JSON), các khung nhị phân PCM16 mono 16 kHz (ADR-025), `sentence_end`, `stop`; fork đổi PCM16 sang float32, cắt
  thành khung 320 mẫu (20 ms) và gọi `put_audio_frame(chunk, datainfo)` của avatar của phiên đó. Khung đầu câu mang
  `datainfo = {"status": "start", "utterance_id", "seq"}`, khung cuối mang `{"status": "end", ...}`. Fork gửi ngược `playback_started`,
  `sentence_played`, `stats`, `error` trên cùng WebSocket. Từ vựng tin nhắn giống `/ws/host` của ADR-016 để `LiveTalkingRenderer`
  dùng lại cách chờ ack của `StaticRenderer`. Chi tiết: [contracts/fork-protocol.md](./contracts/fork-protocol.md).
- **Lý do:**
  - `docs/api.md` chỉ có `/human` (chữ), `/humanaudio` (cả file), `/interrupt_talk`, `/is_speaking`, `/record`, `/set_audiotype`, `/sse`.
    Không có đường stream PCM. Bên trong, `BaseASR.put_audio_frame(audio_chunk: float32, datainfo: dict)` nhận khung 16 kHz 20 ms và
    `datainfo` đi kèm khung tiếng tới tận lúc WebRTC gửi khung đó: `server/webrtc.py` gọi `player.notify(eventpoint)`, rồi
    `BaseAvatar.notify` đẩy sự kiện có `status` ra hàng đợi SSE. Đây là móc có sẵn để biết **lúc khung tiếng đầu câu thực sự được gửi đi**,
    cùng lúc với khung hình nhép miệng đi kèm.
  - Một WebSocket hai chiều đơn giản hơn POST từng khung + SSE riêng; app đã dùng WebSocket cho `/ws/host`.
  - Khi hàng đợi tiếng rỗng, `get_audio_frame` tự trả khung im lặng (`type=1`), nên app được đẩy nhanh hơn thời gian thật; hàng đợi
    `Queue()` không giới hạn, `flush_talk` (sau `/interrupt_talk`) xóa sạch hàng đợi khi bỏ qua.
- **Phương án đã cân nhắc:** `POST /humanaudio` từng câu (phải đợi đủ câu, mất stream); POST khung PCM + nghe `/sse` (hai kênh, khó
  ghép lỗi); ghi PCM ra pipe/virtual audio device (phức tạp trên Windows).
- **Nguồn:** `docs/api.md`, `asr/base.py` (`put_audio_frame`, `get_audio_frame`, `flush_talk`), `server/webrtc.py`, `avatars/base_avatar.py`
  (`notify`) của LiveTalking.
- **TODO:** xác minh ack `status: end` tới đúng lúc khung cuối được gửi khi câu kết thúc giữa một lô suy luận (R6).

## R4. Hình và tiếng tới Chrome: WebRTC của LiveTalking, phát trong trang `/host` của app

- **Quyết định:**
  - Ở `AVATAR_MODE=livetalking`, trang `/host` của app (vẫn cổng 8000) hiện thẻ `<video>` nhận WebRTC từ fork qua `POST /offer` của
    LiveTalking (SDP JSON, trả `sessionid`), dùng `RTCPeerConnection` có sẵn của Chrome, không thêm thư viện JS.
  - Tiếng đi trong cùng kết nối WebRTC với hình, nên tiếng và miệng do LiveTalking giữ khớp. Trang host **không** phát Web Audio ở
    chế độ này. Phụ đề và nhãn trạng thái vẫn do app điều khiển qua `/ws/host`.
  - Trang host báo `sessionid` cho app trong tin `ready`; app dùng `sessionid` đó để mở `/ailive/ws`.
  - Fork chạy `transport: webrtc`, `max_session: 1` (một trang host, đỡ VRAM).
  - Google Meet chia sẻ tab `/host` như cũ (FR-018): Chrome chia sẻ được tiếng của thẻ `<video>` trong tab.
- **Lý do:** LiveTalking đã có WebRTC (aiortc) và trang mẫu `webrtcapi.html` gọi `/offer`; dùng lại thay vì tự encode. LiveTalking bật
  CORS nên trang ở cổng 8000 gọi được cổng 8010 trên `127.0.0.1`.
- **Phương án đã cân nhắc:** `POST /whep` (chuẩn hơn, trả `X-Session-ID`; giữ làm phương án nếu `/offer` đổi); app tự nhận khung hình
  rồi encode (thêm aiortc vào app, trái R2); virtual cam (cần driver, để feature OBS).
- **Nguồn:** `docs/api.md` (`/offer`, `/whep`), `config.yaml` (`transport`, `max_session`, `listenport: 8010`), `app.py` (CORS) của
  LiveTalking; ADR-016.
- **TODO:** đo độ trễ jitter buffer của Chrome với WebRTC localhost (R6).

## R5. Nhãn "AI" ghép trong khung hình của fork; giữ watermark LiveTalking

- **Quyết định:**
  - Fork vẽ nhãn ngay trước khi đẩy khung ra output (`process_frames`, cạnh chỗ đang vẽ watermark), trên mọi khung: idle, nói, câm.
    Chữ và vị trí lấy từ `AI_LABEL_TEXT`, `AI_LABEL_POSITION` (đã có trong `.env.example`) truyền vào fork lúc bật.
  - Không có API hay cờ nào tắt nhãn. Fork từ chối khởi động khi chữ nhãn rỗng. Nhãn vẽ bằng `cv2.putText` có nền đặc nên chữ phải là
    ASCII (ví dụ `AI`, `AI-generated`); fork từ chối chữ ngoài ASCII.
  - **Giữ nguyên** watermark "LiveTalking" mà code gốc vẽ ở mọi khung (`cv2.putText(..., "LiveTalking", (10, 20), ...)`), không xóa,
    không che (CLAUDE.md DO NOT).
  - Khi tự về ảnh tĩnh (FR-022), trang host hiện nhãn bằng lớp CSS như chế độ static (ADR-016), vì không còn khung video.
- **Lý do:** FR-010, Điều I. LiveTalking Apache-2.0 nhưng README ghi: "Videos developed based on this project and published on platforms
  such as Bilibili, WeChat Channels, and Douyin must include the LiveTalking watermark and logo." Code đã tự vẽ chữ "LiveTalking";
  `genavatar.video2imgs` cũng đóng chữ đó lên ảnh avatar.
- **Phương án đã cân nhắc:** nhãn bằng CSS phủ lên `<video>` (không phải trong khung, trái FR-010); vẽ bằng Pillow để có tiếng Việt
  (thêm phụ thuộc trực tiếp vào fork; chưa cần vì nhãn hiện là "AI").
- **Nguồn:** LICENSE (Apache-2.0), README, `avatars/base_avatar.py` (`process_frames`), `avatars/wav2lip/genavatar.py` của LiveTalking.
- **TODO:**
  - Câu README chỉ nêu nền tảng Trung Quốc; YouTube và Shopee có phải hiện thêm **logo** LiveTalking không? Hỏi tác giả hoặc đọc
    điều khoản bản thương mại trước khi thu tiền khách (RISKS L1).
  - Watermark do `genavatar` đóng lên ảnh avatar nằm cả trong vùng mặt đưa vào model không? Xem lúc chuẩn bị nhân vật đầu tiên.

## R6. Mốc `avatar_first_frame` và độ trễ tạo hình

- **Quyết định:** `avatar_first_frame` = lúc app nhận ack `playback_started` của câu đầu từ fork. Fork gửi ack này khi WebRTC gửi khung
  tiếng đầu tiên của câu (sự kiện `status: start` ở R3), tức khung hình nhép miệng đầu tiên rời output. Thời gian bước tạo hình của lượt
  là `tts_first_chunk → avatar_first_frame` (bước đã có trong bảng độ trễ). Fork gửi thêm `stats` cuối câu: số khung, `render_fps` thực
  tế và `infer_fps` (FR-020).
- **Lý do:**
  - ARCHITECTURE §4 định nghĩa mốc này là "frame đầu tiên miệng bắt đầu nói ra khỏi output"; ack lúc gửi khớp định nghĩa đó.
  - FR-019 nói "được hiển thị". Chrome còn giữ khung trong jitter buffer trước khi vẽ; app không gắn được khung đang vẽ với một câu cụ
    thể nếu không thêm dữ liệu vào luồng video. Chấp nhận lệch này, đo riêng một lần.
  - Độ trễ cấu trúc của LiveTalking (đọc từ code): suy luận theo lô `batch_size` khung hình (mặc định 16, mỗi khung 40 ms = 2 khung tiếng
    20 ms), cần thêm `r = 10` khung tiếng ngữ cảnh bên phải (200 ms). Lô chứa đầu câu chỉ suy luận khi đủ, nên khung đầu ra muộn tới
    khoảng `batch_size × 40 ms + 200 ms + thời gian suy luận một lô` (bs 16: ≥ 0,84 s cộng suy luận). Giảm `batch_size` (ví dụ 4–8) làm
    giảm độ trễ nhưng giảm thông lượng; chọn bằng số đo (R8).
- **Phương án đã cân nhắc:** trang host báo bằng `requestVideoFrameCallback` (không gắn được với câu); ước từ thời lượng audio (sai khi đệm,
  R12 của 004 đã loại).
- **Nguồn:** `avatars/base_avatar.py` (`inference`, `render`), `asr/base.py` (`stride_left_size = opt.l`, `stride_right_size = opt.r`),
  `config.yaml` (`l: 10`, `r: 10`, `batch_size: 16`) của LiveTalking; ARCHITECTURE §4.
- **Số đo lệch ack ↔ hiển thị (2026-11-12, T074, phiên `20261112-192347`):**
  - Cách đo (thay cho quay màn hình 60 fps, chính xác hơn và không cần ghi hình mặt): đầu đo chạy trong trang `/host` của Chrome thật.
    WebAudio đọc tiếng của luồng WebRTC, lấy lúc tiếng bắt đầu sau ≥ 1 s im lặng (RMS < 0,003). Ghép với giờ ack (`t_mono` của
    `avatar_first_frame`, đổi sang giờ đồng hồ bằng độ lệch trung vị của `comment_received` / `tts_first_chunk`, chênh 22 ms) trong cửa
    sổ −0,5…+2,5 s. `requestVideoFrameCallback` cho độ trễ từ lúc khung tới trình duyệt đến lúc dự kiến vẽ.
  - Ack → Chrome phát tiếng: 326/342 ack ghép được, trung vị 275 ms, p95 644 ms, nhỏ nhất 208 ms, lớn nhất 938 ms. Số này gồm cả đoạn gần
    im lặng ở đầu tiếng TTS nên là cận trên.
  - Khung nhận → vẽ (n = 16 467): trung vị 211 ms, p95 525 ms.
  - Kết luận: tiếng và hình đi cùng một luồng WebRTC, Chrome tự đồng bộ hai bên, nên lệch này chung cho cả hai: không có cảnh "tiếng xong
    trước miệng", không cần chỉnh `LIVETALKING_LEAD_S` vì lệch này. Khoảng lặng giữa câu gần như không đổi vì cả hai đầu cùng dịch. Mọi
    số độ trễ ghi theo ack thấp hơn lúc người xem thấy chừng 0,2–0,3 s (p95 ~0,65 s).
- **TODO:** không có.

## R7. Clip nền: chuẩn bị nhân vật, xoay vòng, chuyển clip mượt

- **Quyết định:**
  - **Chuẩn bị (FR-001–005):** lệnh `uv run python -m ai_live.avatar prepare <thư mục nhân vật>` của app kiểm `character.json` và hồ sơ
    nguồn gốc (thuần Python, test được không GPU), rồi gọi script chuẩn bị của fork bằng Python của venv fork (`LIVETALKING_PYTHON`).
    Script fork chạy `genavatar` cho **từng clip** (ra ảnh toàn khung, ảnh mặt, tọa độ), dùng S3FD đếm mặt mọi khung, từ chối khi khác
    đúng một mặt và báo tên clip + chỉ số khung. App ghi kết quả (sẵn sàng / lỗi kèm lý do) vào `character.json`. Một lệnh cho người vận hành.
  - **Clip dùng:** bản gốc 24 fps (`idle_01.mp4`, `talk_01.mp4`...), không dùng bản `_pingpong`: LiveTalking đã phát khung theo kiểu đi
    tới rồi đi lùi (`mirror_index`), nên chỗ lặp tự liền mạch. Bản `_pingpong` giữ lại để xem bằng mắt.
  - **Xoay vòng (FR-012, FR-013):** fork có `ailive_ext/rotation.py` (thuần Python): chọn clip đúng loại, khác clip vừa dùng của loại
    đó, trừ khi chỉ có một. Clip nói chọn mới ở đầu mỗi lượt; câu dài hơn clip thì clip lặp kiểu đi tới đi lùi (spec cho phép "lặp lại
    hoặc nối"). Clip chờ đổi sau mỗi vòng đi tới đi lùi đầy đủ.
  - **Chuyển clip (FR-009):** mọi clip tạo từ cùng `face.png`, nên khung 0 của các clip gần như cùng tư thế. Khi đổi clip, clip mới bắt
    đầu ở khung 0, và fork bật lại cơ chế chuyển dần sẵn có (`enable_transition`, đang tắt, `_transition_duration = 0.1`) với thời lượng
    cấu hình được (`LIVETALKING_TRANSITION_S`, mặc định 0,3 s, TODO chỉnh theo SC-007). Đổi clip chỉ ở đầu / cuối lượt hoặc khi hết vòng
    clip chờ.
    _Sửa khi làm T066 (2026-11-12):_ `enable_transition` của upstream chỉ trộn khi đổi nói ↔ im lặng, không khớp chỗ đổi clip (giữ clip
    nói qua lúc im lặng, xoay clip chờ trong lúc im lặng). Fork dùng `Crossfade` riêng trong `rotation.py`, trộn mỗi khi `clip_id` đổi,
    tính theo số khung, trước watermark và nhãn AI; `enable_transition` vẫn tắt.
  - **Giữ clip nói giữa hai câu (US2 #1; sửa theo analyze A1, người dùng chọn 2026-11-06):** giao thức không có tin "hết lượt", và giữa hai câu của cùng lượt fork im lặng ít nhất một lô suy luận (R15). Nếu về clip chờ ngay khi im lặng, nhân vật sẽ giật về chờ giữa hai câu. Fork giữ clip nói hiện tại thêm tối đa `LIVETALKING_HOLD_S` (mặc định 1,5 s, bằng mục tiêu lặng p95 của Điều VI; đổi 2,5 s ngày 2026-11-12, xem dưới) sau khung cuối của câu: trong khoảng giữ phát khung nền gốc của clip nói (không dán miệng, miệng như clip nguồn), chỉ số khung chạy tiếp kiểu đi tới đi lùi. Câu mới đến trong khoảng giữ: `seq > 0` nói tiếp trên clip đó, `seq == 0` chọn clip nói mới (_sửa 2026-11-12, T067: mọi câu đến trong khoảng giữ nói tiếp trên clip đó; clip nói đổi khi bắt đầu từ clip chờ hoặc khi clip đã chạy hết một vòng đi tới đi lùi, ở ranh giới câu. Lý do: mỗi câu kịch bản là một `utterance_id` riêng nên quy tắc cũ đổi clip ở mọi câu (44 lần / 7 phút), chỉ chiếu ~3 s đầu của mỗi clip. Khoảng nghỉ giữa hai câu kịch bản đo được p95 ~2,9 s nên `LIVETALKING_HOLD_S` mặc định thành 2,5 s; cộng thêm tới hai lô suy luận vì "đang nói" xét theo lô_). Im lặng quá `LIVETALKING_HOLD_S` hoặc nhận `stop` → chuyển dần về clip chờ. Logic nằm trong `ClipScheduler` của `ailive_ext/rotation.py` (thuần Python, test không GPU). Phương án đã loại: thêm tin `turn_end` vào giao thức (lõi phải biết câu nào là câu cuối của lượt, phải sửa `ShowDirector`/`ScriptRunner`, trái Điều IV).
  - **24 → 25 fps:** LiveTalking chạy cố định 25 fps (khung hình 40 ms = 2 khung tiếng 20 ms). Phát khung clip 24 fps ở 25 fps (chuyển
    động nhanh hơn 4%), không nội suy.
- **Lý do:**
  - LiveTalking chỉ có một vòng nói (`frame_list_cycle`) và một clip chờ mỗi `audiotype` (`custom_config`); không có xoay vòng nên phải sửa.
  - Kiểm thô 2026-11-06: cuối clip nói lệch tư thế so với khung 0 của clip chờ, bản thường nhảy hình ở chỗ lặp; ping-pong và chuyển dần
    giải quyết cả hai. Khi chuyển từ im lặng sang nói, code gốc đã đưa chỉ số clip nói về 0, nhưng chỉ số clip chờ thì chạy tiếp từ chỗ cũ
    (có thể nhảy hình) nên cũng phải về 0.
  - Đổi fps trong LiveTalking kéo theo đổi kích thước khung tiếng; README ghi fps "must be 25".
- **Phương án đã cân nhắc:** ghép tất cả clip nói thành một clip dài (vẫn một vòng, chỗ nối giữa clip nhảy hình); nội suy clip lên 25 fps
  (thêm bước xử lý, lợi ích không thấy được); để app chọn clip và gửi tên clip (xoay clip chờ vẫn phải ở fork vì app không biết lúc
  clip chờ hết vòng).
- **Nguồn:** `avatars/base_avatar.py` (`mirror_index`, `inference`, `process_frames`, `custom_index`), `avatars/wav2lip/genavatar.py`
  (`generate_avatar(video_path, avatar_id, save_path, img_size=96, pads=[0,10,0,0], face_det_batch_size=16)`), `data/custom_config.json`,
  `config.yaml` (`fps`) của LiveTalking; báo cáo kiểm thô clip ([progress/LOG.md](../../progress/LOG.md) 2026-11-06).
- **TODO:**
  - RAM laptop đủ nạp mọi clip không: mỗi clip 121 khung 480×832×3 byte ≈ 145 MB ảnh toàn khung chưa nén; 4–6 clip ≈ 0,6–0,9 GB. Kiểm
    lúc chạy thật.
  - `talk_01` hé miệng thấy răng ở khung ~84–106: model sẽ vẽ đè vùng miệng, nhưng răng ở viền có thể lộ. Xem ở SC-001; nếu lộ thì cắt
    clip hoặc tạo lại.

## R8. Máy không kịp: giảm tải thay vì để tiếng đi trước hình (FR-007)

- **Quyết định:**
  - Trong LiveTalking, mỗi khung hình đi ra cùng đúng 2 khung tiếng của nó (`process_frames` đẩy cặp hình + tiếng), nên **tiếng không thể
    đi trước hình**: máy chậm thì cả hai cùng chậm, độ trễ tăng và tiếng bị ngắt quãng. FR-007 vì thế được giữ bằng cấu trúc, phần việc
    là giữ suy luận ≥ 25 khung/giây.
  - Các nút giảm tải, theo thứ tự thử: (1) `batch_size` nhỏ hơn hoặc lớn hơn theo số đo; (2) giảm kích thước khung clip (ví dụ 480×832 →
    360×624) lúc chuẩn bị; (3) fork thêm `LIVETALKING_LIP_EVERY_N = 2`: chỉ suy luận miệng ở mỗi khung thứ 2, khung còn lại dùng lại
    miệng vừa tạo (miệng 12,5 khung/giây, nền và tiếng vẫn 25); (4) RunPod (báo chi phí trước, ADR-019).
- **Lý do:** FR-007 cho phép giảm khung hình hoặc độ nét. Nút (3) là cách giảm "số khung hình" của miệng mà không phá cặp hình + tiếng 40 ms.
- **Phương án đã cân nhắc:** giảm fps toàn bộ xuống 12,5 (phải đổi kích thước khung tiếng trong toàn bộ LiveTalking, rủi ro cao); bỏ khung
  khi tụt (tiếng sẽ đi trước hình, trái FR-007).
- **Nguồn:** `avatars/base_avatar.py` (`inference`, `process_frames`) của LiveTalking.
- **Thứ tự thử thật (analyze A3):** (1), rồi (3) (chỉ đổi biến), rồi (2) (phải tạo lại bộ clip nhỏ hơn và chạy lại `prepare`; cách tạo clip nhỏ hơn hỏi người dùng lúc cần, T075).
- **TODO:** số đo thật trên GTX 1650 Ti quyết định dùng nút nào; nếu cả (1)–(3) vẫn dưới 25 khung/giây thì báo người dùng trước khi tính RunPod.

## R9. Tự về ảnh tĩnh sau 2 lượt lỗi liền và bật lại (FR-022)

- **Quyết định:**
  - App có `SwitchingRenderer` (lớp bọc, thuần Python) giữ hai renderer: `LiveTalkingRenderer` và `StaticRenderer` dùng ảnh `face.png`
    của chính nhân vật. Lớp bọc là `AvatarRenderer` duy nhất mà `ShowDirector` thấy.
  - Đếm **lỗi bước render liền nhau theo lượt** (mỗi `utterance_id`): lượt có lỗi render +1; lượt render xong về 0; lượt lỗi ở bước khác
    (LLM, guard, TTS) hoặc bị bỏ qua không đổi bộ đếm. Đạt 2 thì từ lượt kế tiếp dùng `StaticRenderer` và phát sự kiện `avatar_mode`.
  - `ShowDirector` và `ScriptRunner` báo kết quả bước render cho renderer qua phương thức tùy chọn `record_render_outcome(utterance_id, ok)`
    (Protocol `RenderOutcomeSink`, kiểm bằng `isinstance` như đang làm với `host_ready`). Phải báo từ lõi vì lỗi giả lập
    (`FaultInjector.check_render`) nổ trước khi gọi `renderer.speak`, lớp bọc không tự thấy (SC-005 dùng lỗi giả lập).
  - Bật lại: `POST /api/avatar/lipsync` trên trang điều khiển đưa lớp bọc về `livetalking` từ lượt kế tiếp, bộ đếm về 0. Trang host đổi
    hiển thị theo tin `mode` trên `/ws/host`; nếu kết nối WebRTC đã chết, trang host gọi lại `/offer` và báo `sessionid` mới.
  - Ghi log `avatar_fallback` và `avatar_lipsync_enabled`; trang điều khiển hiện dải cảnh báo và nút "Bật lại nhân vật nhép miệng".
- **Lý do:** FR-022, US2 #5–#6, SC-005. Lớp bọc giữ lõi pipeline không phụ thuộc LiveTalking (Điều IV); chỉ thêm một lời báo kết quả.
- **Phương án đã cân nhắc:** đếm trong `ShowDirector` (lõi biết chuyện ảnh tĩnh / nhép miệng, trái Điều IV); để lớp bọc tự gọi
  `check_render` (lỗi giả lập sẽ bị lấy hai lần ở chế độ static); tự bật lại sau N phút (spec chọn người vận hành bật).
- **Nguồn:** spec 005 FR-022; `director/show_director.py` (`_play_all`, `getattr(self.renderer, "host_ready", False)`),
  `director/script_runner.py` (`check_render`, `renderer.speak`), `director/faults.py`.

## R10. Thời gian chờ và lỗi của `LiveTalkingRenderer`

- **Quyết định:**
  - `speak()` ném `RendererUnavailable` khi trang host chưa `ready` (giống static, `kind = host_unavailable`), và
    `RendererError("lipsync_unavailable")` khi trang host chưa báo `sessionid` hoặc chưa nối được `/ailive/ws`.
  - Chờ ack `playback_started` tối đa `LIVETALKING_FIRST_FRAME_TIMEOUT_S` (mặc định 10 s; laptop chậm và lô suy luận làm khung đầu tới
    muộn, R6), quá thì `TimeoutError` (`kind = timeout`). Chờ `sentence_played` tối đa thời lượng tiếng + `RENDERER_ACK_TIMEOUT_S`.
  - Tin `error` từ fork (ví dụ `vram_oom`) làm câu đang nói lỗi ngay với `RendererError(kind)`; `kind` vào `errors.jsonl` (FR-021).
  - `interrupt()` gửi `stop`; fork gọi `flush_talk()` (xóa hàng đợi tiếng) và chuyển về clip chờ. Đo ≤ 1 s bằng SC-004.
  - Mất kết nối `/ailive/ws` thì tự nối lại có giãn cách (1, 2, 4... tối đa 10 s); tin `hello` có `boot_id`; `boot_id` đổi nghĩa là fork
    đã khởi động lại → log `renderer_restarted` (FR-021).
- **Lý do:** FR-017, FR-021, edge case "hết bộ nhớ đồ họa hoặc bị treo". Mặc định 3 s của static quá ngắn cho lô 16 khung trên laptop.
- **Phương án đã cân nhắc:** dùng chung `RENDERER_ACK_TIMEOUT_S` (lượt nào trên laptop cũng có thể quá 3 s); hỏi `/is_speaking` theo chu
  kỳ (thêm request, không có `utterance_id`).
- **TODO:** chỉnh `LIVETALKING_FIRST_FRAME_TIMEOUT_S` theo p95 đo được ở US4.

## R11. CUDA, driver và Python của venv fork

- **Quyết định:** venv fork tạo bằng `uv venv --python 3.12` trong `vendor/livetalking/.venv`, cài theo README LiveTalking: torch 2.9.1 từ
  `https://download.pytorch.org/whl/cu128`, rồi `requirements.txt` của fork. Thử cu128 trước; nếu `torch.cuda.is_available()` sai trên
  driver 565.90 thì thử bản cu126, rồi mới tính cập nhật driver (hỏi người dùng).
- **Lý do:** LiveTalking thử trên Python 3.12, torch 2.9.1, CUDA 12.8, Ubuntu 24.04. Python 3.12 trùng ADR-020 nên không thêm phiên bản.
  Laptop: GTX 1650 Ti (Turing, sm_75), driver 565.90 (ADR-023) báo hỗ trợ tới CUDA 12.7.
- **Phương án đã cân nhắc:** WSL2 Ubuntu (giống môi trường thử của tác giả hơn, thêm một lớp cài đặt; giữ làm phương án nếu Windows lỗi);
  Docker (không có GPU passthrough dễ dàng trên Windows Home).
- **Nguồn:** README LiveTalking (mục cài đặt); ADR-020, ADR-023.
- **TODO:**
  - Bánh xe cu128 có chạy trên driver 565.90 không, và còn kèm kernel cho sm_75 không. Kiểm bằng một lệnh Python sau khi cài.
  - LiveTalking có chạy trên Windows native không (tác giả chỉ ghi Ubuntu); `aiortc` và `av` có bánh xe Windows cho 3.12 không.
  - Dung lượng tải của torch + requirements và của hai checkpoint.

## R12. Thử nhân vật riêng lẻ bằng tiếng ghi âm (FR-011)

- **Quyết định:** `POST /api/debug/speak-audio` (multipart, file WAV PCM16 mono 16 kHz) gửi thẳng tiếng vào renderer đang dùng, không
  cần show, LLM hay TTS. File khác định dạng bị từ chối với lời nhắn tiếng Việt chỉ cách đổi (quickstart dùng `soundfile` có sẵn trong
  venv fork để đổi). Trang điều khiển có ô chọn file cạnh "Nói thử" hiện có. Không lưu file lên đĩa.
- **Lý do:** FR-011, US1 kiểm thử độc lập; SC-001 cần 10 đoạn tiếng thật vì giọng giả chỉ là âm báo. Đọc WAV bằng `wave` của thư viện
  chuẩn, không thêm phụ thuộc. Endpoint debug sẵn có (`/api/debug/speak`) gọi qua `director.speak_text` với TTS, không nhận audio.
- **Phương án đã cân nhắc:** lệnh CLI nối thẳng vào fork (cần trang xem riêng của LiveTalking, khác màn hình host thật); tự đổi tần số
  mẫu trong app (cần numpy/scipy hoặc tự viết bộ lọc).

## R13. Nhân vật gắn với đúng một khách (FR-004)

- **Quyết định:** thêm biến `CUSTOMER_ID` (mã khách của phiên). `character.json` của nhân vật có `customer_id`. Ở chế độ `livetalking`,
  app từ chối khởi động khi thiếu `CUSTOMER_ID`, khi nhân vật chưa `ready`, hoặc khi `customer_id` của nhân vật khác `CUSTOMER_ID`, với
  thông báo tiếng Việt. Thư mục nhân vật chọn bằng `AVATAR_DIR`; `AVATAR_ID` (đã có) phải trùng `character_id`.
- **Lý do:** FR-004, Điều I "một AI host một tài khoản", RISKS P4. Hiện chưa có khái niệm khách trong cấu hình (chỉ `AVATAR_ID`).
- **Phương án đã cân nhắc:** sổ đăng ký host ↔ tài khoản dùng chung (RISKS P4, để mốc Multi-customer); chỉ dựa vào tên thư mục (dễ nhầm).
- **TODO:** `CUSTOMER_ID` lấy theo quy ước nào (mã shop Shopee, tên viết tắt)? Tạm dùng chuỗi tự đặt, ví dụ `demo_customer_01`.

## R14. Kiểm thử không cần GPU

- **Quyết định:**
  - App: test unit cho `CharacterManifest` (hồ sơ nguồn gốc, khách, loại clip), `SwitchingRenderer` (bộ đếm, chuyển, bật lại),
    `LiveTalkingRenderer` với **fork giả** (server WebSocket giả trong test, theo [contracts/fork-protocol.md](./contracts/fork-protocol.md)):
    ack, hết giờ, `error`, `stop`, nối lại, `boot_id`. Test tích hợp `ShowDirector` + `SwitchingRenderer` + fork giả cho SC-005 và FR-015/016.
    Contract test hiện có của `AvatarRenderer` chạy thêm cho hai renderer mới.
  - Fork: `ailive_ext/rotation.py`, `ailive_ext/ingest.py` (đổi PCM16 → khung float32 320 mẫu, gắn `datainfo`) và kiểm nhãn có test
    pytest riêng chạy trong venv fork **không cần GPU**. Phần suy luận thật kiểm bằng tay ở quickstart.
  - Không thêm marker mới cho app; mọi test app chạy mặc định.
- **Lý do:** Điều V. Fork giả dùng `websockets` (đã có trong `uv.lock` qua `uvicorn[standard]`).
- **TODO:** không có.

## R15. Khoảng lặng giữa hai câu của cùng một lượt

- **Quyết định:** `LiveTalkingRenderer.speak` mặc định giữ ngữ nghĩa của static: trả về khi có `sentence_played`. Thêm biến
  `LIVETALKING_LEAD_S` (mặc định `0` = tắt): khi > 0, `speak` trả về sớm lúc phần tiếng còn lại của câu (tính từ `playback_started` + thời
  lượng tiếng) ≤ `LIVETALKING_LEAD_S`, để lõi gửi câu kế tiếp vào hàng đợi của fork trong lúc câu trước còn phát. `is_speaking` vẫn đúng tới
  `sentence_played` của câu cuối; `interrupt` vẫn xóa mọi câu đã xếp. Chỉ bật khi số đo US4 cho thấy khoảng lặng p95 > 1,5 s.
- **Lý do:** lõi gọi `speak` lần lượt, câu sau chỉ gửi khi câu trước xong. Ở static, trình duyệt phát gần như ngay nên khoảng lặng nhỏ. Ở
  LiveTalking, câu mới phải đi qua lô suy luận (R6, ≥ 0,84 s với `batch_size` 16), nên mỗi ranh giới câu thêm chừng đó im lặng, có thể vượt
  mục tiêu lặng p95 ≤ 1,5 s của Điều VI. Trả về sớm giải quyết trong renderer, không đổi lõi hay Protocol.
- **Phương án đã cân nhắc:** lõi gửi trước câu kế tiếp (đổi `ShowDirector`/`ScriptRunner`, trái Điều IV); gộp cả lượt thành một câu với fork
  (mất ack từng câu cho phụ đề).
- ~~**TODO:** đo khoảng lặng giữa câu ở US4 với `LIVETALKING_LEAD_S=0`, rồi chọn giá trị (gợi ý bằng độ trễ khung đầu p50). Khoảng lặng này không làm nhân vật về clip chờ nhờ `LIVETALKING_HOLD_S` (R7); nếu lặng thật p95 lớn hơn `LIVETALKING_HOLD_S` thì nâng `LIVETALKING_HOLD_S` hoặc bật `LIVETALKING_LEAD_S` (T073).~~
- **Số đo (2026-11-12, T073/T075; bảng ở quickstart bước 9, mục "Thử `LIVETALKING_LEAD_S`"):** đo khoảng lặng ở chỗ Chrome nghe.
  - `LEAD_S` 0: p95 3,19 s, vượt cả `LIVETALKING_HOLD_S` 2,5 s.
  - `LEAD_S` 1,3: p95 1,96 s.
  - `LEAD_S` 2,5: p95 0,76–1,00 s, đạt.
  - Đề xuất `LIVETALKING_LEAD_S=2.5`, chờ người dùng duyệt đổi mặc định; không cần nâng `LIVETALKING_HOLD_S`.
  - Ràng buộc: câu xếp hàng chờ khung đầu lâu hơn chừng `LEAD_S`, nên `LEAD_S` phải nhỏ hơn hẳn `LIVETALKING_FIRST_FRAME_TIMEOUT_S`.
- **Sửa khi đo (2026-11-12):**
  - `LEAD_S` làm `sentence_gap` bị tính dư (tính từ lúc `speak` trả về) và làm mất số đo của câu trả về sớm.
  - Thêm `RenderTurnStats.last_played_at` và Protocol tùy chọn `RenderSettleSource` (contracts/adapters.md §2, data-model §5). Đây là
    Protocol tùy chọn, nên lõi không phụ thuộc vào renderer cụ thể.

# Nghiên cứu (Phase 0): Đưa AI host vào OBS

- **Feature ID:** `006-obs-output` · **Ngày:** 2026-11-13 · **Plan:** [plan.md](./plan.md)

## R1. Đưa hình và tiếng vào OBS bằng cách nào

- **Quyết định:** OBS **Browser Source** mở trang mới `/obs` của app. Trang này dùng lại toàn bộ đường của trang host: khung nhép miệng
  từ fork qua WebRTC (đã ghép cảnh 009 và nhãn "AI" trong fork), ảnh tĩnh + Web Audio khi về dự phòng, ack phát tiếng để giữ nhịp show.
- **Lý do:** không thêm thư viện Python, không đổi fork; giữ nguyên ảnh tĩnh dự phòng (005 FR-022) và ack `playback_started` /
  `sentence_played` mà ShowDirector, độ trễ (mốc `avatar_first_frame`) và canh show 007 đang dựa vào. OBS gom hình và tiếng của trang vào
  một nguồn ("Control audio via OBS"), nên người vận hành chỉ thêm một nguồn (SC-001).
- **Phương án đã cân nhắc:**
  - Fork `--transport virtualcam` (`streamout/virtualcam.py`, pyvirtualcam): cần thêm `pyvirtualcam` và một cáp âm thanh ảo (VB-Cable)
    cho tiếng; transport của fork loại trừ nhau nên mất WebRTC, mất ảnh tĩnh dự phòng và ack phát tiếng. Loại.
  - Fork `--transport rtmp` (`streamout/rtmp.py`, python_rtmpstream) đẩy vào một RTMP server cục bộ để OBS kéo về: thêm phụ thuộc +
    server, thêm 1–3 s trễ bộ đệm, cùng các mất mát như trên. Loại.
  - OBS "Window Capture" cửa sổ Chrome + "Application Audio Capture": hai nguồn, dễ bắt nhầm cửa sổ, Chrome thu nhỏ là đen; vẫn cần bấm
    "Bắt đầu". Loại.
  - Fork đẩy thẳng RTMP lên Shopee (không qua OBS): ngoài phạm vi spec; để dành cho `OutputSink` sau này (ARCHITECTURE §3).

## R2. Có tiếng mà không cần bấm trong OBS

- **Quyết định:** trang `/obs` tự tạo `AudioContext` và phát `<video>` ngay khi tải, không có lớp phủ "Bắt đầu".
- **Lý do:** CEF của OBS chạy với `--autoplay-policy=no-user-gesture-required`.
- **Nguồn:** `obsproject/obs-browser`, `browser-app.cpp`, hàm `OnBeforeCommandLineProcessing`:
  `command_line->AppendSwitchWithValue("autoplay-policy", "no-user-gesture-required");` (đọc 2026-11-13).
- **Hệ quả:** mở `/obs` trên Chrome thường thì `AudioContext` ở `suspended` (không có cử chỉ người dùng); trang vẫn chạy, nhịp
  `host_status` báo `audio: "suspended"` và kiểm tra trước demo báo lỗi. Không thêm nút nào vào `/obs` (FR-002). Kiểm tự động dùng Chrome
  chạy cờ `--autoplay-policy=no-user-gesture-required` để mô phỏng CEF (R10).

## R3. WebRTC trong Browser Source của OBS

- **Quyết định:** dùng `RTCPeerConnection` như trang host; kiểm thật trong OBS ở quickstart §4.
- **Lý do:** Browser Source của OBS là Chromium (CEF), có WebRTC. Các công cụ phổ biến như VDO.Ninja nhận hình qua WebRTC trong Browser
  Source. Fork nghe ở `127.0.0.1:8010`, cùng máy với OBS.
- TODO: đo trong OBS bản cài thử (ADR-059) xem `getStats().framesDecoded` có số (watchdog hình đứng cần) và tiếng của `<video>` WebRTC có
  vào mixer của OBS khi bật "Control audio via OBS" không.

## R4. Trang nào phát tiếng: vai `obs` và `host` trên `/ws/host`

- **Quyết định:** trang mở `/ws/host?role=obs` hoặc `?role=host` (thiếu hoặc lạ thì là `host`, giữ tương thích trang cũ). Renderer giữ
  một kết nối phát như cũ, thêm luật ưu tiên `obs` > `host`:
  - `obs` tới khi đang có `host`: `obs` nhận quyền phát, `host` bị đóng mã **4001** (`CLOSE_YIELDED`).
  - `host` tới khi đang có `obs`: `host` bị đóng ngay mã 4001, `obs` giữ nguyên.
  - Cùng vai tới sau: kết nối mới thắng, kết nối cũ đóng mã 4000 (`CLOSE_REPLACED`) như hiện nay (US2 #4: thêm nguồn hai lần trong OBS).
  - Trang host nhận 4001 hiện "Đang phát qua OBS, xem trong cửa sổ OBS" và không nối lại (nối lại sẽ bị đẩy ra mãi). Trang nhận 4000 giữ
    hành vi cũ.
- **Lý do:** spec FR-006, FR-007 (clarify 2026-11-13). Laptop chỉ chạy một phiên WebRTC của fork (`--max_session 1`), nên thứ tự ưu tiên
  phải cố định chứ không "ai tới sau thắng": người vận hành lỡ mở `/host` trên Chrome giữa live Shopee không được cướp tiếng của OBS.
  Luật nằm ở server nên đúng cả khi hai trang tới gần như cùng lúc.
- **Phương án đã cân nhắc:** trang thứ hai chỉ xem (không phát) — không làm được vì fork chỉ có một phiên hình; route `/obs` riêng cho
  WebSocket — trùng gần hết `/ws/host`; dựa vào `OUTPUT_MODE` để chọn trang thắng — chế độ Meet mà ai đó mở `/obs` thì sao: ưu tiên cố
  định đơn giản hơn và chế độ chỉ quyết định kiểm tra (R8).

## R5. Trang mất quyền phát phải nhả phiên WebRTC của fork

- **Quyết định:** khi `/ws/host` đóng với 4000 hoặc 4001, `host.js` (cả hai vai) đóng `RTCPeerConnection`, hủy hẹn giờ `/offer` lại, dừng
  `<video>` và Web Audio, rồi dừng hẳn.
- **Lý do:** đọc code hiện tại tìm ra lỗi tiềm ẩn: trang host bị thay chỉ dừng Web Audio (`stopAll`), còn `<video>` của fork vẫn phát và
  không bị tắt tiếng ở chế độ nhép miệng → **tiếng nói đôi** nếu trang mới cũng có hình fork; đồng thời phiên WebRTC cũ vẫn giữ chỗ duy
  nhất của fork (`--max_session 1`), trang mới gọi `/offer` bị từ chối (`{"code": -1}`) và kẹt ở ảnh tĩnh. Fork tự xóa phiên khi
  `connectionState` là `failed` hoặc `closed` (`vendor/livetalking/server/rtc_manager.py`, `on_connectionstatechange`), nên trang cũ đóng
  peer là đủ, trang mới thử `/offer` lại mỗi 2 s (`REOFFER_DELAY_MS`) sẽ vào được.
- TODO: đo thời gian từ lúc trang cũ đóng peer tới lúc fork xóa phiên (aiortc nhận DTLS close hay phải chờ ICE hết hạn). Nếu > 8 s thì
  không đạt mục tiêu "về hình nhép miệng ≤ 10 s" khi OBS nhận quyền từ trang host; khi đó đề xuất ADR sửa fork: `/offer` kèm cờ
  `ailive_takeover` đóng phiên cũ trước khi tạo phiên mới.

## R6. Tự nối lại trong phiên dài

- **Quyết định:**
  - Fork tắt/bật: như trang host (peer `failed`/`disconnected` → `/offer` lại mỗi 2 s; tin `mode` từ server chuyển ảnh tĩnh ↔ nhép miệng).
  - App tắt/bật: trang `/obs` thử nối `/ws/host` mỗi 1 s như trang host; khi nối lại được **sau một lần mất kết nối**, trang `/obs` tải lại
    chính nó (`location.reload()`) để lấy cấu hình, cảnh và phiên bản cảnh mới của lần chạy app mới. OBS cho tự phát lại nên tải lại không
    cần bấm. Trang `/host` giữ hành vi cũ (tải lại thì phải bấm "Bắt đầu").
- **Lý do:** sau khi app khởi động lại, số phiên bản cảnh (009 `scene.version`) đếm lại từ đầu; trang cũ đang giữ số lớn hơn sẽ bỏ qua tin
  `scene` mới (`onScene` chỉ nhận bản lớn hơn) và kẹt ở cảnh cũ. Tải lại là cách chắc nhất để trang khớp với app mới, và chỉ xảy ra khi app
  đã khởi động lại.
- **Giới hạn đã biết:** nếu OBS mở trang khi app chưa chạy, CEF hiện trang lỗi và không tự thử lại; runbook dặn bật app trước OBS, hoặc
  bấm "Refresh" trên nguồn. Không có cách sửa trong trang vì trang chưa tải được.

## R7. Khung hình, tỉ lệ, nhãn "AI" và phụ đề

- **Quyết định:**
  - `/obs` dùng cùng HTML/CSS với `/host`, thêm lớp `obs` trên `<body>`. CSS ẩn `#start-overlay`, `#host-status` và `#subtitle` (web) khi
    có lớp `obs`. Phụ đề trong khung (009 `SCENE_SUBTITLES`) vẫn theo cấu hình cảnh vì đó là nội dung pipeline sinh ra.
  - Tỉ lệ: `.stage.scene-on` đã giữ khung 480×832 ở giữa, phần thừa đen (009); không có cảnh thì ảnh/video `object-fit: contain`. OBS co
    nguồn thì nội dung thu nhỏ, có viền đen, không cắt (FR-004). Hướng dẫn: đặt kích thước nguồn 720×1248 (gấp 1,5 lần khung cảnh) hoặc
    480×832.
  - Nhãn "AI": như trang host. Khi đang có khung fork, nhãn nằm trong khung fork; khi ảnh tĩnh, nhãn CSS nằm trên ảnh và OBS chụp cả trang
    nên nhãn có trong khung OBS. `/obs`, như `/host`, không đọc query string (Điều I).
- **Lý do:** FR-002, FR-003, FR-004; clarify 2026-11-13 (không phụ đề trong khung OBS).

## R8. Chế độ phát `OUTPUT_MODE`

- **Quyết định:** dùng lại biến `OUTPUT_MODE` có sẵn trong `.env.example` (đang ghi `webrtc | virtualcam | rtmp`, chưa code nào đọc), đổi
  giá trị thành `meet | obs`, mặc định `meet`. `webrtc` (giá trị cũ) được hiểu là `meet` và ghi log cảnh báo một lần; `virtualcam`/`rtmp`
  làm app báo lỗi cấu hình rõ ràng lúc khởi động.
- **Lý do:** FR-014. `.env` trên máy này còn dòng `OUTPUT_MODE=webrtc`; không được sửa `.env` của người dùng, nên giá trị cũ phải chạy được.
  Chế độ chỉ quyết định kiểm tra trước demo và canh show đòi đầu ra nào; luật phát (R4) không phụ thuộc chế độ.
- **Phương án đã cân nhắc:** biến mới `LIVE_OUTPUT` — để lại `OUTPUT_MODE` cũ vô nghĩa trong `.env.example` và ARCHITECTURE. Tự phát hiện
  OBS (không cấu hình) — kiểm tra trước demo không biết phải đòi gì khi chưa mở gì.

## R9. Kiểm tra trước demo và canh show theo chế độ

- **Quyết định:**
  - Renderer biết vai của kết nối đang phát (`host_role`: `obs`, `host` hoặc None). Sự kiện `HOST_CONNECTION` thêm trường `role`.
  - Kiểm tra trước demo, mục `host`: chế độ `meet` giữ nguyên lời cũ. Chế độ `obs`: chưa nối → LỖI "Nguồn OBS chưa nối" kèm cách thêm
    nguồn; đang phát ở trang host (không phải OBS) → LỖI "Đang phát ở trang host trên Chrome, chưa phải OBS"; nối rồi nhưng
    `audio` ≠ `running` → LỖI kèm cách bật "Control audio via OBS"/tải lại nguồn.
  - Canh show: ở chế độ `obs`, "đầu ra đang nối" nghĩa là có kết nối vai `obs`; mất kết nối đó → cảnh báo `host_closed` với chữ "Nguồn OBS
    đã ngắt" và việc cần làm theo OBS (≤ 10 s, SC-007: ngưỡng `host_closed` hiện là tức thì khi socket đóng). Trang host Chrome có nhận
    quyền phát ở chế độ `obs` thì vẫn tính là đầu ra OBS mất.
  - Chữ việc cần làm của các cảnh báo khác (hình đứng, mất tiếng) đổi "tab /host … Meet" thành "nguồn OBS" khi chế độ `obs`.
- **Lý do:** FR-010–FR-012, US3. Dùng lại khung 007 thay vì thêm loại cảnh báo mới (Điều VII).

## R10. Kiểm chứng không cần người

- **Quyết định:**
  1. Test pytest (không GPU): luật vai trên renderer, route `/obs`, `/ws/host?role=`, `OUTPUT_MODE`, readiness và watchdog theo chế độ.
  2. Kiểm trình duyệt bằng Chrome DevTools MCP (Chrome chạy cờ autoplay như CEF): `/obs` tự phát, không có phần điều khiển, mở/đóng `/host`
     5 lần, tải lại khi app khởi động lại.
  3. Kiểm thật trong **OBS Studio bản portable** (ADR-059: công cụ kiểm thử, không phải phụ thuộc của app; giải nén ngoài repo ở
     `%LOCALAPPDATA%\ai-live\obs`): dựng sẵn scene collection có một Browser Source `/obs`, chạy `obs64.exe --portable --startrecording`,
     ghi ra file, rồi chấm bằng bộ tự kiểm `scripts/selfcheck/lipsync_check.py` của 005 (nhãn, khung đứng, lệch hình–tiếng).
- **Lý do:** SC-002/003/004/005 cần bản ghi từ chính OBS; người dùng không cần ngồi xem (ủy quyền làm liên tục). Show chạy `REPLY_ENGINE=fake`
  hoặc nội dung `verbatim` nên không gọi LLM free.
- Kết quả 2026-11-13: `scripts/selfcheck/lipsync_check.py` điều khiển fork rồi chấm bản ghi của chính fork (`<prefix>.mp4` + `.wav`
  + `.jsonl` cho `ailive_ext.analyze`), không nhận một file ghi ngoài. OBS portable đã dựng nhưng chưa chạy (bộ phân quyền chặn).
- TODO: muốn chấm file OBS tự động thì cần một bước tách `.wav` từ file OBS và tạo `.jsonl` giả, có đáng làm không hay chấm bằng mắt? Bộ tự kiểm đọc được file "Fragmented MP4" của OBS không (OBS 30+ có định dạng này; nếu không, ghi `.mkv` rồi remux bằng PyAV trong venv fork). Dừng ghi bằng tắt tiến trình OBS vì không thêm client obs-websocket (phụ thuộc mới).

## R11. Âm vọng và nghe thử

- **Quyết định:** hướng dẫn giữ "Audio Monitoring" của nguồn ở "Monitor Off" (mặc định của OBS); bỏ chọn "Shutdown source when not
  visible" để chuyển cảnh không làm rớt kết nối.
- **Lý do:** trường hợp biên của spec. Nếu nguồn bị tắt khi ẩn, trang bị hủy, kết nối mất và canh show báo; khi hiện lại trang tải mới và
  nối lại (R6), nên chỉ mất tiếng trong lúc ẩn.

## R12. Video dự phòng

- **Quyết định:** không đổi. App không có route nào phát file video (007 FR-021, test T044); `/obs` chỉ nhận khung realtime của fork.
- **Lý do:** Điều I, ràng buộc 1 trong CLAUDE.md.

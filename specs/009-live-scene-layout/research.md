# Nghiên cứu (Phase 0): 009 Bố cục cảnh live

> Mỗi mục: Quyết định / Lý do / Phương án đã cân nhắc. Số đo khung lấy từ các clip đã chuẩn bị của `demo_host_01` (480×832).

## R1. Trộn cảnh ở đâu

- **Quyết định:** App vẽ các lớp RGBA; fork trộn vào mỗi khung trong `process_frames` (ngay sau `ailive_fade.apply`, trước
  `cv2.putText("LiveTalking")` và `ailive_label.apply`). Ở chế độ ảnh tĩnh, app ghép ảnh tĩnh của nhân vật với cùng các lớp.
- **Lý do:** Ràng buộc số 2 đòi nhãn "AI" nằm trong khung do pipeline vẽ; đặt cảnh trước watermark và nhãn thì không lớp nào che được
  hai thứ đó. App có dữ liệu sản phẩm, font và trạng thái show, nên vẽ ở app; fork chỉ trộn mảng đã vẽ sẵn (nhanh, ít logic, ít sửa
  vendor). Một nguồn vẽ dùng chung cho hai chế độ nên khung tĩnh và khung nhép miệng giống nhau (FR-008).
- **Phương án đã cân nhắc:** (a) Ghép bằng CSS trên trang host: luồng WebRTC thì được, nhưng ra OBS/RTMP sau này sẽ mất cảnh, và trái
  ràng buộc "trong pipeline". (b) Fork tự vẽ chữ: phải mang dữ liệu sản phẩm và font sang fork, trùng logic. (c) Ghép ở OBS: phụ
  thuộc OBS, không dùng được cho Meet.

## R2. Thư viện vẽ ở app

- **Quyết định:** Pillow (`ImageDraw`, `ImageFont.truetype`, `ImageFilter.GaussianBlur`), khai báo trực tiếp trong `pyproject.toml`
  (ADR-051). Đã có 12.3.0 trong `uv.lock`, không tải thêm.
- **Lý do:** Vẽ chữ tiếng Việt có dấu đúng cần FreeType; cv2 `putText` chỉ có font Hershey không dấu. Pillow nhỏ, ổn định, đã sẵn.
- **Phương án đã cân nhắc:** cv2 trong app (phải thêm opencv, chữ không dấu); skia/cairo (phụ thuộc mới, nặng); HTML canvas trong
  trình duyệt chụp ra ảnh (phức tạp, chậm).

## R3. Font chữ tiếng Việt

- **Quyết định:** `SCENE_FONT_PATH` nếu có; nếu không thì tìm theo thứ tự `segoeuib.ttf`, `arialbd.ttf`, `segoeui.ttf` (Windows),
  `DejaVuSans-Bold.ttf` (Linux). Bật cảnh mà không có font nào thì app báo lỗi tiếng Việt rõ ràng lúc khởi động. Không tải font.
- **Lý do:** Laptop chạy Windows có sẵn Segoe UI (đủ dấu tiếng Việt, dễ đọc trên màn hình nhỏ). RunPod/Linux có DejaVu. Tải font OFL
  (Be Vietnam Pro) là tải tài sản mới, cần ADR riêng: để dành nếu cần thương hiệu.
- **Phương án đã cân nhắc:** Đóng gói font vào repo (license và kích thước); font mặc định bitmap của Pillow (không dấu, xấu).
- **Rủi ro:** license dùng font Windows trong luồng thương mại (RISKS L12).

## R4. Bố cục trong khung 480×832

- **Số đo:** mặt nằm trong y 82–304 trên mọi clip (`coords.pkl`, max y2 = 304); tay y ~700–800; nền tường trơn; ảnh tĩnh `face.png`
  832×1216 cắt phủ 9:16 thì khớp khung clip gần như hoàn toàn. Nhãn "AI" mặc định góc phải trên ~66×56 px; watermark (0,0)–(80,26).
- **Quyết định (tỉ lệ theo khung, không số cứng):**
  - Vùng cấm mặt: y < face_bottom + 8 (≈312), cả chiều ngang.
  - Mặt bàn: dải ngang từ `desk_top` = 0,76·H xuống đáy, ảnh `desk.png` phủ ngang; thiếu ảnh thì tô màu `desk_color`.
  - Sản phẩm: đáy đặt trên mép bàn (~0,83·H), cao ~0,18·H (món chính ~0,205·H), món nổi ×1,3; bóng mềm dưới đáy do app vẽ.
  - Chỗ: tối đa `max_slots` = 5; món chính ở giữa; chiều rộng chỗ theo trọng số (chính 1,25, phụ 1,0, nổi 1,5).
  - Thẻ: thẻ trắng bo góc ở mép trước bàn (~0,84·H tới đáy − 10 px), tên đậm ≤ 2 dòng, giá màu nhấn; khuyến mãi đầu tiên chỉ trên
    thẻ món nổi. Nhãn đặt góc dưới thì thẻ dời lên trên nhãn.
  - Phụ đề (US3): hộp tối mờ ở y ~0,40–0,53·H (dưới cằm, trên sản phẩm), ≤ 2 dòng.
- **Lý do:** Theo câu trả lời làm rõ: giữ host đầy khung, mọi sản phẩm bày trên bàn trước host, món đang nói to hơn. Tay host bị bàn che
  một phần là chấp nhận được và trông như đứng sau bàn thật. Các số đo thật được tinh chỉnh bằng ảnh chụp (quickstart §4).
- **Phương án đã cân nhắc:** thu nhỏ host sang một bên (đã loại khi làm rõ); kệ dọc hai bên (che mất tay và vai, chật ở 480 px).

## R5. Vùng cấm và nơi kiểm

- **Quyết định:** Kiểm hai lớp. App: bố cục không đặt gì vào vùng cấm và đục trong suốt các hộp nhãn/watermark (+4 px) trên lớp cuối.
  Fork: khi nhận `scene_layer`, từ chối (`error {kind: "scene_rejected"}`) nếu có điểm ảnh alpha > 0 trong vùng mặt, hộp nhãn hoặc hộp
  watermark mà fork tự tính; lớp cũ giữ nguyên. Fork gửi hình học thật trong `hello.scene` (face_bottom, keep_out) để app vẽ lại khớp.
- **Lý do:** Fork là chỗ cuối cùng trước khi ra hình, biết chính xác hộp nhãn (theo env của fork) và clip đang dùng, nên kiểm ở đây
  mới chắc chắn tuân thủ FR-019. App kiểm trước để lỗi hiếm khi xảy ra.
- **Phương án đã cân nhắc:** Chỉ kiểm ở app (tin vào ước lượng, sai khi env nhãn của fork khác app); fork tự cắt bớt lớp (che giấu
  lỗi cấu hình, khó gỡ).

## R6. Thời điểm đổi sản phẩm nổi

- **Quyết định:** Đổi khi renderer báo `playback_started` của câu kịch bản thuộc phân đoạn có `product_id` (Protocol mới
  `PlaybackListener`); không đổi theo sự kiện `sentence` (lúc chuẩn bị, sớm vài giây với `LIVETALKING_LEAD_S`). Bản đồ
  utterance_id → product_id lấy từ payload `sentence` (thêm `product_id`). Câu trả lời comment không có trong bản đồ nên không đổi.
  Phân đoạn chung (product_id rỗng) và show `idle`/`ended` thì bỏ nổi; `paused` giữ nguyên (FR-017).
- **Lý do:** FR-015/FR-016 đòi khớp với lúc host thật sự nói. Ack phát là mốc duy nhất khớp với hình và tiếng trên cả hai renderer.
- **Phương án đã cân nhắc:** Theo `segment_requested` (quá sớm); theo đồng hồ ước lượng (lệch khi TTS chậm).

## R7. Ảnh tĩnh và về ảnh tĩnh

- **Quyết định:** App ghép `face.png` (cắt phủ 9:16) + lớp nền + lớp phụ đề thành `GET /api/scene/still.png?v=N`; trang host đổi
  `src` khi nhận tin `scene {version}` trên `/ws/host`. Khi `SwitchingRenderer` đang ở chế độ ảnh tĩnh thì ảnh này là hình hiển thị.
  Nhãn "AI" CSS của trang host giữ nguyên (ADR-016).
- **Lý do:** FR-008: về ảnh tĩnh vẫn giữ cảnh. Dùng chung lớp đã vẽ nên không tốn thêm.
- **Phương án đã cân nhắc:** Vẽ cảnh bằng CSS cho chế độ tĩnh (hai cách vẽ, dễ lệch nhau).

## R8. Cắt nền ảnh sản phẩm thật

- **Quyết định:** Làm thủ công trên máy: Paint của Windows 11 (xóa nền chạy trên máy) hoặc GIMP; lưu PNG có nền trong suốt vào
  `products/`, ảnh gốc vào `originals/`, ghi các thao tác vào `provenance.json`. App chỉ nhận PNG/WebP có kênh alpha.
- **Lý do:** Ràng buộc số 7: ảnh sản phẩm phải là ảnh thật, chỉ chỉnh nền/cắt/cỡ/sáng. Làm tay giữ chi tiết nhãn hàng, người làm tự
  kiểm từng ảnh. Không gửi ảnh khách ra dịch vụ ngoài.
- **Phương án đã cân nhắc:** rembg (tải model, cần ADR, lỗi viền); remove.bg (gửi ảnh khách lên dịch vụ ngoài, tốn tiền sau bản free).

## R9. Ảnh mẫu cho demo

- **Quyết định:** `scripts/make_demo_scene.py` (trong git) vẽ bằng Pillow một bàn gỗ đơn giản và hình chai/tuýp phẳng có chữ
  "ẢNH MẪU" cho sản phẩm của thương hiệu giả "Mây Sáng", ghi `placeholder: true` và nguồn bàn `drawn`. Ra `assets/scenes/demo/`
  (ngoài git). Lệnh kiểm báo cảnh báo cho mỗi ảnh mẫu.
- **Lý do:** Cần bộ cảnh để test và chụp màn hình khi chưa có ảnh khách; ảnh vẽ bằng chương trình không thể bị nhầm với ảnh thật nhờ chữ
  "ẢNH MẪU". Với khách thật, ảnh mẫu bị cảnh báo và gói duyệt nhắc thay.
- **Phương án đã cân nhắc:** Ảnh AI tạo (cấm cho sản phẩm); để trống (không xem được bố cục).

## R10. Phụ đề trong khung

- **Quyết định:** Lớp riêng `subtitle`, chỉ bật khi `SCENE_SUBTITLES=true`. Đặt khi renderer báo `playback_started` (văn bản câu), xóa
  khi `playback_ended`/`playback_stopped`. Khi bật, trang host ẩn phụ đề web để không hiện hai lần.
- **Lý do:** FR-018. Lớp riêng thì đổi phụ đề không phải gửi lại lớp nền lớn.

## R11. Chi phí trộn mỗi khung

- **Quyết định:** Fork cắt lớp sát vùng alpha khác 0 (app đã cắt), lưu sẵn `premult = rgb·a` và `inv_a = 255 − a` kiểu uint16; mỗi khung
  `roi = (roi·inv_a + premult) // 255`. Trạng thái các lớp là một dict thay nguyên khối (không khóa).
- **Lý do:** Dải bàn 480×~200 px: vài trăm nghìn phép nhân uint16, ~1–2 ms trên CPU laptop. Ước lượng thật đo bằng `scene_ms`.
- **Phương án đã cân nhắc:** `cv2.addWeighted` toàn khung (tốn hơn, không có alpha từng điểm); float32 (chậm hơn uint16).

## R12. Đo và quan sát

- **Quyết định:** Fork cộng dồn thời gian trộn, `stats` thêm `scene_ms` (trung bình mỗi khung của lượt); app thêm cột `scene_ms` vào bảng
  độ trễ (FR-022). App log `scene_rendered` (phiên bản, thời gian vẽ, kích thước), `scene_highlight`, `scene_rejected`. Sự kiện bus mới
  `scene` cho trang điều khiển. `GET /api/scene` trả trạng thái và danh sách vấn đề của bộ cảnh.
- **Lý do:** Điều VIII và SC-004.

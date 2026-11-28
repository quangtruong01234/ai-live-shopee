# Nghiên cứu (Phase 0): Nền sau người dẫn giống phòng live của shop

- **Feature ID:** `014-live-host-background` · **Ngày:** 2026-11-24 · **Plan:** [plan.md](./plan.md)
- Dạng ghi: **Quyết định / Lý do / Phương án đã cân nhắc**. Chỗ chưa chắc ghi `TODO:` kèm câu hỏi.

Đầu vào đã đo trong repo (2026-11-23/24):
- Khung live của `demo_host_02` là đoạn lặp `full_imgs` của avatar fork: **81 khung, 480×832**, giống nhau ở hai thư mục
  `demo_host_02__ultralight_musetalk` và `demo_host_02__w2l_musetalk`. `character.json` hiện có `"clips": []`, nên chỉ có một vòng lặp.
- Mép bàn trên khung live ở **645 px** (`character.json` `scene.desk_top` 0.78 → 649 px). `face.png` là cảnh quay khác (mép bàn 727 px).
- Bản dựng thử (`bg_proto.py` ở scratchpad, ngoài repo): GrabCut khởi tạo bằng hình chữ nhật lọt mảng kệ cũ cạnh vai và dải LED trên
  đầu ở khung 40 (host nghiêng đầu).
- Đo trên laptop dev, khung 480×832, mặt nạ giả (2026-11-24): ghép bằng `numpy.copyto(where=...)` cả khung mất **~6,4 ms/khung**;
  `cv2.copyTo(plate, mask, frame)` cộng trộn riêng dải viền (~1,7 nghìn điểm) mất **~0,18 ms/khung**. Tính dấu vân khung `zlib.crc32`
  một khung mất **~1 ms**.

---

## R1. Ghép nền ở đâu

- **Quyết định:** thêm một **bước ghép nền mới trong fork LiveTalking**, chạy trong `process_frames` ngay **trước** `ailive_scene.apply`
  (thứ tự: khung có miệng mới → **nền** → lớp cảnh 009/013 → watermark → nhãn AI). Module mới `ailive_ext/background.py`.
- **Lý do:**
  - Khung live chỉ tồn tại trong fork (WebRTC tới `/host` và `/obs`), nên app hay trình duyệt không ghép được dưới người host.
  - Lớp cảnh 009 (`Geometry.guarded()`) cấm mọi điểm ảnh nhìn thấy trong vùng mặt `(0, 0, width, face_bottom + 8)` trên toàn bề ngang,
    mà nền phải phủ đúng vùng đó (quanh đầu, tóc). Nới luật này cho lớp cảnh sẽ phá bảo đảm "không che mặt" của 009. Nền nằm **dưới**
    người nên không che mặt; đặt thành bước riêng thì luật 009 giữ nguyên.
  - Ghép trước lớp cảnh thì sản phẩm, bóng đổ, thẻ (013) vẫn nằm trên nền, và nhãn AI vẫn trên cùng (FR-005).
  - Ghép **sau** khi dán miệng (`paste_back_frame`) vì hộp mặt được dán có thể chứa vài điểm phòng cũ ở mép. Ghép trước khi dán sẽ làm
    phòng cũ lọt lại trong hộp mặt.
  - `/obs` dùng cùng luồng khung nên giống `/host` mà không làm gì thêm (FR-014).
- **Phương án đã cân nhắc:**
  - Lớp cảnh `background` trong `scene.py`: loại vì luật vùng mặt (ở trên).
  - Ghép sẵn nền vào 81 khung gốc lúc nạp avatar (khoảng 97 MB) rồi để fork chạy như cũ: loại vì hộp mặt dán đè mang phòng cũ về, và đổi
    ảnh nền (áp bộ sản phẩm mới 012) phải dựng lại cả bộ khung.
  - Ghép trong trình duyệt bằng canvas (cần mặt nạ theo từng khung gửi qua WebRTC): loại, vì không có kênh đồng bộ khung với mặt nạ, và
    OBS Browser Source sẽ chịu thêm tải.

## R2. Tách người lúc live hay chuẩn bị sẵn

- **Quyết định:** **chuẩn bị sẵn một mặt nạ người cho mỗi khung** của mọi khung fork sẽ phát (vòng `full_imgs` và khung clip nếu có),
  chạy một lần cho mỗi nhân vật, trước giờ live. Lúc live, fork chỉ tra mặt nạ theo chỉ số khung rồi ghép.
- **Lý do:**
  - Đoạn lặp cố định (81 khung), và khung lip-sync chỉ đổi vùng miệng (luôn nằm trong vùng người), nên mặt nạ của khung gốc vẫn đúng khi
    có miệng mới.
  - Tách người lúc live tốn GPU/CPU mỗi khung trên laptop 4 GB đang chạy lip-sync (ADR-023), và mặt nạ có thể nhấp nháy giữa các khung.
  - Điều I: mặt nạ không chứa tiếng hay miệng; hình, miệng, tiếng vẫn sinh thời gian thực. Giống bước `prepare` cắt mặt sẵn của 005.
- **Phương án đã cân nhắc:** tách người theo thời gian thực (MediaPipe mỗi khung): loại vì tốn tài nguyên và nhấp nháy; chỉ cần nếu sau này có
  khung không lặp (ví dụ sinh cả người), ngoài phạm vi.

## R3. Cách tách người

- **Quyết định:** công cụ chuẩn bị có **hai cách**, cùng cho ra một kiểu mặt nạ:
  1. `plate` (mặc định khi chưa duyệt ADR-083, **không tải gì**): dựng **ảnh phòng trống** bằng trung vị theo thời gian trên 81 khung,
     dùng hiệu khung với ảnh phòng làm gợi ý người/nền, rồi GrabCut khởi tạo **bằng mặt nạ gợi ý** (không bằng hình chữ nhật như bản thử),
     giữ mảng lớn nhất, lấp lỗ.
  2. `mediapipe` (cần ADR-083 được duyệt và tải model): **MediaPipe ImageSegmenter**, ưu tiên model nhiều lớp
     `selfie_multiclass_256x256` (có lớp tóc, da, quần áo), gộp mọi lớp không phải nền thành "người".
  Sau cả hai: làm mượt theo thời gian (R4), làm mịn viền (R5), giữ mặt bàn (R6).
- **Lý do:**
  - Điều VII: thử cách không cần tải trước. Ảnh phòng trung vị biết chính xác phòng cũ trông thế nào ở chỗ host không che, nên tách tốt
    hơn GrabCut khởi tạo bằng hình chữ nhật (nguyên nhân lọt kệ cũ trong bản thử là GrabCut không biết phòng thật).
  - Nhưng chỗ host gần như không bao giờ rời (sau đầu, vai) thì ảnh trung vị chính là người, nên cách `plate` có thể vẫn lọt ở đó. Model
    tách người không phụ thuộc chuyện này. Quyết định dùng cách nào dựa vào số đo lọt (R12) trên 20 khung, không đoán trước.
  - `mediapipe` 1.2.3 **đã có trong venv fork** (ADR-053, có `tasks/python/vision/image_segmenter.py`), nên không cài gói pip mới; chỉ
    thiếu file `.tflite` (không kèm trong gói).
  - Model nhiều lớp có lớp tóc riêng, giúp chỗ tóc mảnh (trường hợp biên của spec).
- **Giấy phép:**
  - Hướng dẫn chính thức của Google liệt kê SelfieSegmenter (256×256, 144×256) và model nhiều lớp (nền, tóc, da người, da mặt, quần áo,
    phụ kiện) [1].
  - Model card ML Kit selfie segmentation (2/2021) nêu Apache 2.0 [2]. Bản đăng lại của Qualcomm ghi giấy phép "other" [3][4].
  - `TODO:` đọc model card **chính thức của MediaPipe** cho đúng file `selfie_multiclass_256x256.tflite` (và `selfie_segmenter.tflite`)
    trước khi tải: giấy phép có cho dùng thương mại không, có điều kiện ghi công không? Chưa xác nhận thì không tải (RISKS L16).
  - `TODO:` ghi kích thước và sha256 của file `.tflite` khi tải (sau khi ADR-083 được duyệt).
- **Phương án đã cân nhắc:**
  - GrabCut khởi tạo bằng hình chữ nhật (bản thử): loại, lọt kệ cũ.
  - IS-Net / DIS5K (model bỏ nền 013): loại, bộ dữ liệu huấn luyện chỉ cho nghiên cứu (RISKS L15).
  - BiRefNet, RobustVideoMatting, MODNet: chất lượng viền tốt hơn nhưng nặng hơn hoặc cần kiểm giấy phép trọng số riêng; chưa cần cho
    81 khung 480×832. Giữ làm phương án nếu cả hai cách trên không đạt SC-001/SC-002.
  - Dịch vụ tách nền trả phí (remove.bg…): loại, tốn phí và gửi hình người mẫu ra ngoài (Điều II).
- **Bổ sung: vật trong phòng dính mép người (2026-11-24, sửa lỗi theo WORKFLOW §2, người dùng: "sửa luôn đốm cam cạnh tay áo đi"):**
  - **Lỗi:** một chai cam trên kệ cũ dính mép ngoài tay áo phải ở mọi khung (R12). Bước cắt cầu nối không tách được vì mép tay áo đung đưa
    nối chai với người theo cách khác nhau ở mỗi khung.
  - **Cách sửa:** bước `drop_still_room()` chạy sau R4, cho cả hai cách tách:
    - Điểm ảnh **không bao giờ đổi** so với ảnh phòng trung vị được chia thành mảng (nối 4 hướng). Chai cam đứng yên; mép tay áo thì
      chuyển động nên cắt rời chai khỏi thân.
    - Bỏ một mảng khi: không phải mảng lớn nhất, chạm phòng, và ≥ 35 % điểm của nó (trên ảnh phòng trung vị) có màu giống phòng gấp
      > 2 lần giống người.
    - Biểu đồ màu phòng/người **gộp cả vòng lặp**, không tính từng khung: tính từng khung thì chai cam lúc 0,63, lúc 0,0 phần giống phòng.
    - Bỏ kèm các điểm chuyển động có màu giống phòng trong 8 px quanh mảng đó (nửa chai nằm trong vùng tay áo đung đưa).
    - Sau đó chỉ giữ khối lớn nhất, **không lấp lỗ**: lấp lỗ sẽ trả lại khe phòng cũ giữa tay và người.
  - **Số đo trên `demo_host_02`:** mảng chai có ≥ 50 % điểm giống phòng ở cả 81 khung. Đầu, đuôi tóc và các mẩu áo đứng yên đều ≤ 10 %.
  - **Kết quả:** hết chai cam ở cả hai vòng lặp, mép tay áo không đổi; số cờ lọt không đổi (R12).
  - **Test:** 3 test mới, gồm một cảnh tổng hợp chai cam dính tay áo đung đưa và một đầu đứng yên. Test chai cam fail khi tắt bước này.
- **Bổ sung: viền màu của áo (2026-11-25, sửa lỗi theo WORKFLOW §2, người dùng: "có vệt bọc xung quanh khiến lúc hiện trắng hiện vàng ở
  màu áo"):**
  - **Lỗi:** GrabCut xếp viền cam ở cổ áo phải và gấu hai tay áo của `demo_host_02` vào phòng cũ, vì phòng cũng tông be/vàng. Ngay từ mặt
    nạ thô, tầm 12 % điểm viền đã ở ngoài. Chỗ đó lộ nền mới (kệ trắng/đỏ), mỗi khung một khác, nên viền áo lúc trắng lúc cam.
  - **Cách sửa:** bước `refill_trim()` chạy ngay sau `drop_still_room`:
    - Chỉ xét điểm ảnh mà phép đóng nhỏ (`TRIM_CLOSE_PX` = 4, hình elip) thêm vào, tức điểm kẹp giữa hai phần người.
    - Lấy lại điểm nào có độ bão hoà HSV > `TRIM_MIN_SAT` (90). Phòng cũ nhạt màu: trung vị 21.
    - Vì vậy khe phòng nhạt giữa tay và người vẫn là phòng, vật màu ngoài bóng người không bị lấy. Dải bàn không đụng tới, không lấp lỗ.
  - **Số đo trên `demo_host_02`:** mỗi khung đổi 281–813 điểm (trung bình 550). Cờ lọt 20 → 19 khung, mảng lọt lớn nhất vẫn 214 px (R12).
    Đốm cam cạnh tay áo không quay lại.
  - **Phương án đã cân nhắc:** quay/tạo lại host trên phông xanh rồi tách bằng chroma key. Bị loại vì phải tạo lại ảnh và video host, huấn
    luyện lại Ultralight và khử ánh xanh trên tóc (ADR-083 đã loại phương án phông xanh). Lỗi nằm ở bước tách, không nằm ở màu phông.
  - **Test:** 3 test mới, gồm viền cam 3 px giữa tay áo và cánh tay, khe phòng nhạt, vật màu cách xa và dải bàn.

## R4. Ổn định theo thời gian

- **Quyết định:** sau khi có mặt nạ thô từng khung, lấy **trung vị của 3 khung liền kề** (vòng lặp nối đầu-cuối, vì khung 80 nối về khung 0)
  trên xác suất người, rồi mới cắt ngưỡng. Khung clip làm mượt trong từng clip.
- **Lý do:** viền nhấp nháy giữa các khung dễ thấy hơn một viền hơi lệch nhưng đứng yên. Host cử động chậm (25 khung/giây), nên 3 khung
  (~0,12 s) không làm trễ viền đáng kể.
- **Phương án đã cân nhắc:** optical flow để dời mặt nạ theo chuyển động: phức tạp hơn mức cần cho đoạn lặp ngắn, giữ làm phương án nếu
  vẫn còn nhấp nháy.

## R5. Làm mịn viền

- **Quyết định:** **guided filter** tự viết bằng numpy + `cv2.boxFilter` (bán kính khoảng 4 px, eps nhỏ) dùng khung gốc làm ảnh dẫn, rồi
  co mặt nạ 1 px trước khi làm mềm, để viền theo đúng tóc và vai mà không mang quầng phòng cũ (FR-004). Mặt nạ lưu dạng ảnh xám 8 bit
  (0 = nền, 255 = người, giữa = viền mềm).
- **Lý do:** OpenCV trong venv fork **không có** `cv2.ximgproc` (đã kiểm), nên không dùng `guidedFilter` có sẵn. Guided filter chỉ cần
  vài phép `boxFilter`, chạy lúc chuẩn bị nên không ảnh hưởng tốc độ live.
- **Phương án đã cân nhắc:** Gaussian blur mặt nạ (bản thử): viền mềm đều nhưng không bám tóc, tạo quầng; matting đầy đủ (closed-form): chậm
  và thừa cho cỡ khung này.
- **Bổ sung: mép tóc (2026-11-24, sửa lỗi theo WORKFLOW §2):**
  - **Lỗi gặp:** người dùng thấy "tóc đằng sau hơi bị vỡ" trên `/host` với nền "kệ hàng".
  - **Nguyên nhân:** GrabCut và bước mở (opening) bỏ các sợi tóc mảnh của đuôi tóc. Sau đó viền mềm SNAP 16 cắt cứng chỗ còn lại.
  - **Cách sửa:** thêm `hair_edge()` trong `background_prep.py`, chạy sau `soften()`, trước `desk_ramp()`. Gần tóc, alpha được đọc lại
    từ màu theo "đường màu":
    - B = màu phòng mờ quanh điểm, F = màu tóc mờ trong lõi người.
    - alpha = vị trí của điểm trên đoạn B→F.
  - **Cổng chặn** (mỗi cổng sinh ra từ một lỗi thấy trên `demo_host_02`):
    - chỉ trong dải 8 px quanh viền và trên đường vai (`shoulder_row`, + 4 px);
    - tương phản |F−B| > 80, sai số so với đường màu < 25 (35 lấy nhầm chai xanh ngọc cạnh tai);
    - F tối (luma < 110): cạnh da thì kệ trắng thành bóng mờ;
    - F cùng tông màu với tóc ở đỉnh đầu (lệch < 20): áo xanh navy cạnh vai lệch 36;
    - ngoài mặt nạ cũ chỉ lấy điểm có alpha ≥ 0.5 và nối liền với người: điểm rời là đốm phòng.
  - **Kết quả:** đuôi tóc giữ được sợi tóc; viền vai, áo và mẩu chai cam không đổi (alpha y như trước).
  - **Kiểm thử:** 6 test mới trong fork `tests/test_background_prep.py`: sợi tóc được giữ; chai cạnh vai, áo xanh đậm, đốm rời và người
    không có vai thì không đổi.

## R6. Giữ mặt bàn

- **Quyết định:** từ mép bàn trở xuống luôn giữ khung gốc: mặt nạ được nâng lên 255 bằng một dốc 6 px quanh mép bàn. Mép bàn tính bằng px từ
  `character.json` `scene.desk_top` (0.78 → 649 px) và **ghi vào manifest** (`desk_top_px`) lúc chuẩn bị; lúc live fork dùng đúng số đã ghi.
- **Lý do:** FR-005 và giả định "mặt bàn trong khung gốc luôn giữ nguyên". Bản thử với dốc `clip((y - (DESK - 3)) / 6, 0, 1)` cho viền bàn
  tự nhiên. Lấy từ `character.json` để cảnh 013 (sản phẩm đứng trên mép bàn) và nền cùng một mốc.
- **Phương án đã cân nhắc:** tự dò mép bàn trên khung (như `realism_report.py`): công cụ dò từng bắt nhầm cạnh kệ (611 px thay vì 645), nên
  chỉ dùng để cảnh báo trong báo cáo, không dùng để cắt.

## R7. Gắn mặt nạ với đúng khung (khớp / không khớp)

- **Quyết định:** manifest lưu **dấu vân của từng khung** (`zlib.crc32` của bytes ảnh BGR đã giải mã) cùng cỡ khung và số khung. Lúc nạp
  avatar, fork tính dấu vân cho từng khung của `frame_list_cycle` (và khung clip nếu có) và tra mặt nạ theo dấu vân. Thiếu bất kỳ khung nào
  hoặc khác cỡ thì trạng thái là `mismatch` và **không dùng nền** (FR-010, US2 kịch bản 2).
- **Lý do:**
  - Đoạn lặp được làm lại (trường hợp biên) thì bytes khung đổi, nên dấu vân bắt được mà không cần so tên file.
  - Hai thư mục avatar `w2l` và `ultralight` có cùng `full_imgs`, nên một bộ mặt nạ dùng được cho cả hai (demo giữ Wav2Lip theo ADR-066).
  - 81 khung × ~1 ms = ~0,1 s lúc khởi động, không ảnh hưởng live.
- **Phương án đã cân nhắc:** so theo tên file hay số khung: không phát hiện được khung bị làm lại cùng tên; sha256: chậm hơn mà không cần
  chống giả mạo.

## R8. Ghép nhanh mỗi khung

- **Quyết định:** khi nạp, mỗi mặt nạ được tách sẵn thành (a) mặt nạ nhị phân "nền" (alpha = 0) cho `cv2.copyTo(plate, mask, frame)`, và
  (b) chỉ số phẳng + alpha của dải viền (0 < alpha < 255). Mỗi khung: copy nền bằng `cv2.copyTo`, trộn dải viền bằng số nguyên `uint16`
  (cùng cách `Layer.from_bgra` của 009). Mục tiêu **≤ 4 ms/khung** (10% của 40 ms ở 25 khung/giây), đo bằng `stats.background_ms`.
- **Lý do:** số đo ở đầu file: ~0,18 ms/khung với `cv2.copyTo`, so với ~6,4 ms nếu dùng `numpy.copyto(where=...)`. Dư nhiều cho SC-003.
  Bộ nhớ: 81 mặt nạ × 400 KB ≈ 32 MB, chấp nhận được.
- **Phương án đã cân nhắc:** trộn float cả khung: chậm; ghép trên GPU (torch): thêm chuyển dữ liệu qua lại, không cần.

## R9. Ảnh nền gửi vào fork

- **Quyết định:** app vẽ **một ảnh nền phẳng** (RGB, đúng cỡ khung fork, không trong suốt), đã áp độ mềm và độ sáng, rồi gửi một lần qua
  WebSocket bằng tin mới `scene_background` (PNG base64, giới hạn 4 MB như lớp cảnh). Fork giữ ảnh đó; chỉ gửi lại sau `hello` mới hoặc khi
  vẽ lại (áp bộ sản phẩm mới). Không có công tắc bật/tắt khi live (spec, làm rõ 2026-11-24).
- **Lý do:** ảnh nền đứng yên (spec: không nền động), nên vẽ một lần là đủ. App đã có Pillow, ảnh sản phẩm đã bỏ nền (012/013), dữ liệu bộ
  cảnh và kênh WebSocket tới fork (`set_scene_layer`), nên đặt phần vẽ ở app giữ fork mỏng.
- **Phương án đã cân nhắc:** fork tự vẽ kệ hàng: fork không có dữ liệu sản phẩm và bộ cảnh; gửi đường dẫn file thay vì bytes: fork và app có
  thể chạy hai máy (RunPod), không dùng chung ổ đĩa.

## R10. Vẽ "kệ hàng" (cách vẽ đổi bởi ADR-086: dãy kệ có chiều sâu, xếp kín mọi tầng)

- **Quyết định:** module app mới `src/ai_live/scene/backdrop.py`, vẽ bằng Pillow + numpy theo bản thử: tường sáng ấm, hai khoang tủ, 4 tầng kệ
  trên mép bàn, dải LED ấm dưới mỗi tầng, bóng tầng kệ, sản phẩm trên kệ là **ảnh đang dùng (active) của các món đang nạp** (012), lặp vòng
  theo thứ tự món, phủ nhẹ 20% màu tường (xa máy ảnh), cao theo tỷ lệ thật (món sau nhỏ hơn món 013 trên bàn). Không vẽ chữ, giá, logo nào
  (FR-007). Sau đó làm mờ `softness_px` và nhân độ sáng (R11).
- **Lý do:** bản thử cho kết quả hợp chủ đề nhất (spec, bối cảnh). Vẽ từ ảnh đã có, không cần dữ liệu mới từ khách. Shop có một món thì kệ
  lặp lại món đó (trường hợp biên).
- **Phương án đã cân nhắc:** ảnh kệ có sẵn tải trên mạng: không có quyền dùng và có hàng của bên khác; sinh ảnh bằng AI: ngoài phạm vi.

## R11. Khớp ánh sáng và độ mềm (nhân sáng tuyến tính và `softness_px` 3,0 đổi bởi ADR-086: đường cong gamma, 1,5)

- **Quyết định:**
  - Lúc chuẩn bị, công cụ đo trên khung gốc và ghi vào manifest: độ sáng trung bình và chênh R−B của **vùng người** và của **phòng cũ** quanh
    người.
  - App chỉnh ảnh nền để độ sáng trung bình của nền gần độ sáng phòng cũ (host được chiếu sáng cho phòng đó) nhân `brightness`, và dời cân
    bằng trắng về chênh R−B của phòng cũ, giới hạn ±12 (ngưỡng màu ánh sáng của skill realism).
  - Mặc định `softness_px` = **3,0** (bán kính Gaussian trên khung 832 px), `brightness` = **0,95**: số của bản thử 2026-11-23, sẽ chỉnh
    bằng công cụ đo (US4). Khoảng cho phép: `softness_px` 0–8 (0 = tắt), `brightness` 0,8–1,1.
- **Lý do:** FR-006. Khung host là video mềm, nền sắc hơn người trông như dán. Luật 013 FR-006 cấm đổi màu **sản phẩm**; ở đây đổi màu
  **nền** để hợp với người là đúng mục đích.
- **Phương án đã cân nhắc:** gray-world trên cả khung: làm lệch màu sản phẩm trên kệ quá mức; không chỉnh gì: nền trắng lạnh sau người được
  chiếu đèn vàng trông như dán.

## R12. Ngưỡng "lọt phòng cũ" cho SC-001

- **Quyết định:** chỉ số lọt (US4, FR-016), heuristic:
  - Xây hai biểu đồ màu từ khung gốc: **phòng cũ** (điểm cách người ≥ 40 px, trên mép bàn) và **người** (điểm sâu ≥ 24 px trong mặt nạ).
  - Điểm lọt: điểm được **giữ từ khung gốc** (alpha ≥ 128) trong dải 24 px sát viền người, có màu giống phòng cũ hơn hẳn giống người
    (tỉ lệ khả năng > 4).
  - Gom thành mảng liền (8 hướng). **Cờ khi có mảng > 150 px** (trên khung 480×832, khoảng 12×12 px, thấy được ở cỡ điện thoại); kèm ảnh
    đánh dấu đỏ.
  - SC-001 đạt khi 20 khung không có cờ **và** mắt người duyệt (chủ dự án) không thấy mảng lọt.
- **Lý do:** không có "đáp án đúng" cho từng khung, nên đo bằng màu: phòng cũ (kệ trắng, LED vàng, cây xanh) khác màu áo và da. Ngưỡng 150 px
  chọn theo cỡ mảng kệ lọt trong bản thử (lớn hơn nhiều) và cỡ một chi tiết nhỏ nhất thấy được trên điện thoại.
  `TODO:` đo lại ngưỡng 150 px và tỉ lệ 4 trên 20 khung demo khi có mặt nạ thật; đổi trong `realism_report.py` nếu mắt không đồng ý.
- **Đo trên khung thật (T032, 2026-11-24, `demo_host_02`, `plate`, 162 khung):**
  - Lần chạy đầu: **162/162 khung có cờ**, mảng lớn nhất 791 px. Hai nguyên nhân:
    - Bao lồi chuyển động gồm cả dải bàn rộng hết khung nên phình thành hình thang. Vì vậy chậu cây và kệ phòng cũ ở hai góc ngay trên
      mép bàn bị giữ lại (lọt thật).
    - Biểu đồ màu BGR 8 ngăn/kênh xếp da má ấm chung ngăn với tường kem nên má bị đánh dấu lọt trên mọi khung (cờ sai).
  - Đã sửa trong `background_prep.py`:
    - bao lồi chỉ lấy từ chuyển động của người phía trên mép bàn, chiếu thẳng xuống mép bàn;
    - lề quanh bao lồi 12 → 6 px (12 giữ một mẩu chai trên kệ cạnh khuỷu tay);
    - bỏ phần GrabCut giữ ngoài lề;
    - cắt cầu nối mảnh ≤ 4 px;
    - biểu đồ màu đổi sang Lab 8 ngăn/kênh.
  - Lần chạy sau: **14/162 khung có cờ**, mảng lớn nhất **204 px**. Mắt xem: các mảng > 150 px nằm ở **vệt sáng trên trán** sát chân tóc,
    tức cờ sai. Lọt thật còn lại đều < 100 px: một mẩu chai cam cạnh khuỷu tay phải và một vệt 2–3 px phòng cũ ngay trên mép bàn bên phải.
  - Ngưỡng 150 px / tỉ lệ 4 **chưa đổi**: chờ người duyệt xem `review.jpg` (T033) rồi quyết.
- **Duyệt `review.jpg` (T033, 2026-11-24, Claude duyệt thay theo lời nhờ của người dùng):**
  - Xem đủ 162 ô và phóng to khung 0, 9, 69, 150. Đầu, tóc, vai, hai tay đủ, không bị khoét người. Không còn mảng kệ hay chậu cây.
  - Cờ ở 14 khung đều là vệt sáng trên trán sát chân tóc (cờ sai), đúng như ghi ở trên.
  - **Lọt thật còn lại:** một mẩu chai cam trên kệ cũ, khoảng 16×10 px, dính liền mép ngoài tay áo phải (quanh x 420–437, y 494–506) ở
    **mọi khung**. Nó nối với tay áo qua một đoạn cao ~10 px, dày hơn bước cắt cầu nối, và cùng màu viền cam của áo nên GrabCut giữ lại.
    Ở cỡ điện thoại nó trông như một mẩu viền tay áo. Chấp nhận cho demo.
  - Hai trường hợp biên của spec (giơ tay, nghiêng người ra ngoài) **không có** trong khung của `demo_host_02` (host luôn đan tay trên
    bàn), nên chưa kiểm được.
  - Ngưỡng giữ 150 px / tỉ lệ 4. ~~`TODO:` người dùng xem lại mẩu cam cạnh tay áo~~: người dùng không chấp nhận ("sửa luôn đốm cam
    cạnh tay áo đi"), đã sửa bằng bước `drop_still_room` (R3, mục "Bổ sung: vật trong phòng dính mép người").
- **Duyệt lại sau khi sửa mép tóc (R5, 2026-11-24):**
  - Chạy lại `background-prepare demo_host_02`: 162 khung, **20/162 khung có cờ**, mảng lớn nhất **214 px**. Trước khi sửa là 14 cờ,
    lớn nhất 204 px.
  - So ảnh duyệt cũ và mới ở khung 17, 24, 69, 105, 150: chấm đỏ nằm đúng chỗ cũ (đỉnh tóc và chân tóc, cổ áo, mép tay áo phải).
  - Cờ tăng vì mảng báo nhầm trên tóc to thêm khoảng 10 px nên vượt 150 px ở vài khung. Không có mảng lọt mới.
  - Mẩu chai cam cạnh tay áo phải giữ nguyên (alpha y như trước), vẫn chấp nhận cho demo.
  - Đánh dấu duyệt lại: `reviewed_by` = "Claude (người dùng nhờ duyệt T033, sửa mép tóc)".
  - `TODO:` chỉ số lọt đọc tóc tối thành phòng cũ. Nên loại vùng tóc khỏi phép đo, hay nâng ngưỡng riêng cho đỉnh đầu?
- **Duyệt lại sau khi bỏ mẩu chai cam (R3, 2026-11-24):**
  - Chạy lại `background-prepare demo_host_02`: vẫn **20/162 khung có cờ**, mảng lớn nhất **214 px** (cờ nhầm trên tóc như trên).
  - Đếm trên mặt nạ đã lưu, ô chai cam (x 428–437, y 494–505): còn tối đa 1 px ở 2/162 khung, các khung khác sạch. Xem 8 khung trải đều
    hai vòng lặp: mép tay áo phải nguyên, không khoét người.
  - Mỗi khung bỏ thêm 105–207 px; ngoài chai cam chỉ có vài mẩu phòng thật dính mép người (cửa sổ sáng sau vai, lá cây cạnh tay trái).
  - Đánh dấu duyệt lại: `reviewed_by` = "Claude (người dùng nhờ duyệt T033, bỏ đốm cam)".
- **Phương án đã cân nhắc:** so với mặt nạ vẽ tay (ground truth): tốn công cho từng nhân vật; so với ảnh phòng trung vị: sai ở chỗ người
  luôn che (R3).

## R13. Ảnh xem trước trên trang điều khiển

- **Quyết định:** công cụ chuẩn bị lưu thêm **một khung mẫu** (`preview_frame.png`, khung 0 của vòng lặp) và mặt nạ của nó. App dựng ảnh xem
  trước = khung mẫu + ảnh nền theo mặt nạ + lớp `base` của cảnh 009/013 + nhãn AI, mà không cần fork chạy (giả định của spec). Endpoint
  riêng `GET /api/scene/background/preview.png`.
- **Lý do:** FR-012 cần ảnh xem trước cả khi fork chưa chạy. Khung mẫu nằm trong thư mục nhân vật (gitignored), không đưa vào git.
- **Phương án đã cân nhắc:** chụp khung từ fork qua WebRTC: cần fork chạy; dùng `face.png`: là cảnh quay khác, xem trước sai.

## R14. Ảnh tĩnh `face.png` và chế độ `static`

- **Quyết định:** 014 **không** chuẩn bị nền cho `face.png`, nên `AVATAR_MODE=static` và ảnh tĩnh `/api/scene/still.png` giữ nguyên.
- **Lý do:** trường hợp biên của spec cho phép ("nền chỉ áp khi ảnh đó cũng đã được chuẩn bị nền, nếu không thì giữ nguyên ảnh"). Demo chạy
  fork lip-sync; chế độ tĩnh chỉ dùng để test logic.
- **Phương án đã cân nhắc:** tách người cho `face.png` bằng cùng công cụ: làm sau nếu cần (một ảnh thêm vào manifest).

## R15. "Bảng shop" và "ảnh shop" (US3; ảnh shop làm 2026-11-28, ADR-100)

- **Quyết định (thiết kế nhẹ, chưa làm trong demo):**
  - Tên shop: thêm mục tuỳ chọn "Tên shop: …" trong phần đầu file dữ liệu (trước sản phẩm đầu tiên); `ProductCatalog.shop_name: str | None`.
    Không có thì bảng không chữ và có cảnh báo `background_no_shop_name` (US3 kịch bản 2).
  - Màu bảng: `accent_color` đã có trong `scene.json`.
  - Ảnh shop: lưu ở `assets/scenes/<scene_id>/background/shop_photo.<ext>` kèm `shop_photo.json` (`confirmed_by`, `confirmed_at`, sha256),
    xác nhận quyền dùng như ảnh sản phẩm 012; phủ kín bằng cắt giữa giữ tỷ lệ (cover crop).
- **Lý do:** đúng các câu trả lời làm rõ (tên shop từ file dữ liệu, không nhập trên trang). Chỉ mô tả đủ để task sau demo không phải
  thiết kế lại.
- **Phương án đã cân nhắc:** ô nhập tên shop trên trang điều khiển: bị loại khi làm rõ.
- **Cập nhật 2026-11-28 (ADR-100):** ảnh shop làm trước bảng shop. `shop_photo.json` có thêm `source` (`photo` / `ai_generated`) và
  `original_name`. Ảnh do AI tạo được dùng nếu là cảnh shop chung (không người, không sản phẩm của khách, không logo đọc được) và luôn
  mềm ít nhất 4 px. Bước xác nhận làm bằng lệnh CLI `shop-photo`; route tải trên trang điều khiển (T064) để sau.

## R16. Kiểm thử không GPU

- **Quyết định:**
  - App: test `backdrop.py` (chỉ dùng ảnh sản phẩm có trong dữ liệu, không chữ, đúng cỡ), loader khối `background`, logic rơi về (thiếu
    manifest, `mismatch`, không có ảnh sản phẩm, fork không hỗ trợ), endpoint trạng thái và xem trước, readiness `check_background`, renderer gửi
    `scene_background` sau `hello` (WebSocket giả của 005).
  - Fork (`ailive_ext/tests`, pytest trong venv fork, không cần model): `background.apply` trên khung tổng hợp (vùng nền thay đúng, vùng
    người giữ nguyên từng bit, viền trộn đúng), dấu vân khớp/không khớp, tin `scene_background` hợp lệ/sai cỡ/`null`, tự về phòng gốc khi ghép lỗi.
  - Công cụ chuẩn bị: test cách `plate` trên chuỗi khung tổng hợp (người là hình elip di chuyển trên nền có vân); cách `mediapipe` bỏ qua
    (`skip`) khi không có file `.tflite`.
- **Lý do:** Điều V. Logic ghép chạy trên CPU với khung giả; chỉ bước đo fps thật (SC-003) và duyệt bằng mắt (SC-001/002/005) cần fork chạy.

---

## Nguồn

1. [Image segmentation guide, Google AI Edge (MediaPipe)](https://developers.google.com/edge/mediapipe/solutions/vision/image_segmenter/index)
2. [ML Kit Selfie Segmentation model card (2/2021)](https://developers.google.cn/static/ml-kit/images/vision/selfie-segmentation/selfie-model-card.pdf?authuser=1)
3. [Qualcomm, MediaPipe-Selfie-Segmentation trên Hugging Face](https://huggingface.co/qualcomm/MediaPipe-Selfie-Segmentation)
4. [Qualcomm AI Hub, mediapipe_selfie](https://aihub.qualcomm.com/models/mediapipe_selfie)

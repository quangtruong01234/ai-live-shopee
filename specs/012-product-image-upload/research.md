# Nghiên cứu (Phase 0): 012-product-image-upload

Mọi quyết định dựa trên code hiện có (đọc 2026-11-20): bộ nạp cảnh `scene/loader.py`, `SceneController` (`scene/controller.py`), route
`PUT /api/content` (`app/routes.py`), `DocxProductStore` (`products/store.py`), sự kiện `sentence` (`director/script_runner.py`),
`build_state` (`app/context.py`), `/ws/control` (`app/ws.py`, chuyển mọi sự kiện bus trừ `host_status`). Không cần tài liệu bên ngoài:
chỉ dùng Pillow (đã có, ADR-051) và FastAPI (đã có).

## R1. Nơi lưu ảnh tải lên

- **Quyết định:** lưu trong bộ cảnh của khách, thư mục riêng `SCENE_DIR/uploads/`:
  - `uploads/<product_id>/<version_id>.png`: một file cho mỗi phiên bản; `version_id` = 12 ký tự hex đầu của SHA-256 của PNG đã chuẩn
    hóa (R2), nên tải lại đúng ảnh cũ thì dùng lại phiên bản cũ, không nhân bản file.
  - `uploads/images.json`: sổ ảnh (data-model §2): khách, và cho từng sản phẩm: trạng thái đang dùng (một phiên bản, "đã gỡ", hoặc "ảnh
    của bộ cảnh 009"), lịch sử để hoàn tác, thông tin từng phiên bản (lúc tải, lúc áp, lúc xác nhận). Ghi nguyên tử: file tạm cùng thư mục
    rồi `os.replace`.
  - Bộ nạp cảnh đọc `images.json` trước: sản phẩm có trạng thái trong sổ thì sổ quyết định; sản phẩm không có trong sổ thì giữ đúng luật
    009 (`products/<id>.png|.webp` + `provenance.json`).
- **Lý do:**
  - Bộ cảnh 009 đã là chỗ lưu dữ liệu ảnh của một khách, nằm ngoài git (`assets/scenes/` đã gitignore), được bước kiểm bộ cảnh và lệnh
    `python -m ai_live.scene check` đọc. Lưu ở đây thì FR-012 (mở lại phiên vẫn còn ảnh) có sẵn, không cần chỗ lưu thứ hai.
  - Không chép đè `products/<id>.png`: file đó do người làm bộ cảnh đặt tay, có mục `provenance.json` riêng; ghi đè thì mất ảnh gốc của
    bộ cảnh và lịch sử hoàn tác.
  - Một file JSON nhỏ đổi trong một lần `os.replace` nên áp bộ mới (R7) ghi mọi ảnh trong một bước: hoặc thành công cả, hoặc không đổi gì.
- **Phương án đã cân nhắc:**
  - Chép ảnh vào `products/` và tự sinh mục `provenance.json`: đụng file người làm bộ cảnh quản lý, mất hoàn tác, và `provenance.json` đòi
    `original` (ảnh gốc) mà spec đã bỏ (làm rõ 2026-11-20).
  - SQLite: thêm phụ thuộc vận hành cho vài chục bản ghi (Điều VII).
  - Chỉ giữ trong bộ nhớ: trái FR-012.

## R2. Kiểm và chuẩn hóa ảnh lúc tải lên

- **Quyết định:** kiểm ngay khi nhận file, trong luồng phụ (`asyncio.to_thread`), theo thứ tự rẻ trước:
  1. Cỡ file ≤ 10 MB (`MAX_IMAGE_BYTES` của 009): xét `Content-Length` rồi đếm khi đọc thân, quá thì dừng đọc → `too_large`.
  2. `Image.open` (chỉ đọc đầu file): không mở được → `bad_image`; định dạng ngoài PNG/WEBP/JPEG/MPO → `bad_format`.
  3. Cạnh dài ≤ 4000 px (`MAX_IMAGE_SIDE`) xét trên `im.size` trước khi giải mã → `too_big`.
  4. Ảnh động: `getattr(im, "n_frames", 1) > 1` với PNG/WEBP → `animated`. Riêng **MPO** (JPEG nhiều ảnh của điện thoại, Pillow mở JPEG
     chụp từ nhiều máy Android/iPhone ra định dạng này) dùng khung đầu như JPEG thường.
  5. `ImageOps.exif_transpose` để xoay đúng chiều ảnh điện thoại (trường hợp biên "ảnh chụp có thông tin xoay").
  6. Đổi sang RGBA. Ảnh không có kênh alpha (JPEG, PNG RGB) trở thành RGBA đặc: vẫn nhận, ghi `has_alpha=false` để trang cảnh báo
     "ảnh còn nền" (FR-004).
  7. Ảnh gần như trong suốt: số điểm có alpha > 0 dưới 1% tổng số điểm → `empty` (trường hợp biên "trong suốt hoàn toàn hoặc gần như
     trống"; 009 chỉ bắt trường hợp trong suốt hoàn toàn).
  8. Cắt theo vùng alpha > 0 (như `_load_art` 009) rồi thu cạnh dài ≤ 1280 px, lưu PNG.
  Mỗi lần từ chối trả mã + câu tiếng Việt (contracts/api.md §6), không ghi gì xuống đĩa.
- **Lý do:**
  - Cùng giới hạn với 009 nên ảnh nào tải lên được thì mở lại phiên cũng nạp được (giả định của spec).
  - Ảnh trên bàn tối đa 640 px (`ART_MAX_SIDE`, khi nổi được phóng 1,3 lần trong ô của layout); giữ 1280 px là dư cho cỡ nổi mà file
    nhỏ, nạp lại nhanh (R5, rủi ro Q39).
  - Lưu PNG RGBA thống nhất nên bộ nạp cảnh không phải biết ảnh gốc là JPEG hay WebP; luật "phải có alpha" của 009 tự đạt.
  - `layout.compute_layout` đã giữ tỷ lệ theo `art_sizes`, nên ảnh còn nền hiện nguyên khung, không méo (FR-004), không cần code vẽ mới.
- **Phương án đã cân nhắc:**
  - Giữ nguyên file gốc của người dùng: bộ nạp phải xử lý JPEG, EXIF, MPO mỗi lần nạp, và luật `no_alpha` của 009 sẽ chặn JPEG.
  - Tự cắt nền: ngoài phạm vi (spec), cần model mới.
  - Ngưỡng "gần như trống" theo vùng bao alpha thay vì số điểm: một chấm mờ ở góc làm vùng bao rộng mà ảnh vẫn trống; đếm điểm chắc hơn.
    Ngưỡng 1% là mặc định của plan, đặt hằng số trong code; đổi khi thử với ảnh thật.

## R3. Cách gửi file ảnh lên

- **Quyết định:** thân request là nội dung file thô (`Content-Type` của file), tên file gửi trong header `X-Filename` mã hóa phần trăm,
  giống hệt `PUT /api/content` (001 research R13). Trang điều khiển đọc `File` từ `<input type="file">` và gửi bằng `fetch(..., {body: file})`.
- **Lý do:** không thêm phụ thuộc. `python-multipart` chỉ có trong `uv.lock` dưới dạng phụ thuộc gián tiếp, chưa khai báo; dùng nó phải có
  ADR (CLAUDE.md). Mỗi lần chỉ gửi một ảnh nên không cần multipart.
- **Phương án đã cân nhắc:** multipart form (cần ADR phụ thuộc); base64 trong JSON (to hơn 33%, vẫn phải giới hạn cỡ).

## R4. Xem trước

- **Quyết định:** `SceneController.preview(catalog, overrides, highlight)` vẽ một khung tĩnh trong luồng phụ: bản sao `SceneSet` với ảnh của
  sản phẩm đang xem đổi sang ảnh ứng viên (`dataclasses.replace(scene, art=...)`), rồi `compute_layout` → `render_base` → `compose_still`
  với ảnh mặt host như `still.png`, đúng hàm vẽ của live nên cùng cỡ và vị trí (FR-008). Không đụng `_base`, `_layout`, `version` hay fork.
  Ảnh ứng viên đi qua cùng hàm đọc ảnh tải lên của bộ nạp (cắt alpha, thu 640 px) để xem trước khớp với ảnh sẽ nạp. Trang đặt
  `/api/scene/preview.png` cạnh `/api/scene/still.png` (ảnh đang live). Với bộ chuẩn bị (`target=staging`) vẽ cả bàn với catalog và ảnh
  của bộ chuẩn bị. Khi cảnh tắt (`ctx.scene` là None) API trả 409 `scene_disabled`; trang chỉ hiện ảnh nhỏ của file kèm câu "cảnh đang tắt,
  ảnh chưa hiện trên live" (trường hợp biên).
- **Lý do:** dùng lại toàn bộ đường vẽ 009 (vùng cấm, bóng, thẻ) nên xem trước đúng như live mà không viết bộ vẽ thứ hai. Vẽ base 009 đo
  `scene_ms` trung vị 4,66 ms; cả khung tĩnh 1080p kèm mã hóa PNG ước vài chục đến vài trăm ms, trong ngân sách 1 s.
- **Phương án đã cân nhắc:** ghép ảnh trên trình duyệt bằng canvas: phải chép lại luật bố cục và vùng cấm sang JS, dễ lệch với live.

## R5. Áp ảnh lên live trong ≤ 2 s

- **Quyết định:**
  - `ProductImageStore.apply(pid, vid, confirmed_at)` giữ một `asyncio.Lock`, sửa sổ trong bộ nhớ rồi ghi `images.json` (luồng phụ) bằng
    file tạm + `os.replace`. Ghi lỗi (đầy ổ, quyền) thì sổ trong bộ nhớ quay về như cũ, trả 500 `save_failed`, live giữ ảnh cũ (FR-011).
  - Sau khi ghi, gọi `SceneController.reload()` (mới): đặt `_reload = True`, `_mark()`, rồi chờ tới khi một lần vẽ **bắt đầu sau lời gọi**
    vẽ xong (đếm thế hệ vẽ), trả `version` mới. Route trả `to_frame_ms` = từ lúc nhận request tới lúc lớp `base` đã chuyển cho renderer
    (`set_scene_layer`; fork áp ở khung kế tiếp, 009 không có ack), và log `scene_image_changed`.
  - Nhiều lần áp gần nhau dồn vào một lần nạp lại (vòng `_work` của 009 đã gộp `_dirty`); sổ ghi theo thứ tự khóa nên lần áp sau cùng thắng,
    và lần nạp lại nào bắt đầu sau lần ghi cuối đều đọc sổ mới nhất (trường hợp biên "hai lần áp gần nhau").
  - Phát sự kiện bus `scene` kind `image_changed` (`product_id`, `action`, `active`) để mọi tab trang điều khiển tải lại khung ảnh (trường hợp
    biên "hai tab").
- **Ước tính thời gian:** ghi JSON < 10 ms; nạp lại bộ cảnh đọc lại mọi ảnh của các sản phẩm đang có (≤ 5 món, ảnh tải lên ≤ 1280 px:
  vài chục ms mỗi ảnh); vẽ base vài ms đến vài chục ms; tổng ước 0,1–0,5 s, trong ngân sách 2 s. Ảnh bộ cảnh 009 lớn (tới 4000 px) có thể
  làm nạp lại chậm hơn: đo `to_frame_ms` ở quickstart; nếu vượt 1 s thì thêm bộ nhớ đệm ảnh đã giải mã theo (đường dẫn, mtime, cỡ) trong
  bộ nạp (rủi ro Q39). Chưa làm trước khi đo (Điều VII).
- **Lý do:** đường "CONTENT_REPLACED → nạp lại bộ cảnh → vẽ base → `set_scene_layer`" đã chạy và đã đo ở 009 (FR-013 của 009, ≤ 2 s);
  feature này chỉ thêm một cách kích hoạt nó. Vẽ trong luồng phụ nên không chặn vòng sự kiện; đường câu → tiếng không đổi (Điều VI).
- **Phương án đã cân nhắc:**
  - Thay riêng ảnh của một sản phẩm trong `SceneSet` đang có, không nạp lại: nhanh hơn nhưng có hai đường tạo `SceneSet`, dễ lệch với lần
    mở phiên sau (FR-012); chỉ làm nếu đo thấy chậm.
  - Phát `CONTENT_REPLACED` giả: làm show director tưởng file nội dung đổi.

## R6. Luật nguồn gốc cho ảnh tải từ trang điều khiển (đổi hợp đồng 009) → ADR-071

- **Quyết định:** với sản phẩm mà `images.json` chọn một phiên bản tải lên, bộ nạp **không** đòi mục trong `provenance.json` hay ảnh gốc
  (009 FR-002, mã `missing_provenance`, `missing_original`). Thay vào đó phiên bản đó phải có `rights_confirmed_at`; thiếu thì lỗi mới
  `missing_confirmation` và **không vẽ ảnh đó** (chỉ thẻ), để SC-003 "0 ảnh lên live khi thiếu xác nhận" đúng cả khi ai sửa sổ bằng tay.
  `images.json` ghi `customer_id` lúc tạo (từ `CUSTOMER_ID`); khác khách của phiên thì `customer_mismatch` như `scene.json` (bộ cảnh không
  dùng được, 009). Sổ hỏng (JSON lỗi, sai schema) → lỗi `bad_uploads`, bỏ qua cả sổ và dùng luật 009 cho mọi sản phẩm.
  Ảnh bộ cảnh 009 (không có trong sổ, hoặc trạng thái "kit") giữ nguyên luật 009.
- **Lý do:** spec bỏ hồ sơ nguồn và ảnh gốc (làm rõ 2026-11-20, FR-005) nhưng vẫn đòi bước kiểm bộ cảnh chấp nhận ảnh khi mở lại phiên.
  Lúc xác nhận là bằng chứng duy nhất còn lại nên phải bắt buộc ở bộ nạp, không chỉ ở API. Khóa chặt hơn (không vẽ) vì đây là điều kiện
  tuân thủ (ràng buộc 8), khác `missing_provenance` của 009 chỉ là cảnh báo kiểm trước demo.
- **Phương án đã cân nhắc:** tự sinh mục `provenance.json` với `original` trỏ chính ảnh tải lên: giả hồ sơ, đi ngược mục đích FR-002 của 009.

## R7. Bộ chuẩn bị và "Áp dụng bộ mới" một lần → ADR-072

- **Quyết định:**
  - `StagedSet` (một bộ duy nhất, trong bộ nhớ của app): catalog đọc bằng `store.parse` (đã có, không `install`), tên file, lúc tạo, và
    cho từng sản phẩm của file mới một gán ảnh tùy chọn `{version_id, rights_confirmed_at, assigned_at}`. Tải ảnh cho bộ chuẩn bị dùng chung
    `POST /api/scene/uploads` (R2) rồi gán; sản phẩm chưa có trong catalog live vẫn tải được (thư mục `uploads/<pid>/`).
  - Trạng thái ảnh mỗi món của bộ chuẩn bị: gán trong bộ chuẩn bị > ảnh đang dùng trong sổ (kể cả của sản phẩm không có trong catalog live,
    FR-014) > ảnh bộ cảnh 009 dùng được > thiếu. Trang hiện "dùng lại ảnh cũ" cho hai nguồn giữa.
  - "Áp dụng bộ mới": thiếu ảnh mà không có `confirm_missing=true` → 409 `missing_images` kèm danh sách tên món (FR-015, trang hỏi lại).
    Khi áp: `async with scene.hold():` (mới; giữ khóa mà vòng vẽ lấy quanh mỗi `_redraw`, chờ lần vẽ đang chạy xong) → ghi một lần
    `images.json` với mọi gán (mỗi món: gán của bộ chuẩn bị chỉ thắng nếu `assigned_at` mới hơn lần đổi gần nhất của món đó trong sổ, trường
    hợp biên "thay ảnh giữa lúc chuẩn bị") → `store.install(staged.catalog)` → `director.on_catalog_replaced` (đường 001/004 có sẵn) → thả
    khóa, đặt `_reload` và chờ một lần vẽ. Vì không lần vẽ nào chạy giữa lúc đổi sổ và đổi catalog nên không có khung hình trộn (FR-015,
    SC-006). Ghi sổ lỗi → không `install`, trả 500, live giữ bộ cũ; `install` lỗi → khôi phục sổ cũ (đã giữ bản trong bộ nhớ) rồi trả lỗi.
  - Thành công: bỏ bộ chuẩn bị, log `scene_staging_applied` (số món, số món thiếu ảnh, `to_frame_ms`), sự kiện `scene` kind `staging`.
  - Hủy: bỏ bộ chuẩn bị; file ảnh và phiên bản đã tải vẫn còn (FR-015a).
  - Nạp file nội dung theo cách cũ (`PUT /api/content`) giữa lúc chuẩn bị: bộ chuẩn bị giữ nguyên; trang thấy `catalog.version` live đổi
    và ghi "bộ đang live đã đổi" (trường hợp biên).
- **Lý do:** vòng vẽ 009 đọc `store.catalog` mỗi lần vẽ và chỉ nạp lại bộ cảnh khi nhận `CONTENT_REPLACED` qua bus (bất đồng bộ). Nếu
  `install` xong mà một lần vẽ do phụ đề chen vào trước khi sự kiện tới, nó vẽ thẻ mới với ảnh cũ: đúng khung hình trộn FR-015 cấm. Khóa
  vẽ là cách nhỏ nhất để hai thay đổi lên cùng một lần vẽ. Bộ chuẩn bị chỉ trong bộ nhớ vì spec chỉ cần nó trong một buổi; ảnh (thứ tốn
  công) đã lưu xuống đĩa ngay lúc tải.
- **Phương án đã cân nhắc:**
  - Nạp file mới ngay rồi gán ảnh dần: người dùng đã chọn "chuẩn bị đủ rồi áp một lần" (làm rõ 2026-11-20).
  - Lưu bộ chuẩn bị xuống đĩa để sống qua lần khởi động lại: thêm trạng thái phải dọn, chưa có nhu cầu.
  - Cho phép nhiều bộ chuẩn bị: spec chỉ cần một.

## R8. Hoàn tác và gỡ ảnh

- **Quyết định:** mỗi sản phẩm trong sổ có `active` và `history` (ngăn xếp trạng thái trước, tối đa 20). Trạng thái là một trong:
  `version_id`, `null` (đã gỡ), `"kit"` (ảnh bộ cảnh 009). Lần đầu một sản phẩm vào sổ, trạng thái trước của nó là `"kit"` (bộ nạp sẽ dùng
  file `products/` nếu có, nếu không thì như chưa có ảnh). Áp ảnh: đẩy `active` cũ vào `history`, đặt `active` mới. Gỡ: như áp với `null`
  (trang hỏi xác nhận, FR-017). "Về ảnh trước": lấy phần tử cuối của `history` làm `active`, không đẩy gì (FR-016); `history` rỗng → 409
  `nothing_to_revert`. Mọi thao tác đi qua cùng đường ghi sổ + nạp lại của R5. Phiên bản quay về là `version_id` thì phải có
  `rights_confirmed_at` (đã có từ lần áp trước).
- **Lý do:** một thao tác, ≤ 2 s, và cả "về ảnh bộ cảnh ban đầu" lẫn "về trạng thái chưa có ảnh" đều hoàn tác được.
- **Phương án đã cân nhắc:** chỉ lưu "ảnh trước" một mức: hoàn tác hai lần thì mất ảnh cũ hơn; chọn phiên bản bất kỳ từ danh sách: spec chỉ
  cần một thao tác, để sau.

## R9. Giữ phiên bản ảnh

- **Quyết định:** giữ mọi phiên bản đã tải, không dọn tự động. Trang hiện số phiên bản và tổng dung lượng thư mục `uploads/` trong phần chi
  tiết; dọn bằng tay (xóa thư mục `uploads/<pid>/` khi app tắt) ghi trong quickstart.
- **Lý do:** ảnh ≤ 1280 px PNG, vài trăm KB đến ~2 MB mỗi file, vài sản phẩm, giai đoạn demo (giả định của spec). Dọn tự động có rủi ro xóa
  ảnh còn trong `history`. Giữ phiên bản cũ cũng là bằng chứng khi có khiếu nại (Q37).
- **Phương án đã cân nhắc:** giữ N phiên bản gần nhất mỗi sản phẩm: cần luật không xóa phiên bản còn trong `history` hay đang dùng; để khi
  dung lượng thành vấn đề (M2).

## R10. "AI vừa nói" (US4)

- **Quyết định:**
  - `SpokenLog`: một subscriber của bus, giữ `deque(maxlen=100)` các câu từ sự kiện `sentence` **có `segment_id`** (câu kịch bản; câu trả
    lời bình luận không có khóa này). Mỗi mục: `utterance_id`, `text`, `segment_id`, `product_id`, tên sản phẩm (tra catalog lúc nhận, vì
    catalog có thể đổi sau), `topic`, `ts`.
  - `script_runner` thêm khóa `topic` (`segment.topic.value`) vào payload `sentence`: khóa mới, client cũ bỏ qua. Sự kiện này phát ngay trước
    khi câu được đọc và **sau** guard (câu bị guard chặn phát `guard_blocked`, không phát `sentence`), nên "không gồm câu bị chặn" (FR-020)
    có sẵn. Câu bị bỏ trước khi phát (tạm dừng, bỏ đoạn) cũng không phát `sentence` vì `_skip_item` kiểm trước.
  - `build_state` thêm `spoken` (mới nhất trước) để tải lại trang vẫn thấy (FR-021). Trang điều khiển chèn đầu danh sách khi nhận sự kiện
    `sentence` có `segment_id` qua `/ws/control` (đã chuyển mọi sự kiện bus), nên trễ chỉ là một lượt WebSocket (≤ 1 s, FR-020).
  - Vòng đệm xóa khi bắt đầu show mới (`show_state` → `running` từ `idle`/`ended`); giữ sau khi show kết thúc ("vừa kết thúc").
- **Lý do:** 100 > 50 câu tối thiểu, bộ nhớ không đáng kể; không đọc lại nhật ký phiên từ đĩa.
- **Câu bị ngắt giữa chừng:** một câu đã phát `sentence` rồi bị dừng (người vận hành bấm dừng) vẫn nằm trong danh sách; nhật ký phiên cũng
  ghi nó là đã bắt đầu. SC-007 so với các câu "đã phát" trong nhật ký phiên, cùng mốc nên khớp.
- **Phương án đã cân nhắc:** đọc lại nhật ký phiên JSONL khi tải trang: chậm dần theo độ dài show, phải lọc; thêm `topic` bằng cách tra
  `segment_id` ở phía `SpokenLog`: phải với vào trạng thái của director, phụ thuộc chéo.

## R11. Chi tiết sản phẩm (US4)

- **Quyết định:** `GET /api/content/products/{pid}` (catalog live) và `GET /api/content/staging/products/{pid}` (bộ chuẩn bị) trả nguyên văn
  các trường của `Product` trừ `link` (spec FR-022: không cần hiện; `link` 001 cũng không bao giờ được nói). Hàm `product_detail(product)` ở
  `products/` để hai route và test dùng chung. Trang điều khiển mở khi bấm vào tên sản phẩm, hiện dạng bảng; không qua LLM.
- **Lý do:** dữ liệu đã nằm trong `Catalog` sau `parse`; chỉ cần đưa ra. Tách route thay vì nhét vào `/api/state` để trạng thái gửi qua
  WebSocket không phình theo cỡ file nội dung.
- **Phương án đã cân nhắc:** gửi cả catalog trong `/api/state`: mỗi lần tải lại và mỗi tab mới đều nhận toàn bộ FAQ, không cần.

## R12. Khách và an toàn đường dẫn

- **Quyết định:**
  - FR-007: mọi route ghi ảnh từ chối 409 `customer_mismatch` khi bộ cảnh đang dùng không thuộc khách của phiên (`scene.json` hoặc
    `images.json` ghi khách khác `CUSTOMER_ID`, tức `SceneSet.unusable` như 009). Không route nào nhận `SCENE_DIR` hay khách từ request.
  - `product_id` phải khớp `^[a-z0-9]+(-[a-z0-9]+)*$`, dài ≤ 120 ký tự: đúng dạng `_slug` của `docx_loader.py` sinh ra (bỏ dấu,
    chữ thường, mọi đoạn ký tự khác `[a-z0-9]` thành một `-`, bỏ `-` hai đầu). `version_id` khớp `^[0-9a-f]{12}$`. Sai → 400 `bad_id`
    trước khi ghép đường dẫn. Đường dẫn cuối cùng còn được kiểm nằm trong `SCENE_DIR/uploads/` (như `_inside` của 009).
  - Tên file người dùng (`X-Filename`) chỉ lưu làm thông tin hiển thị (`source_name`), không dùng làm đường dẫn.
  - Chỉ chấp nhận áp ảnh cho sản phẩm có trong catalog live (route ảnh live) hay trong bộ chuẩn bị (route gán bộ chuẩn bị): trường hợp biên
    "sản phẩm không còn trong file" → 404 `unknown_product`.
- **Lý do:** trang điều khiển không có đăng nhập (giả định của spec, như nạp file nội dung), nên ranh giới an toàn là thư mục bộ cảnh và
  khách cố định của phiên.

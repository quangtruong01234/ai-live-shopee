# Nghiên cứu (Phase 0): Sản phẩm đứng trên bàn như đồ thật

- **Feature:** `013-realistic-desk-products` · **Ngày:** 2026-11-22 · **Plan:** [plan.md](./plan.md)
- Định dạng mỗi mục: Quyết định / Lý do / Phương án đã cân nhắc. Chỗ chưa chắc ghi `TODO:` kèm câu hỏi.

## R1. Cách bày "như thật": chọn ở đâu và đặt từng món thế nào

**Quyết định.**
- `scene.json` thêm `layout.mode`: `"rows"` (009, mặc định) hoặc `"realistic"`. Bộ cảnh cũ không có khóa này chạy y như trước (FR-001,
  US1 #6). Đổi cách bày là sửa file rồi mở lại phiên, như mọi khóa `layout` khác của 009.
- Hàm mới `compute_realistic_layout(...)` trong `scene/layout.py`, cùng đầu vào và cùng kiểu trả về `SceneLayout` như `compute_layout`
  (009), nên `SceneController`, xem trước và `render_base` chỉ cần chọn hàm theo `layout.mode`.
- Dữ liệu vào: `desk_y = desk_top × H` (mép bàn, R2), `hands_zone` (R2), vùng cấm 009 (mặt từ cằm trở lên, nhãn "AI", watermark), cỡ ảnh
  từng món. Mặt bàn nhìn thấy là dải `band = H − desk_y`.
- Hai **khoảng đặt**: trái = `[lề, hands_x1 − khe]`, phải = `[hands_x2 + khe, W − lề]` (lề 12 px, khe 8 px, theo hằng số 009).
- **Chỗ đứng** cố định theo thứ tự trong file (`slot_order` của 009: món chính trước rồi các món phụ). Mỗi chỗ có: bên, vị trí ngang (tỷ lệ
  trong khoảng đặt của bên đó), độ sâu (đáy = `desk_y + depth × band`) và chiều cao mục tiêu (tỷ lệ `H`). Giá trị đầu, lấy từ bản dựng thử
  2026-11-22 (khung 480×832, mép bàn 722 px, dải bàn 110 px):

  | Chỗ | Món | Bên (người xem) | Ngang trong khoảng đặt | Độ sâu | Cao mục tiêu |
  |-----|-----|-----------------|------------------------|--------|--------------|
  | P | món chính | phải | 0,20 | 0,64 | 0,25 H |
  | S1 | phụ thứ 1 | trái | 1,00 | 0,56 | 0,21 H |
  | S2 | phụ thứ 2 | trái | 0,00 | 0,40 | 0,19 H |
  | S3 | phụ thứ 3 | phải | 1,00 | 0,32 | 0,17 H |
  | S4 | phụ thứ 4 | trái | 0,45 | 0,24 | 0,15 H |

  Sửa 2026-11-23 trên khung live thật (`demo_host_02`, ảnh Coca): cao mục tiêu cũ (0,154 H…) cho sản phẩm bé hơn bàn tay; ngang trong
  khoảng đặt dãn ra hai đầu (S1 sát tay, S2 sát mép khung) vì 0,62/0,25 làm hai món phụ bên trái chồng nhau ở mọi cỡ.

  Món sau nhỏ hơn và đáy cao hơn (lùi về sau) theo đúng FR-004. Bản dựng thử đặt hai món phụ ở (70, +44, cao 120) và (128, +62, cao 104),
  tức món phụ nhỏ hơn lại ở trước; bảng trên đổi lại cho khớp FR-004. Số chỗ tối đa vẫn là `layout.max_slots` (giới hạn 5 ở cách bày này).
  TODO: người dùng duyệt vị trí bằng ảnh chụp (quickstart US1); hằng số chỉnh trong `layout.py`, không đưa ra file cấu hình.
- **Cỡ:** chiều rộng = tỷ lệ ảnh × chiều cao (không méo, FR-004). Thu nhỏ (giữ tỷ lệ) khi: đỉnh lên quá vùng mặt (`face_zone` của 009, tức
  cằm + 8 px); món tràn ra ngoài khoảng đặt của bên đó; hoặc hộp món (cộng lề bóng và lề ánh sáng làm nổi, R3) chạm vùng cấm hay vùng tay.
  Cao còn dưới `MIN_ART_HEIGHT` (0,06 H, 009) thì không đặt và báo `too_wide`/`no_room` như 009 và 012.
- **Hai món chồng nhau:** cho phép món trước che chân món sau; nếu phần bị che quá nửa diện tích món sau thì thu cả hai thêm 10% mỗi bước
  tới khi hết, không được thì bỏ món sau và báo `no_room`.
- **Cỡ theo FR-004 (2026-11-23):** món sau bị chặn ở cỡ lớn nhất mà vẫn thấp hơn hoặc nhỏ diện tích hơn mọi món đứng trước nó (cao mảnh
  sau hộp dẹt được; lấn cả hai chiều thì không).
- **Bên chật (2026-11-23):** một bên còn chồng nhau hoặc mất món thì cả bên đó thu theo bậc 1,0 / 0,9 / 0,8 / 0,7 / 0,6 của cao mục tiêu
  tới khi sạch; giữ kết quả mất ít món nhất, rồi không phải thu ép, rồi tổng diện tích lớn nhất.
- **Lật bên (2026-11-23):** tính thêm bố cục soi gương (mọi chỗ đổi bên, ngang → 1 − ngang); chọn bản soi gương khi món chính ở đó được
  vẽ ≥ 1,15 × diện tích và không mất thêm món. Chọn bên trước khi làm nổi, nên đổi món đang nói không làm các món nhảy bên.
- **Thứ tự vẽ:** đáy cao (xa) vẽ trước, đáy thấp (gần) vẽ sau, nên món trước luôn đè món sau. Món đang nổi không đổi thứ tự (khác 009, nơi
  món nổi vẽ cuối) vì đồ thật ở sau không nhảy ra trước.
- **Chỉ có 1 món:** đứng ở chỗ P (phải), bên trái trống; lật sang trái theo luật lật bên ở trên.
- **Nhân vật không có bàn trong ảnh (FR-009):** vẽ mặt bàn như `_draw_desk` của 009 ở `desk_top` của bộ cảnh, rồi bày như trên.

**Lý do.** Bảng chỗ đứng cố định dễ đoán, dễ kiểm bằng test, đúng ảnh mẫu Shopee (món hai bên tay, có gần có xa). Dùng chung `SceneLayout`
nên không phải sửa renderer fork, `punch` hay luồng lớp `base` của 009.

**Phương án đã cân nhắc.** Thuật toán xếp tự do (tối ưu khoảng trống): khó đoán, khó duyệt bằng ảnh. Cho người vận hành kéo thả: ngoài
phạm vi spec. Đặt món chính ở giữa (009): che đúng tay host, là lỗi spec muốn sửa.

## R2. Vạch mép bàn và vùng tay

**Quyết định.**
- Vạch mép bàn giữ như 011: `character.json` → `scene.desk_top` (tỷ lệ chiều cao khung). Sửa `demo_host_02` từ 0,78 về giá trị đo trên
  ảnh (bản dựng thử đo được khoảng 0,868; task chốt con số bằng lớp gỡ lỗi, sai lệch ≤ 1% H, FR-010).
- `character.json` → `scene` thêm `hands_zone: [x1, y1, x2, y2]`, tỷ lệ khung (0–1), `x1 < x2`, `y1 < y2`. Đo một lần khi làm nhân vật,
  không tự dò tay (Giả định của spec). Thiếu thì dùng vùng mặc định `[0.30, desk_top − 0.10, 0.70, 1.0]` và đưa ra cảnh báo
  `hands_zone_missing` (FR-003); kiểm tra trước demo hiện cảnh báo đó.
- Ở cách bày "như thật", vùng tay là **vùng cấm của bố cục**: hộp món, bóng, ánh sáng làm nổi, thẻ không được chạm (FR-007). Không thêm vùng
  tay vào `punch` (đục trong suốt) vì ở nhân vật không có bàn trong ảnh, đục mặt bàn vẽ thêm sẽ để lộ một lỗ; thay vào đó bố cục từ chối mọi
  hộp chạm vùng tay và test kiểm điểm ảnh của lớp `base` trong vùng tay chỉ có mặt bàn (hoặc trong suốt).
- `FrameGeometry` thêm trường `hands_zone: Box | None` (điểm ảnh), tính từ tỷ lệ khi khung có kích thước thật (từ fork hoặc ước lượng).
- **Lớp gỡ lỗi khi xem trước (FR-008):** mở rộng `draw_debug_zones` của 009: vẽ vạch mép bàn (ngang, màu xanh lá) và khung vùng tay (màu
  tím) chồng lên ảnh xem trước. Chỉ ở `GET /api/scene/preview.png?debug=1` và `python -m ai_live.scene preview --debug-zones` (cờ đã có của 009), không bao giờ vào
  lớp gửi fork.

**Lý do.** Khai tay rẻ, chắc chắn, đã có tiền lệ `desk_top`; mỗi nhân vật chỉ đo một lần. Vùng tay trong bố cục (không đục) giữ đúng hành
vi bàn vẽ thêm của 009.

**Phương án đã cân nhắc.** Dò tay bằng model tư thế (MediaPipe…): thêm phụ thuộc, ngoài phạm vi. Vạch mép bàn nghiêng/cong: ngoài phạm vi
(spec, trường hợp biên). Đục vùng tay: lộ lỗ ở bàn vẽ thêm.

## R3. Bóng đổ, chỉnh sáng, làm nổi

**Quyết định.**
- **Bóng (FR-005):** hai lớp mờ dưới đáy mỗi món, vẽ trước món: (a) bóng tiếp xúc hẹp, rộng 0,9 × bề rộng món, cao 6 px, mờ 3 px, độ đậm
  140/255; (b) bóng mềm rộng 1,25 × bề rộng, cao 0,10 × chiều cao món, mờ 8 px, độ đậm 70/255. Lề bóng được tính vào hộp kiểm vùng cấm
  (R1); hộp này là hai elip có tâm ở giữa đáy. Hằng số do người dùng duyệt bằng ảnh chụp.
  Sửa 2026-11-23: bóng vẽ theo **đường đáy thật** của ảnh: mỗi cột lấy điểm thấp nhất còn đặc (alpha ≥ 128), cột ngoài ảnh lấy đáy của cột
  đặc gần nhất. Mỗi lớp là một dải dọc theo đường đáy: phần nằm sau đáy cao 0,5 × chiều cao lớp, phần lộ ra trước đáy chỉ 0,5 (tiếp xúc) và
  0,3 (mềm). Bóng tiếp xúc chạy tới 0,55 × bề rộng tính từ giữa. Lý do: thùng chụp xéo có đáy nghiêng, nên elip nằm ngang ở hàng thấp nhất
  để lại khe mặt bàn dưới góc trái, và nửa elip lộ ra trước đáy làm món trông như bay. Viền nửa trong suốt của ảnh đã bỏ nền (alpha < 200)
  được tô lại bằng màu phần đặc kề bên lúc vẽ, ảnh gốc giữ nguyên; không tô thì viền trắng sót lại thành vệt sáng giữa món và bóng.
- **Chỉnh sáng (FR-006):** `scene.json` → `layout.brightness` (0,85–1,10, mặc định 1,0). Nhân đều ba kênh R, G, B với cùng một hệ số
  (`ImageEnhance.Brightness`), giữ nguyên kênh alpha. Nhân đều không đổi tỷ lệ giữa các kênh nên không đổi sắc độ, trừ điểm ảnh bị cắt ở 255
  khi làm sáng; vì vậy giới hạn trên chỉ 1,10. Test: với điểm ảnh không bị cắt, sắc độ (hue HSV) trước và sau lệch ≤ 1°. Không dùng tông ấm
  của bản dựng thử (R×1,02, B×0,95) vì đó là đổi màu.
- **Làm mờ món không nổi:** giữ cơ chế 009, hệ số 0,85 như 009 (lùi rõ, vẫn đọc được, US3 #4). Bản đầu dùng 0,92; duyệt 2026-11-23 trên
  khung thật thấy món nổi không tách khỏi món khác.
- **Làm nổi (FR-022):** ánh sáng dịu màu trắng ấm (255, 240, 210), mờ 12 px, độ đậm 230/255 (009 dùng màu nhấn, 200/255). Cỡ tăng
  `layout.highlight_scale`; ở cách bày "như thật" mặc định 1,08, giới hạn 1,00–1,10. Bản đầu 120/255 và 1,04: duyệt 2026-11-23 trên
  khung thật thấy ánh sáng kem gần như vô hình trên bàn gỗ sáng (thử 120, 170, 230, 255), nên món nổi tách ra chủ yếu nhờ cỡ và món
  khác tối đi. Món nổi vẫn bị chặn theo FR-004 (không lấn món đứng trước nó). Phóng **neo ở giữa đáy** nên đáy vẫn đứng đúng mặt bàn.
  Bố cục khi có món nổi được kiểm vùng cấm như khi không có (009 đã tính bố cục lại theo `highlight`).

**Lý do.** Hai lớp bóng cho cảm giác đặt trên mặt bàn tốt hơn một elip của 009 (bản dựng thử). Chỉnh sáng nhân đều là cách duy nhất chắc
chắn không đổi màu. Phóng neo đáy giữ FR-002.

**Phương án đã cân nhắc.** Bóng theo hướng đèn thật, phản chiếu trên bàn: ngoài phạm vi. Tự chỉnh sáng theo độ sáng mặt bàn: khó kiểm,
dễ làm tối ảnh đã chụp chuẩn; để mức chỉnh tay trong bộ cảnh.

## R4. Chế độ thẻ

**Quyết định.**
- `scene.json` → `layout.cards`: `"none"` | `"one"` | `"all"`. Mặc định theo cách bày: `"realistic"` → `"none"` (FR-019), `"rows"` →
  `"all"` (giữ nguyên 009, US1 #6). Với `"rows"` chỉ nhận `"all"`; khóa khác giá trị thì cảnh báo `cards_ignored` và dùng `"all"`.
- `"all"` ở cách bày "như thật": thẻ ngay dưới đáy từng món, thu theo bề rộng món như `card_text` 009; thẻ chạm món khác hay vùng tay thì
  bỏ thẻ món đó và báo cảnh báo `card_no_room` (thẻ không quan trọng bằng món).
- `"one"`: chỉ vẽ thẻ của món đang nổi (`highlight`), nên tự hiện/ẩn theo câu đang phát đúng luật 009 FR-015–FR-017 (lớp `base` đã được vẽ lại
  mỗi lần đổi món nổi). Phân đoạn chung → không có món nổi → không thẻ (US3 #1).
- **Vị trí thẻ "one":** ở phía trên các món cùng bên với món đang nói, trong dải trống giữa phụ đề (009: 40–48,5% H) và đỉnh món cao nhất
  của bên đó, canh theo khoảng đặt của bên đó. Không còn đủ chỗ thì đặt ở góc dưới cùng bên đó, chỉ khi không chạm món nào; vẫn không được
  thì không vẽ thẻ và báo `card_no_room`.
  Lệch Giả định của spec ("thẻ ở góc dưới khung"): ở khung dọc 480×832 dải dưới cùng chính là mặt bàn nơi các món đứng, thẻ ở đó che chân món,
  trái US3 #1 ("không che chính các sản phẩm"). TODO: người dùng duyệt vị trí này bằng ảnh chụp.
- Chữ trên thẻ dùng nguyên `card_text` của 009 (FR-020): nguyên văn file, đổi theo file mới khi nạp lại.

**Lý do.** Dùng lại toàn bộ luật làm nổi và vẽ thẻ của 009; chỉ thêm việc chọn thẻ nào vẽ và đặt ở đâu.

**Phương án đã cân nhắc.** Thẻ thành lớp riêng ngoài `base` (vẽ nhanh hơn khi đổi món): 009 đã vẽ lại `base` khi đổi món nổi trong ngân
sách (`scene_ms` trung vị 4,66 ms), không cần thêm lớp. Đổi chế độ thẻ trên trang điều khiển giữa phiên: spec chỉ cần chọn theo phiên.

## R5. Bỏ nền phẳng (nền trắng, nền một màu)

**Quyết định.** Hàm `remove_flat_background(rgba) -> CutResult` trong `scene/matting.py` (Pillow + numpy):
1. **Nhận diện nền phẳng:** lấy các điểm ảnh ở viền 2 px của ảnh; màu nền = trung vị viền. Nền phẳng khi ≥ 90% điểm viền cách màu nền
   ≤ 28 (khoảng cách Chebyshev trên R, G, B). Không phẳng → chuyển sang model (R6).
2. **Loang từ viền:** đánh dấu nền = các điểm gần màu nền (≤ 28) **liên thông với viền** (flood fill, `ImageDraw.floodfill` trên ảnh mặt nạ
   hoặc BFS numpy). Điểm cùng màu nền nằm trong lòng sản phẩm nhưng không thông ra viền được giữ.
3. **Mép:** alpha = 0 ở nền, 255 ở sản phẩm; `MinFilter(3)` rồi `GaussianBlur(0.8)` trên kênh alpha để mép mềm 1–2 px (FR-015 cho phép).
4. **Chỉ đổi alpha:** kênh R, G, B giữ nguyên từng điểm ảnh (test so từng điểm có alpha > 0). Cắt ảnh theo hộp bao của alpha như 012.
5. Kết quả qua kiểm độ chắc (R8). Không chắc → thử model nếu có (R6), không có model → `failed`.
Chạy trong luồng phụ (`asyncio.to_thread`), ảnh đã thu ≤ 1280 px nên ước tính < 0,5 s. TODO: đo trên bộ ảnh SC-003.

**Lý do.** Bản dựng thử 2026-11-22 cho kết quả sạch với ảnh thùng Coca nền trắng bằng đúng các tham số này. Không cần thư viện mới
(numpy đã có, R6).

**Phương án đã cân nhắc.** Ngưỡng màu toàn ảnh (không loang): khoét mất phần trắng trong sản phẩm (US2 #4). Dùng model cho mọi ảnh: chậm
hơn nhiều, tranh CPU với VieNeu không cần thiết.

## R6. Model tách nền cho nền phức tạp và giấy phép

**Quyết định.**
- **Không** cài `rembg`. Tự viết phần tiền xử lý và hậu xử lý (khoảng 30 dòng), chạy model ONNX bằng `onnxruntime`.
- **Phụ thuộc:** `onnxruntime` (1.31.1) và `numpy` **đã có trong `uv.lock` và `.venv`** do `vieneu` kéo theo (ADR-024). Plan khai hai gói này
  thành phụ thuộc trực tiếp trong `pyproject.toml` (`onnxruntime>=1.31.1`, `numpy`), để không phụ thuộc ngầm vào `vieneu`. Không cài gì mới,
  nhưng vẫn cần ADR-074 và người dùng duyệt (CLAUDE.md, Điều VII).
- **Model mặc định:** `isnet-general-use.onnx` (IS-Net/DIS, xuebinqin). Bản ONNX lấy từ release của rembg:
  `https://github.com/danielgatis/rembg/releases/download/v0.0.0/isnet-general-use.onnx`, md5 `fc16ebd8b0c10d971d3513d564d01e29` (trong
  `rembg/sessions/dis_general_use.py`). Lưu ngoài git ở `models/matting/isnet-general-use.onnx`. TODO: ghi kích thước và sha256 khi tải.
- **Tiền xử lý ISNet** (theo `rembg/sessions/base.py` `BaseSession.normalize` và `dis_general_use.py`): RGB, thu về 1024×1024 bằng LANCZOS;
  chia cho giá trị lớn nhất của ảnh (`max(np.max(a), 1e-6)`, không phải chia 255); trừ trung bình (0,5; 0,5; 0,5), chia độ lệch (1; 1; 1);
  đổi trục thành NCHW float32. **Hậu xử lý:** lấy `out[0][:, 0]`, kéo về 0–1 bằng (x − min)/(max − min) (không sigmoid), thành mặt nạ 8 bit,
  phóng về cỡ ảnh bằng LANCZOS; mặt nạ thành kênh alpha, R, G, B giữ nguyên (FR-015).
- **Phương án dự phòng:** BiRefNet_lite (`birefnet-general-lite.onnx`, rembg release
  `BiRefNet-general-bb_swin_v1_tiny-epoch_232.onnx`, md5 `4fab47adc4ff364be1713e97b7e66334`). Tiền xử lý: 1024², trung bình ImageNet
  (0,485; 0,456; 0,406), độ lệch (0,229; 0,224; 0,225); hậu xử lý: sigmoid rồi kéo về 0–1. Chỉ chuyển sang nếu ISNet không đạt 7/10 ảnh
  nền phức tạp (SC-003) ở bước đo; khi đó ghi ADR mới. Mã viết sẵn hai cấu hình tiền/hậu xử lý, chọn theo tên file model.
- **Giấy phép (ràng buộc 5, RISKS L15):**
  - IS-Net: repo `xuebinqin/DIS` có `LICENSE.md` là Apache-2.0; README mục "Term of Use": mã và thước đo dùng Apache-2.0, bộ dữ liệu DIS5K
    có điều khoản riêng (`DIS5K-Dataset-Terms-of-Use.pdf`). Model "general-use" được huấn luyện trên dữ liệu không nêu rõ.
    Đã đọc điều khoản DIS5K (2026-11-22, T056): chỉ dùng phi thương mại cho nghiên cứu hoặc giáo dục, cấm dùng thương mại khi
    chưa có phép của tác giả "even after copying, editing, processing or any operations". Không nói rõ trọng số có bị tính là
    dữ liệu đã xử lý không. TODO: hỏi tác giả bằng văn bản trước khi dùng model cho ảnh của khách (xem `docs/RISKS.md` L15).
  - Bản ONNX của rembg: repo rembg dùng MIT.
  - BiRefNet_lite: file LICENSE của repo là MIT (đã đọc 2026-11-22), thẻ model ghi MIT. Nhưng thẻ ghi bản DIS
    "trained on DIS-TR" (một phần DIS5K), nên cùng vướng điều khoản DIS5K như IS-Net.
  - BRIA RMBG-1.4/2.0: giấy phép riêng, cấm thương mại khi chưa mua → loại.
- **Model đặt bằng biến môi trường** `MATTING_MODEL_PATH` (mặc định rỗng). Rỗng hoặc file không có → không dùng model: chỉ bỏ nền phẳng; ảnh
  nền phức tạp → `failed` lý do "chưa cài model tách nền"; kiểm tra trước demo cảnh báo `matting_model_missing` (không phải lỗi).

**Nguồn.**
- rembg: https://github.com/danielgatis/rembg (MIT), mã phiên: `rembg/sessions/base.py`, `dis_general_use.py`, `birefnet_general.py`,
  `birefnet_general_lite.py` (đọc 2026-11-22); PyPI https://pypi.org/project/rembg/ (phụ thuộc: opencv-python-headless, pymatting,
  scikit-image, scipy, pooch…).
- DIS: https://github.com/xuebinqin/DIS và `LICENSE.md` (Apache-2.0, đọc 2026-11-22).
- BiRefNet_lite: https://huggingface.co/ZhengPeng7/BiRefNet_lite (thẻ ghi MIT).
- Tốc độ BiRefNet bản đầy đủ trên CPU (M1 Max) khoảng 4,3 s/ảnh:
  https://dev.to/kiarina/removing-a-portrait-background-with-birefnet-onnx-on-cpu-gbj.
- BRIA: https://huggingface.co/briaai/RMBG-1.4 (giấy phép không thương mại).

**Lý do.** `rembg` kéo theo cả loạt thư viện nặng (OpenCV, scikit-image, scipy, pymatting) chỉ để chạy một model; phần cần dùng chỉ là
tiền/hậu xử lý ngắn trên `onnxruntime` đã có. ISNet nhẹ hơn BiRefNet và giấy phép Apache-2.0 rõ hơn.

**Phương án đã cân nhắc.** `rembg` (nhiều phụ thuộc, tải model ngầm vào `~/.u2net`); BRIA (giấy phép); dịch vụ tách nền trả phí (FR-013
cấm, ràng buộc chi phí); U²-Net (cũ hơn, kém hơn ISNet theo chính tác giả).

## R7. Chạy model mà không làm giật tiếng (FR-016)

**Quyết định.**
- Chạy model trong **tiến trình con**: `python -m ai_live.scene.matting --model <path> --in <png> --out <png>`, gọi bằng
  `asyncio.create_subprocess_exec(sys.executable, ...)`, nên vòng sự kiện không bị chặn và lỗi/crash/thiếu RAM của model không kéo sập app.
- **Mức ưu tiên thấp:** trên Windows `creationflags=subprocess.BELOW_NORMAL_PRIORITY_CLASS`; trên Linux/macOS tiến trình con tự gọi
  `os.nice(10)` lúc khởi động. Bộ lập lịch HĐH ưu tiên luồng VieNeu và app.
- **Giới hạn luồng:** `onnxruntime.SessionOptions.intra_op_num_threads = 2`, `inter_op_num_threads = 1`; chừa lõi cho VieNeu.
- **Một ảnh một lúc:** `asyncio.Semaphore(1)` cho bước model; ảnh thứ hai chờ.
- **Hết giờ 60 s:** giết tiến trình con, kết quả `failed` lý do "tách nền quá lâu".
- **Không giữ tiến trình model thường trực:** tải ảnh hiếm (vài lần mỗi buổi), nạp model mỗi lần (ước tính 1–3 s) đổi lấy không chiếm RAM cả
  buổi. TODO: đo thời gian nạp và RAM đỉnh trên laptop dev.
- **Khi đang có show:** đo SC-005 (lặng p95 khi tách nền giữa show). Nếu không đạt, đặt `MATTING_DURING_SHOW=false`: lúc show đang chạy, ảnh
  nền phức tạp không chạy model, kết quả `failed` lý do "đang live, bỏ nền phức tạp sau khi dừng show" (spec, trường hợp biên). Mặc định
  `true` cho tới khi đo. Nền phẳng luôn chạy (nhẹ).

**Lý do.** Tiến trình riêng + ưu tiên thấp + ít luồng là cách cách ly CPU đơn giản nhất mà không cần `psutil` hay hàng đợi ngoài.

**Phương án đã cân nhắc.** Chạy trong luồng phụ cùng tiến trình: onnxruntime dùng mọi lõi, không hạ ưu tiên riêng được, crash kéo sập app.
`ProcessPoolExecutor`: khó đặt ưu tiên trên Windows và giữ tiến trình thường trực. Chạy trên GPU laptop (DirectML/CUDA): cần gói
onnxruntime khác (phụ thuộc mới) và GPU đang chạy lip-sync.

## R8. Kiểm độ chắc của ảnh đã bỏ nền (FR-014)

**Quyết định.** Hàm `assess_cut(alpha) -> (ok, reason)` áp cho cả hai cách. Không chắc khi có một trong các điều:
- tỷ lệ phần sản phẩm (alpha ≥ 128) < 5% hoặc > 95% ảnh → "gần như không còn gì" / "không tách được nền";
- > 25% điểm viền ảnh vẫn thuộc sản phẩm → sản phẩm dính viền, có thể bị cắt hoặc nền chưa bỏ;
- tỷ lệ điểm lưng chừng (alpha 26–229) > 12% phần sản phẩm → mép nhòe, model không chắc;
- (chỉ nền phẳng) phần sản phẩm vỡ thành nhiều mảnh: mảnh lớn nhất < 85% tổng → nghi khoét mất phần cùng màu nền (US2 #4).
Không chắc ở nền phẳng → thử model (nếu có); không chắc ở model → `failed` với lý do tiếng Việt. Ảnh lỗi không bao giờ được chọn sẵn.
Ngưỡng là giá trị đầu. TODO: chỉnh trên bộ ≥ 20 ảnh của SC-003 (10 nền trơn, 10 nền phức tạp) để 100% ảnh xấu bị báo (SC-003 vế 3), ghi
ngưỡng cuối vào research.

**Lý do.** Chỉ số rẻ, tính trên mặt nạ đã có, bắt được các kiểu lỗi trong spec (khoét, dính viền, model mờ). Chấp nhận báo nhầm một số ảnh
tốt (vẫn dùng được ảnh gốc) hơn là đưa ảnh lỗi lên live.

**Phương án đã cân nhắc.** Chạy cả nền phẳng lẫn model rồi so hai mặt nạ: tốn thêm thời gian model cho mọi ảnh. Để người vận hành tự nhìn:
spec đòi hệ thống báo trước (FR-014).

## R9. Lưu bản đã bỏ nền trong kho ảnh 012

**Quyết định.**
- **Bản đã bỏ nền là một phiên bản riêng** trong `uploads/images.json` của 012: file `uploads/<pid>/<vid_cut>.png`, `vid_cut` = 12 ký tự
  đầu sha256 của PNG như mọi phiên bản. Phiên bản thêm hai trường: `derived_from` (vid ảnh tải lên) và `bg_removal` (xem data-model).
  Phiên bản ảnh tải lên thêm `bg_removal` và `cutout_version` (vid bản bỏ nền, hoặc null).
- Vì là phiên bản thường, mọi thao tác 012 (áp dụng, về ảnh trước, gỡ, bộ chuẩn bị, xác nhận quyền dùng, xem trước) chạy **không đổi**
  (FR-017). Người vận hành chọn bản nào thì `apply` với `version_id` của bản đó.
- Tải lại đúng ảnh cũ (012 `reused`) → dùng lại `cutout_version` đã có, không bỏ nền lần nữa.
- Ảnh đã trong suốt (`has_alpha = true`) → `bg_removal.method = "already_transparent"`, không tạo bản mới (FR-011, US2 #2).
- Tải lên **chờ bỏ nền xong rồi mới trả lời** (một request): nền phẳng < 1 s, model ≤ 20 s (SC-006); trang hiện "Đang bỏ nền…" trong lúc chờ.
  Vòng sự kiện không bị chặn (luồng phụ/tiến trình con, R5, R7).
- Ảnh tải lên vẫn được giữ cạnh bản bỏ nền (Giả định của spec, SC-004).
- `SCHEMA_VERSION` của `images.json` giữ 1: trường mới là tùy chọn, bộ đọc 012 bỏ qua khóa lạ trong phiên bản. TODO (task): xác nhận bộ đọc
  012 không từ chối khóa lạ; nếu có thì nâng lên 2 kèm đọc ngược.

**Lý do.** Coi bản bỏ nền là phiên bản ảnh có sẵn đường đi trong 012, khớp FR-017 mà không sửa logic áp/hoàn tác/bộ chuẩn bị.

**Phương án đã cân nhắc.** Một phiên bản có hai file (`<vid>.png`, `<vid>.cut.png`) và cờ "dùng bản nào": phải sửa mọi thao tác 012 và
luật xác nhận. Bỏ nền bất đồng bộ (trả lời ngay, gửi kết quả qua `/ws/control` sau): thêm trạng thái "đang xử lý" ở cả kho và trang; chỉ
cần nếu đo thấy chờ quá lâu.

## R10. Kiểm tra trước demo và log

**Quyết định.**
- Cảnh báo mới (mức `warning`, `SceneIssue`, đi qua `check_scene` của `ops/readiness.py` như 009):
  - `hands_zone_missing`: cách bày "như thật" mà nhân vật chưa khai vùng tay (FR-003);
  - `art_has_background`: cách bày "như thật" và ảnh đang dùng của một món còn nền (ảnh tải lên có `has_alpha = false` và không phải bản bỏ
    nền; hoặc ảnh bộ cảnh 009 không có điểm trong suốt) (FR-018);
  - `matting_model_missing`: `MATTING_MODEL_PATH` rỗng hoặc file không có (R6);
  - `card_no_room`, `cards_ignored` (R4).
- Log JSONL `scene_bg_removed`: `product_id`, `version_id` (ảnh tải lên), `cutout_version`, `method`
  (`already_transparent` | `flat` | `model`), `result` (`removed` | `failed` | `kept`), `reason`, `ms`, `model` (tên file, nếu dùng), `width`,
  `height` (FR-024). `scene_ms` và FPS mỗi khung giữ như 009 FR-022; log `scene_rendered` thêm `layout_mode`.

**Lý do.** Dùng lại kênh cảnh báo và log có sẵn của 009/012.

**Phương án đã cân nhắc.** Biến `art_has_background` thành lỗi: spec nói cảnh báo, ảnh còn nền vẫn hiện được.

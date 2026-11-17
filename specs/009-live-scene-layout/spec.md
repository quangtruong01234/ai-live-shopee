# Đặc tả tính năng: Bố cục cảnh live quanh AI host

- **Feature ID:** `009-live-scene-layout` · **Branch:** `main` · **Ngày tạo:** 2026-11-13
- **Trạng thái:** Done <!-- Draft → Clarified → Planned → Tasked → In progress → Done -->
- **Mốc roadmap:** M1b (mục "Bố cục cảnh live quanh host"), dùng cho M1d (tổng duyệt và demo)
- **Mô tả gốc:** "009-live-scene-layout: Bố cục cảnh live quanh host AI. Đầu vào: ghi chú 009-live-scene-layout trong
  progress/FEATURES.md (hướng B đề xuất: ghép lớp realtime mỗi khung: phông sau, ảnh thật sản phẩm, thẻ tên/giá từ dữ liệu sản
  phẩm, phụ đề, làm nổi sản phẩm đang nói; nhãn AI và watermark LiveTalking không bị che)."

**Bối cảnh.** Live bán hàng thường có bố cục người đứng hoặc ngồi sau bàn, sản phẩm bày trên bàn, có thẻ tên và giá. Hiện AI host
của feature 005 chỉ là khung hình dọc nhân vật nửa người trên phông trơn (giữ đúng bối cảnh của ảnh gốc, FR-002 của 005), không có bàn
hay sản phẩm. Người dùng chọn hướng B (ghi chú 2026-11-07): mỗi khung hình được ghép thêm lớp ảnh tĩnh và lớp chữ ngay lúc phát, không
tạo lại clip nền, không tách người khỏi nền. Sau phiên làm rõ 2026-11-13: khung dọc 9:16, host giữ đầy khung, phông của chính clip làm
phông sau; cảnh thêm vào là **mặt bàn phía trước host với mọi sản phẩm bày trên bàn**, mỗi món có thẻ tên và giá.

## Kịch bản người dùng và kiểm thử *(bắt buộc)*

### User Story 1: Bàn bày sản phẩm kèm thẻ tên/giá trước host (Ưu tiên: P1)

Khách chỉ gửi ảnh chụp sản phẩm. Trước phiên live, mình chỉnh các ảnh đó (cắt nền, chỉnh cỡ) để trông như món hàng đặt trên bàn, rồi đặt
vào bộ cảnh của khách cùng một ảnh mặt bàn. Khi mở màn hình host, người xem thấy host đứng sau một quầy bàn ở phần dưới khung dọc; trên
bàn bày sản phẩm chính và các sản phẩm phụ, cạnh mỗi món có thẻ tên và giá lấy đúng từ file dữ liệu sản phẩm. Cảnh nằm ngay trong khung
hình gửi đi (giống nhãn "AI"), nên chia sẻ tab vào Meet hay sau này đưa vào OBS đều thấy y như nhau. Nhãn "AI", watermark
"LiveTalking" và khuôn mặt host vẫn hiện rõ, không bị lớp nào che.

**Vì sao ưu tiên này:** đây là phần khách nhìn thấy đầu tiên trong buổi demo; host đứng trước phông trơn không có hàng trông giống bản
thử hơn là phiên live bán hàng. Story này một mình đã đủ để demo.

**Kiểm thử độc lập:** nạp file dữ liệu demo (1 sản phẩm chính + 2 sản phẩm phụ) và bộ cảnh đủ ảnh, mở màn hình host ở chế độ nhân vật
nhép miệng, chạy show kịch bản vài phút, chụp ít nhất 10 ảnh màn hình ở thời điểm ngẫu nhiên; so tên và giá trên thẻ với file; kiểm
nhãn "AI", watermark và mặt host không bị che. Lặp lại ở chế độ ảnh tĩnh.

**Kịch bản chấp nhận:**
1. **Given** dữ liệu 1 sản phẩm chính + 2 sản phẩm phụ và bộ cảnh đủ ảnh, **When** mở màn hình host (show chưa bắt đầu, host chạy clip
   chờ), **Then** khung dọc thấy host ở giữa, mặt bàn phía trước che phần thân dưới host, cả 3 sản phẩm bày trên bàn, sản phẩm chính ở chỗ
   nổi bật hơn sản phẩm phụ, mỗi sản phẩm có thẻ tên và giá.
2. **Given** sản phẩm có giá một mức, **When** cảnh hiện, **Then** thẻ ghi đúng giá đó; **Given** sản phẩm có bảng phân loại nhiều mức giá,
   **Then** thẻ ghi khoảng giá từ thấp nhất đến cao nhất, đúng từng con số trong file.
3. **Given** cảnh đang hiện, **When** host đang nói hoặc đang chờ, **Then** nhãn "AI", watermark "LiveTalking" và khuôn mặt host
   (từ cằm trở lên) không bị bất kỳ lớp nào của cảnh che, dù một phần.
4. **Given** một sản phẩm không có ảnh trong bộ cảnh, **When** cảnh hiện, **Then** sản phẩm đó vẫn có thẻ tên và giá trên bàn (không
   ảnh), các sản phẩm khác hiện bình thường, và mình được báo sản phẩm nào thiếu ảnh trước khi bắt đầu show.
5. **Given** cảnh đang hiện, **When** thay file dữ liệu sản phẩm bằng file mới có giá khác, **Then** thẻ đổi theo file mới mà không cần mở
   lại phiên, không lúc nào hiện giá cũ lẫn với dữ liệu mới.
6. **Given** phiên đang ở chế độ nhân vật nhép miệng, **When** phiên tự về ảnh tĩnh vì lỗi tạo hình (FR-022 của 005), **Then** cảnh vẫn
   hiện đủ bàn, sản phẩm, thẻ, nhãn "AI", chỉ có host đổi thành ảnh tĩnh.
7. **Given** cấu hình phiên tắt cảnh, **When** mở màn hình host, **Then** màn hình giống hệt hiện nay (feature 001, 004, 005).

---

### User Story 2: Làm nổi sản phẩm host đang nói tới (Ưu tiên: P2)

Khi show kịch bản chuyển sang phân đoạn về một sản phẩm, món đó trên bàn to hơn và được làm nổi (ví dụ viền sáng), thẻ của nó hiện thêm
dòng khuyến mãi; các món khác nhỏ lại và dịu đi nhưng vẫn đọc được tên và giá. Người xem nhìn là biết host đang nói về món nào.

**Vì sao ưu tiên này:** khung dọc hẹp, bày 3–4 món cùng lúc thì món nào cũng nhỏ; làm to món đang nói giúp người xem theo kịp. Cần US1
có trước nhưng không cần gì khác.

**Kiểm thử độc lập:** chạy show kịch bản qua ít nhất một vòng đủ 3 sản phẩm, ghi màn hình; với mỗi phân đoạn đối chiếu sản phẩm được
làm nổi với sản phẩm của phân đoạn trong log show và thời điểm câu đầu của phân đoạn bắt đầu phát.

**Kịch bản chấp nhận:**
1. **Given** show đang chạy, **When** câu đầu của phân đoạn về sản phẩm X bắt đầu phát thành tiếng, **Then** X được làm nổi và to hơn
   trong vòng 1 giây, không sớm hơn lúc câu đó bắt đầu phát (phân đoạn chuẩn bị trước không làm đổi sản phẩm nổi).
2. **Given** phân đoạn chung không về riêng sản phẩm nào (mở màn, chào kết), **When** phân đoạn đó phát, **Then** không sản phẩm nào
   bị làm nổi, mọi sản phẩm hiện theo bố cục thường của US1.
3. **Given** X đang được làm nổi, **When** người vận hành tạm dừng, **Then** X vẫn nổi; **When** bỏ qua phân đoạn, **Then** sản phẩm
   nổi đổi theo phân đoạn kế khi câu đầu của nó phát.
4. **Given** X đang được làm nổi, **When** host chen câu trả lời một comment, **Then** sản phẩm nổi giữ nguyên tới khi kịch bản sang
   phân đoạn khác.
5. **Given** X đang được làm nổi và to hơn, **Then** X và thẻ của nó vẫn không che mặt host, nhãn "AI", watermark, và các món khác
   vẫn đọc được tên và giá.
6. **Given** show đã kết thúc hoặc chưa bắt đầu, **Then** không sản phẩm nào bị làm nổi.

---

### User Story 3: Phụ đề nằm trong khung hình (Ưu tiên: P3)

Phụ đề câu host đang nói hiện ngay trong khung hình gửi đi, có dấu tiếng Việt đầy đủ, để khi đẩy khung hình sang OBS / YouTube vẫn có
phụ đề (hiện phụ đề chỉ là chữ trên trang web, không đi theo khung hình).

**Vì sao ưu tiên này:** demo Meet chia sẻ cả tab nên phụ đề trang web đã đủ; phụ đề trong khung chỉ cần khi ra OBS (M1c, M2).

**Kiểm thử độc lập:** chạy show 5 phút, chụp ảnh lúc host đang nói, so chữ phụ đề với câu trong log show; kiểm dấu tiếng Việt hiện đúng.

**Kịch bản chấp nhận:**
1. **Given** host đang nói một câu, **When** câu đó phát, **Then** phụ đề của chính câu đó hiện trong khung hình, đủ dấu, không bị cắt
   chữ; câu dài xuống dòng tối đa 2 dòng.
2. **Given** phụ đề đang hiện, **When** bỏ qua lượt hoặc tạm dừng, **Then** phụ đề tắt cùng lúc với tiếng.
3. **Given** phụ đề trong khung đang bật, **Then** màn hình host không hiện thêm phụ đề trang web trùng lặp.
4. **Given** phụ đề đang hiện, **Then** không che mặt host, nhãn "AI", watermark hay thẻ sản phẩm.

### Trường hợp biên

- **Ảnh sản phẩm hỏng, sai định dạng hoặc quá lớn:** bị từ chối lúc nạp bộ cảnh kèm lý do; sản phẩm đó hiện thẻ không ảnh (US1 #4);
  phiên không dừng.
- **Ảnh mặt bàn thiếu hoặc hỏng:** cảnh dùng một dải màu trơn ở vị trí mặt bàn, sản phẩm và thẻ vẫn bày trên đó; mình được báo.
- **Tên sản phẩm quá dài cho thẻ:** xuống dòng tối đa 2 dòng rồi rút gọn bằng dấu "…", không tự đổi chữ, không chữ nào tràn ra khỏi thẻ.
- **Nhiều sản phẩm hơn số chỗ trên bàn:** hiện sản phẩm chính và các sản phẩm phụ theo thứ tự trong file cho tới hết chỗ; mình được
  báo sản phẩm nào không có chỗ.
- **Sản phẩm bị bỏ khỏi file mới:** ảnh và thẻ của nó biến mất khỏi bàn khi nạp file mới; ảnh sản phẩm không khớp sản phẩm nào trong
  file mới thì không hiện.
- **Sản phẩm có giá 0 hoặc không có giá:** file dữ liệu đã bắt buộc có giá hoặc bảng phân loại (001); cảnh không tự điền giá.
- **Ảnh sản phẩm dọc và cao (chai, hộp đứng):** được thu nhỏ cho vừa chỗ trên bàn, không kéo méo tỷ lệ, không vươn lên quá cằm host.
- **Host đưa tay xuống thấp trong clip:** tay có thể bị mặt bàn che; chấp nhận, miễn mặt không bị che.
- **Máy chậm, ghép cảnh làm tụt khung hình:** tiếng và miệng vẫn phải khớp như 005 (FR-007 của 005); cảnh không được làm tiếng chạy
  trước hình. Số khung hình mỗi giây khi có cảnh được đo và so với khi không có cảnh (SC-004).
- **Phân đoạn về sản phẩm không có trên bàn (không còn chỗ):** không sản phẩm nào được làm nổi trong phân đoạn đó.

## Yêu cầu *(bắt buộc)*

### Yêu cầu chức năng

**Bộ cảnh và bố cục**

- **FR-001**: Mỗi khách PHẢI có một bộ cảnh riêng gồm: ảnh mặt bàn và ảnh của từng sản phẩm (gắn với sản phẩm trong file dữ liệu).
  Mọi ảnh là ảnh tĩnh; bộ cảnh không chứa video hay tiếng.
- **FR-002**: Ảnh sản phẩm PHẢI làm từ ảnh chụp thật do khách gửi. Mình được chỉnh ảnh trước phiên cho hợp cảnh bàn: cắt nền, cắt
  khung, chỉnh cỡ, chỉnh sáng, thêm bóng đổ dưới đáy để trông như đặt trên bàn. **Không** được vẽ thêm hay xóa chi tiết của chính sản
  phẩm, không đổi hình dáng, màu, chữ hay nhãn trên bao bì. Mỗi ảnh sản phẩm PHẢI giữ được ảnh gốc của khách và ghi lại đã chỉnh gì.
  Hệ thống không tự tạo ảnh sản phẩm.
- **FR-003**: Mình PHẢI kiểm được bộ cảnh trước phiên bằng một thao tác: báo ảnh hỏng/sai định dạng, sản phẩm thiếu ảnh, ảnh không khớp
  sản phẩm nào, sản phẩm không có chỗ trên bàn, ảnh thiếu hồ sơ chỉnh sửa. Lỗi bộ cảnh không chặn việc bắt đầu show; cảnh hiện phần dùng
  được (US1 #4, Trường hợp biên).
- **FR-004**: Khung hình có cảnh PHẢI là khung **dọc 9:16**, cố định cho cả phiên, cùng khung với nhân vật (005).
- **FR-005**: Nhân vật PHẢI giữ nguyên cỡ và vị trí, đầy khung như hiện nay (không thu nhỏ); phông của chính clip nền là phông sau của
  cảnh. Cảnh không thêm lớp phông sau.
- **FR-006**: Mặt bàn PHẢI nằm ở phần dưới khung, phía trước host, che phần thân dưới, không che từ cằm trở lên.
- **FR-007**: Bàn PHẢI bày **tất cả** sản phẩm đang có trong file dữ liệu (ít nhất 1 sản phẩm chính và 3 sản phẩm phụ, PRD §2) cùng lúc:
  sản phẩm chính ở chỗ nổi bật hơn, sản phẩm phụ theo thứ tự trong file. Ảnh và thẻ sản phẩm nằm trước mặt bàn (không bị bàn che).
- **FR-008**: Cảnh PHẢI được ghép vào chính khung hình gửi đi (không phải lớp phủ của trang web), ở cả chế độ nhân vật nhép miệng và chế
  độ ảnh tĩnh (kể cả khi phiên tự về ảnh tĩnh, FR-022 của 005), để Meet, OBS, YouTube nhận cùng một hình.
- **FR-009**: Người vận hành PHẢI bật hoặc tắt cảnh bằng cấu hình khi mở phiên; tắt cảnh thì màn hình host giữ nguyên hành vi của
  001, 004, 005.
- **FR-010**: Người vận hành PHẢI xem trước được cảnh trên màn hình host khi chưa bắt đầu show (host chạy clip chờ hoặc ảnh tĩnh).

**Thẻ tên và giá**

- **FR-011**: Mỗi sản phẩm trên bàn PHẢI có thẻ ghi tên và giá, lấy nguyên văn từ file dữ liệu sản phẩm đang nạp; sản phẩm có bảng
  phân loại thì ghi khoảng giá thấp nhất – cao nhất. Không có con số nào trên thẻ ngoài số trong file.
- **FR-012**: Chữ trên thẻ PHẢI hiện đủ dấu tiếng Việt, không tràn khỏi thẻ (xuống tối đa 2 dòng rồi rút gọn bằng "…").
- **FR-013**: Khi thay file dữ liệu sản phẩm giữa phiên, thẻ PHẢI đổi theo file mới trong vòng 2 giây sau khi nạp xong, không lúc nào
  ghép tên của file cũ với giá của file mới hay ngược lại.
- **FR-014**: Thẻ của sản phẩm đang được nói tới PHẢI hiện thêm dòng khuyến mãi đầu tiên của sản phẩm đó nếu file có, nguyên văn;
  sản phẩm không có khuyến mãi thì không có dòng này.

**Làm nổi sản phẩm đang nói**

- **FR-015**: Khi câu đầu của một phân đoạn về sản phẩm X bắt đầu phát thành tiếng, X PHẢI được làm nổi và to hơn (ảnh và thẻ) trong
  vòng 1 giây; các sản phẩm khác nhỏ lại và dịu đi nhưng vẫn đọc được tên và giá.
- **FR-016**: Sản phẩm nổi PHẢI theo câu đang phát thành tiếng, không theo phân đoạn đang được chuẩn bị trước.
- **FR-017**: Phân đoạn không về riêng sản phẩm nào (mở màn, chào kết, dự phòng chung), show chưa bắt đầu hoặc đã kết thúc: không
  sản phẩm nào nổi. Tạm dừng giữ nguyên sản phẩm nổi; câu trả lời comment chen vào không đổi sản phẩm nổi.

**Phụ đề**

- **FR-018**: Khi bật phụ đề trong khung, câu đang phát PHẢI hiện trong khung hình đủ dấu tiếng Việt, tối đa 2 dòng, bật/tắt cùng tiếng
  của câu đó (bỏ qua, tạm dừng tắt ngay). Bật phụ đề trong khung thì tắt phụ đề trang web để không trùng.

**An toàn của khung hình**

- **FR-019**: Không lớp nào của cảnh (bàn, ảnh sản phẩm, thẻ, phụ đề, hiệu ứng làm nổi) được che nhãn "AI", watermark "LiveTalking"
  hay khuôn mặt host (từ cằm trở lên), dù một phần, ở mọi thời điểm, kể cả khi sản phẩm đang to lên. Bố cục PHẢI giữ vùng cấm cho ba thứ
  này và từ chối cấu hình bố cục chồng lên vùng cấm.
- **FR-020**: Không có cấu hình nào của cảnh làm ẩn hoặc làm mờ nhãn "AI" (Điều I).
- **FR-021**: Lỗi ở bước ghép cảnh PHẢI không làm dừng phiên: khung hình vẫn ra (bỏ phần cảnh lỗi), tiếng vẫn phát, trang điều khiển
  báo lỗi.

**Quan sát**

- **FR-022**: Hệ thống PHẢI ghi lại số khung hình mỗi giây khi có cảnh và thời gian ghép cảnh mỗi khung, xem được cùng bảng độ trễ
  hiện có; ghi lại mỗi lần sản phẩm nổi đổi (thời điểm, sản phẩm, phân đoạn).

### Ràng buộc từ Hiến pháp

- [x] Điều I (realtime / nhãn AI / 1 host 1 tài khoản): cảnh ghép từ ảnh tĩnh và chữ ngay lúc phát, không có video hay tiếng dựng sẵn
  (FR-001, FR-008); nhãn "AI" luôn nằm trong khung và không bị che (FR-019, FR-020); bộ cảnh gắn với đúng một khách như nhân vật
  (FR-001, Thực thể chính); watermark "LiveTalking" không bị che (ràng buộc số 5, RISKS L1).
- [x] Điều II (đồng ý / bảo mật): ảnh sản phẩm (gốc và đã chỉnh) và ảnh mặt bàn là dữ liệu của khách, không commit vào git (như ảnh nhân
  vật); không thêm hình người thật nào vào cảnh.
- [x] Điều III (trả lời có căn cứ): tên, giá, khuyến mãi trên màn hình lấy nguyên văn từ file dữ liệu (FR-011, FR-014); ảnh sản phẩm làm
  từ ảnh thật của khách, chỉ chỉnh cho hợp cảnh, không vẽ thêm chi tiết sản phẩm (FR-002, ràng buộc số 7).
- [x] Điều IV (adapter): cảnh là một lớp thêm vào khung hình đầu ra, bật/tắt bằng cấu hình (FR-009); không sửa lõi show kịch bản, chỉ
  đọc sản phẩm của câu đang phát (FR-015–017).
- [x] Điều VI (độ trễ): cảnh không nằm trên đường câu → tiếng nên không được làm tăng câu đầu (≤ 5 s) hay khoảng lặng giữa câu (p95
  ≤ 1,5 s); chỉ được tốn thêm thời gian vẽ mỗi khung, đo bằng FR-022 và giới hạn ở SC-004.
- [x] Điều VIII (quan sát được, chịu lỗi): FR-003, FR-021, FR-022.

### Thực thể chính

- **Bộ cảnh**: thuộc đúng một khách; gồm ảnh mặt bàn, danh sách ảnh sản phẩm và bố cục bàn (khung dọc 9:16); có hồ sơ nguồn gốc cho
  từng ảnh (ai cung cấp, ngày nhận, đã chỉnh gì).
- **Ảnh sản phẩm**: ảnh tĩnh đã chỉnh của một sản phẩm, gắn với sản phẩm trong file dữ liệu và với ảnh gốc của khách; một sản phẩm có
  tối đa một ảnh trên bàn.
- **Chỗ trên bàn**: một vị trí đặt ảnh + thẻ; có loại (chính, phụ) và thứ tự; có cỡ thường và cỡ khi được làm nổi.
- **Thẻ sản phẩm**: tên, giá hoặc khoảng giá, dòng khuyến mãi khi đang được nói tới; mọi chữ lấy từ dữ liệu sản phẩm.
- **Vùng cấm**: vùng của nhãn "AI", watermark và khuôn mặt host mà không lớp nào được phủ lên.
- **Sản phẩm nổi**: sản phẩm của câu kịch bản đang phát thành tiếng, hoặc không có.

## Tiêu chí thành công *(bắt buộc)*

- **SC-001**: Trong 100% ảnh chụp màn hình host ở thời điểm ngẫu nhiên (ít nhất 20 ảnh, cả lúc chờ, lúc nói, lúc ảnh tĩnh, lúc đổi sản
  phẩm nổi), nhãn "AI", watermark "LiveTalking" và khuôn mặt host không bị che phần nào.
- **SC-002**: 100% tên, giá và khuyến mãi hiện trên thẻ trong một phiên 30 phút khớp nguyên văn file dữ liệu đang nạp, kể cả sau một
  lần thay file giữa phiên.
- **SC-003**: Với ít nhất 10 lần đổi phân đoạn về sản phẩm, 100% lần sản phẩm nổi đúng với sản phẩm của phân đoạn, và mỗi lần đổi
  nằm trong 1 giây sau lúc câu đầu của phân đoạn bắt đầu phát, không lần nào đổi trước lúc đó.
- **SC-004**: Trên laptop dev ở chế độ nhân vật nhép miệng, số khung hình mỗi giây khi bật cảnh không thấp hơn quá 10% so với khi tắt
  cảnh cùng cấu hình, và khoảng lặng giữa câu p95 không tăng quá 0,1 giây (show 10 phút mỗi bên).
- **SC-005**: Phiên 30 phút có bật cảnh chạy không lỗi, không đứng hình, cảnh không lúc nào biến mất (trừ khi lỗi được báo trên trang
  điều khiển theo FR-021).
- **SC-006**: Ít nhất 2/3 người xem thử (cùng những người xem ở 005 T068 nếu được) chọn bản có cảnh là "giống phiên live bán hàng hơn"
  khi xem hai đoạn 1 phút có và không có cảnh, và ít nhất 2/3 nói sản phẩm trông như đặt trên bàn (không lơ lửng, không méo).
- **SC-007**: Đặt ảnh gốc của khách cạnh ảnh đã chỉnh của 100% sản phẩm, người dùng xác nhận không có chi tiết sản phẩm nào bị thêm,
  xóa hay đổi (chỉ khác nền, cỡ, sáng, bóng).

## Giả định

- **Cảnh nằm trong khung hình gửi đi** (FR-008), không phải bố cục trang web quanh video: cùng lý do với nhãn "AI" (ADR-044), để Meet,
  OBS, YouTube, Shopee đều nhận một hình; tránh làm hai lần.
- **Không tách người khỏi nền, không thêm phông** (FR-005): host giữ đầy khung dọc để miệng không nhỏ đi; phông của chính clip nền là
  phông sau. Muốn đổi phông thì tạo lại clip nền ở quy trình làm clip của 005, không thuộc feature này.
- **Chỉnh ảnh sản phẩm là việc mình làm trước phiên, ngoài lúc live** (FR-002); app chỉ nhận ảnh đã chỉnh cùng ảnh gốc và hồ sơ chỉnh.
  Cách cắt nền cụ thể (bằng tay hay bằng công cụ) do plan chọn; nếu cần model hay phụ thuộc mới thì phải có ADR.
- **Ảnh mặt bàn do mình chuẩn bị** (ảnh tự chụp, ảnh có license, hoặc ảnh tạo bằng AI như ảnh gương mặt ở 005, có hồ sơ nguồn gốc),
  không chứa logo hay thương hiệu trừ khi khách gửi. Ảnh tạo bằng AI chỉ dùng cho bàn, **không bao giờ** cho sản phẩm (ràng buộc số 7).
- **Bố cục mặc định cố định**, mình không kéo thả vị trí trong phiên; đổi bố cục là sửa bộ cảnh rồi mở lại phiên.
- **Định dạng giá trên thẻ** theo cách viết tiền Việt hiện có trong dự án (ví dụ "199.000đ"; khoảng giá "199.000đ – 249.000đ"). Plan
  chốt chính xác dấu và ký hiệu.
- Thẻ hiện **dòng khuyến mãi đầu tiên** của sản phẩm đang nói (FR-014) vì khuyến mãi là thứ người xem cần thấy nhất; đổi sang không
  hiện khuyến mãi chỉ là cấu hình.
- Hiệu ứng làm nổi gồm to hơn cộng một thay đổi nhẹ (viền, độ sáng); cỡ và hình thức cụ thể do plan chọn, người dùng duyệt bằng ảnh
  chụp. Đổi cỡ có thể chuyển dần trong khoảng ngắn, miễn xong trong 1 giây (FR-015).
- Phụ đề trong khung (US3) mặc định **tắt** cho demo Meet (phụ đề trang web đã có); bật khi ra OBS/YouTube.
- Ảnh sản phẩm, ảnh bàn là dữ liệu của khách / tài sản của phiên: lưu ngoài git như ảnh nhân vật.

## Ngoài phạm vi

- Tách người khỏi nền (matting) để đặt host vào cảnh thật, thêm phông sau hay đặt sản phẩm phía sau host (hướng C: cần model mới + ADR,
  GPU 4 GB đã dùng ~2,7 GB).
- Thu nhỏ host hay mở rộng khung để có chỗ cho phông (đã cân nhắc ở phiên làm rõ 2026-11-13, không chọn).
- Vẽ cảnh vào ảnh gốc rồi tạo lại clip nền (hướng A).
- Khung ngang 16:9 (vẫn chia sẻ được qua Meet với hai bên trống).
- Host cầm hoặc chỉ tay vào sản phẩm, cử chỉ theo nội dung (để feature sau, như 005).
- Ảnh động, video sản phẩm, nhiều ảnh xoay vòng cho một sản phẩm.
- Kéo thả bố cục hay sửa cảnh giữa phiên trên trang điều khiển.
- Đếm ngược khuyến mãi, mã giảm giá, nút mua, giỏ hàng, link (link không bao giờ hiện, như không bao giờ đọc).
- Đầu ra OBS / RTMP (006, M2): feature này chỉ bảo đảm cảnh nằm trong khung hình để các đầu ra đó dùng lại.
- Chỉnh ảnh sản phẩm ngay trong app hay lúc live.

## Làm rõ

### Phiên 2026-11-13
- Q: Khung cảnh dọc 9:16 hay ngang 16:9? → A: Dọc 9:16 (FR-004; khung ngang vào Ngoài phạm vi).
- Q: Khách có ảnh thật sản phẩm không, có nền trong suốt không; mình có được tự cắt nền không? → A: Khách chỉ có ảnh chụp sản phẩm;
  mình lấy ảnh đó chỉnh cho hợp lúc live, ví dụ sản phẩm đặt trên bàn trước host (FR-002, FR-006, US1, SC-007).
- Q: Clip host đã chiếm trọn khung dọc; phông sau xử lý thế nào? → A: Giữ host đầy khung, phông của chính clip làm phông sau, chỉ ghép
  bàn + sản phẩm + thẻ ở phần dưới khung (FR-005; bỏ lớp phông sau và yêu cầu làm mờ chỗ giáp; US "Bàn phía trước host" gộp vào US1).
- Q: Trên bàn hiện bao nhiêu sản phẩm cùng lúc? → A: Tất cả, món đang nói to hơn (FR-007, FR-015, US2).

## Checklist chất lượng spec

- [x] Không có chi tiết triển khai (ngôn ngữ, framework, API, cấu trúc code)
- [x] Mọi FR đều kiểm thử được và không mơ hồ
- [x] Mọi SC đều đo được và không phụ thuộc công nghệ
- [x] Mỗi user story kiểm thử độc lập được và có kịch bản chấp nhận
- [x] Trường hợp biên đã liệt kê
- [x] Phạm vi và ngoài phạm vi rõ ràng
- [x] Ràng buộc Hiến pháp liên quan đã được nêu
- [x] Không còn `[NEEDS CLARIFICATION]` (hoặc người dùng đã chấp nhận để lại)

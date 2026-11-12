# Đặc tả tính năng: AI host tự nói kịch bản giới thiệu sản phẩm, sinh realtime

- **Feature ID:** `004-show-director` · **Branch:** `main` (ADR-027) · **Ngày tạo:** 2026-10-31
- **Trạng thái:** In progress <!-- Draft → Clarified → Planned → Tasked → In progress → Done -->
- **Mốc roadmap:** M1a (mục `ShowDirector` trong `docs/ROADMAP.md`; feature chính tiếp theo theo ADR-026)
- **Mô tả gốc:** "004-show-director" (bổ sung từ `specs/README.md` và ADR-026: host nói kịch bản giới thiệu sản phẩm liên tục, sinh
  realtime từ dữ liệu sản phẩm; đây là nội dung chính của phiên live, thay cho việc đọc chat để trả lời người xem).

## Kịch bản người dùng và kiểm thử *(bắt buộc)*

### User Story 1: Bấm "Bắt đầu", host tự nói liên tục về sản phẩm (Ưu tiên: P1)

Người vận hành nạp file nội dung sản phẩm của phiên (1 sản phẩm chính, 2–3 sản phẩm phụ), mở màn hình host, rồi bấm "Bắt đầu" trên
trang điều khiển. Host chào mở màn, rồi tự nói liên tục từng phân đoạn ngắn: giới thiệu sản phẩm chính, điểm nổi bật, thông số, giá
và phân loại, khuyến mãi, câu hỏi thường gặp, rồi chuyển sang sản phẩm phụ và quay lại sản phẩm chính. Mỗi câu được sinh ngay lúc
phiên đang chạy, chỉ từ dữ liệu sản phẩm, phát thành tiếng kèm phụ đề. Người vận hành không phải gõ gì thêm.

**Vì sao ưu tiên này:** Đây là nội dung chính của buổi demo sau ADR-026. Chỉ cần story này là đã có một phiên live "tự chạy" để cho
khách xem.

**Kiểm thử độc lập:** Nạp file nội dung mẫu, bấm "Bắt đầu", để chạy 5 phút không chạm vào gì. Quan sát: host nói liên tục, không
im lâu, nói về cả sản phẩm chính và sản phẩm phụ, mọi giá và khuyến mãi nghe được đều có trong file.

**Kịch bản chấp nhận:**
1. **Given** file nội dung hợp lệ đã nạp và màn hình host đang mở, **When** người vận hành bấm "Bắt đầu", **Then** trong vòng 5 giây
   host bắt đầu nói câu chào mở màn bằng tiếng Việt, xưng "em", gọi người xem là "anh chị", từ ngữ miền Nam.
2. **Given** phiên đang chạy, **When** host nói hết một phân đoạn, **Then** phân đoạn kế tiếp nối vào mà không có khoảng lặng dài
   (xem SC-002), và chủ đề hoặc sản phẩm của phân đoạn kế tiếp khác phân đoạn vừa nói.
3. **Given** sản phẩm có nhiều phân loại với giá khác nhau, **When** host nói về giá, **Then** host nói đúng giá từng phân loại hoặc
   khoảng giá như trong file, không tự gộp thành một giá.
4. **Given** sản phẩm không có giá trong file, **When** host giới thiệu sản phẩm đó, **Then** host không nói con số giá nào và bỏ qua
   chủ đề "giá" cho sản phẩm đó.
5. **Given** sản phẩm có danh sách khẳng định bị cấm (ví dụ "trị mụn dứt điểm"), **When** host nói về công dụng, **Then** không câu
   nào nói ra chứa khẳng định đó.
6. **Given** phiên đang chạy, **When** quan sát màn hình host, **Then** mỗi câu hiện thành phụ đề cùng lúc với tiếng, và nhãn "AI"
   luôn hiển thị.

---

### User Story 2: Người vận hành tạm dừng, bỏ qua và kết thúc phiên (Ưu tiên: P2)

Trong lúc host đang nói, người vận hành cần xử lý tình huống: tạm dừng khi có việc, bỏ qua phân đoạn nghe không ổn, hoặc kết thúc phiên
gọn gàng có lời chào.

**Vì sao ưu tiên này:** Buổi demo có người thật theo dõi. Phải có cách dừng ngay nội dung không ổn và kết thúc phiên đàng hoàng.

**Kiểm thử độc lập:** Khi phiên đang chạy, bấm lần lượt từng nút ít nhất 10 lần và đo thời gian từ lúc bấm đến lúc thấy hiệu lực.

**Kịch bản chấp nhận:**
1. **Given** host đang nói giữa một phân đoạn, **When** người vận hành bấm "Tạm dừng", **Then** host nói hết câu đang nói rồi im, không
   bắt đầu câu mới; nhân vật và nhãn "AI" vẫn hiện trên màn hình.
2. **Given** phiên đang tạm dừng, **When** người vận hành bấm "Tiếp tục", **Then** host nói tiếp từ câu kế tiếp của phân đoạn đang dở
   (hoặc phân đoạn mới nếu phân đoạn cũ đã hết) trong vòng 3 giây.
3. **Given** host đang nói, **When** người vận hành bấm "Bỏ qua", **Then** tiếng và phụ đề dừng trong vòng 1 giây, phần còn lại của
   phân đoạn đó bị bỏ, và host chuyển sang phân đoạn kế tiếp.
4. **Given** phiên đang chạy, **When** người vận hành bấm "Kết thúc", **Then** host nói một lời chào kết ngắn (tối đa 2 câu) rồi dừng
   hẳn; bấm "Bỏ qua" trong lúc chào kết thì dừng ngay.

---

### User Story 3: Chạy 30 phút không lặp nguyên văn, không đứng khi có lỗi (Ưu tiên: P2)

Buổi tổng duyệt chạy 30 phút liền (tiêu chí demo số 4 trong `docs/PRD.md` §3). Với chỉ 3–4 sản phẩm, host phải xoay vòng sản phẩm và
chủ đề, nói lại cùng một thông tin bằng câu chữ khác, và vẫn tiếp tục khi dịch vụ sinh nội dung hoặc tạo tiếng bị lỗi.

**Vì sao ưu tiên này:** Nội dung lặp nguyên văn dễ bị coi giống video quay sẵn và làm người xem rời phiên (`docs/RISKS.md` P7). Một lỗi
mạng không được làm hỏng cả buổi demo.

**Kiểm thử độc lập:** Chạy 30 phút, giả lập ít nhất 3 lỗi ở bước sinh kịch bản và bước tạo tiếng. Sau phiên, đọc file lịch sử phụ đề
và nhật ký lỗi.

**Kịch bản chấp nhận:**
1. **Given** phiên chạy 30 phút, **When** đối chiếu toàn bộ câu đã nói, **Then** tỷ lệ câu trùng nguyên văn với câu đã nói trước đó
   trong phiên không vượt ngưỡng ở SC-005.
2. **Given** phiên chạy 30 phút, **When** thống kê phân đoạn theo sản phẩm, **Then** sản phẩm chính chiếm phần lớn thời lượng và mỗi
   sản phẩm phụ đều được giới thiệu đều đặn (SC-004).
3. **Given** bước sinh kịch bản lỗi hoặc quá giờ, **When** host đang chuẩn bị phân đoạn kế tiếp, **Then** phân đoạn đó bị bỏ, lỗi được
   ghi lại và hiện trên trang điều khiển, phiên không dừng. Nếu lỗi kéo dài (mặc định 3 phân đoạn liên tiếp lỗi, chỉnh được), host
   chuyển sang **chế độ dự phòng**: đọc nguyên văn từng câu của bài giới thiệu và mô tả có sẵn trong file nội dung (vẫn qua bộ chặn
   như câu sinh ra; tiếng và hình vẫn sinh realtime), trang điều khiển báo rõ "đang ở chế độ dự phòng". Trước mỗi phân đoạn dự phòng,
   hệ thống thử sinh lại; sinh được thì tự quay về chế độ bình thường.
4. **Given** bước tạo tiếng lỗi ở một câu, **When** host đang nói phân đoạn, **Then** câu đó bị bỏ, lỗi được ghi, host nói tiếp câu kế.

---

### User Story 4: Tự kiểm tra kịch bản không bịa trước khi lên phiên (Ưu tiên: P2)

Trước buổi demo, và mỗi khi đổi cách sinh kịch bản, người vận hành chạy một lệnh tự sinh nhiều phân đoạn mẫu cho mọi sản phẩm và mọi
chủ đề, rồi tự chấm: có con số nào không có trong file, có khẳng định bị cấm, có đọc đường link không, có sai xưng hô không.

**Vì sao ưu tiên này:** Hiến pháp Điều III yêu cầu chạy lại bộ kiểm tra mỗi khi đổi cách sinh lời thoại. Bộ 10 câu hỏi mẫu của 001 chỉ
kiểm phần trả lời comment, không kiểm kịch bản.

**Kiểm thử độc lập:** Chạy lệnh kiểm tra với file nội dung mẫu, xem báo cáo gồm từng phân đoạn, lỗi tìm được và tổng kết; chạy lại lần
hai để thấy so sánh với lần trước.

**Kịch bản chấp nhận:**
1. **Given** file nội dung mẫu, **When** chạy lệnh kiểm tra, **Then** mỗi tổ hợp sản phẩm × chủ đề có dữ liệu đều được sinh ít nhất một
   phân đoạn và được chấm.
2. **Given** một phân đoạn nhắc giá không có trong file hoặc chứa khẳng định bị cấm, **When** chấm, **Then** phân đoạn đó bị đánh dấu
   vi phạm, kèm câu vi phạm và lý do.
3. **Given** đã có kết quả lần chạy trước, **When** chạy lại, **Then** báo cáo so sánh số vi phạm giữa hai lần.

---

### User Story 5: Người vận hành chọn sản phẩm hoặc chủ đề cho phân đoạn kế tiếp (Ưu tiên: P3)

Trong lúc demo, khách hỏi miệng qua Meet "cho xem sản phẩm phụ kia đi" hoặc người vận hành muốn host nhấn mạnh khuyến mãi. Người vận
hành chọn một sản phẩm và/hoặc một chủ đề trên trang điều khiển; phân đoạn kế tiếp nói đúng nội dung đó, rồi xoay vòng tiếp như cũ.

**Vì sao ưu tiên này:** Giúp buổi demo linh hoạt, nhưng không có vẫn demo được.

**Kiểm thử độc lập:** Khi phiên đang chạy, chọn sản phẩm phụ + chủ đề "khuyến mãi", xem phân đoạn kế tiếp.

**Kịch bản chấp nhận:**
1. **Given** phiên đang chạy, **When** người vận hành chọn sản phẩm X và chủ đề Y, **Then** phân đoạn ngay sau phân đoạn đang nói là về X,
   chủ đề Y; host không cắt ngang phân đoạn đang nói.
2. **Given** sản phẩm X không có dữ liệu cho chủ đề Y (ví dụ không có khuyến mãi), **When** người vận hành chọn, **Then** trang điều khiển
   không cho chọn tổ hợp đó (hoặc báo rõ là không có dữ liệu).

---

### User Story 6: Comment mock chen vào kịch bản đang chạy (Ưu tiên: P3)

Trong lúc host đang nói kịch bản, người vận hành gửi một comment mock từ trang điều khiển (công cụ thử của 001, ví dụ "Lan: giá bao
nhiêu?"). Host nói hết câu đang nói, trả lời comment đó theo đúng cách của 001, rồi quay lại kịch bản.

**Vì sao ưu tiên này:** Giữ đường trả lời comment của 001 chạy được cùng kịch bản, để thử giọng và nhân vật trong tình huống giống live
thật, và mở sẵn đường cho lúc mở lại phần đọc chat (ADR-026). Không có vẫn demo được.

**Kiểm thử độc lập:** Khi phiên đang chạy, gửi 10 comment mock ở các thời điểm khác nhau (giữa phân đoạn, giữa hai phân đoạn, lúc tạm
dừng), xem host trả lời và quay lại kịch bản.

**Kịch bản chấp nhận:**
1. **Given** host đang nói giữa một phân đoạn, **When** người vận hành gửi comment mock hợp lệ, **Then** host nói hết câu đang nói, không
   bắt đầu câu kế của phân đoạn, mà trả lời comment (lời trả lời theo đúng quy tắc căn cứ dữ liệu, xưng hô và bộ chặn của 001).
2. **Given** host vừa trả lời xong và hàng đợi comment trống, **When** quay lại kịch bản, **Then** host nói câu kế tiếp của phân đoạn bị
   ngắt (hoặc phân đoạn mới nếu phân đoạn cũ đã hết), như khi bấm "Tiếp tục".
3. **Given** comment mock bị bộ lọc 001 loại (spam, có link...), **When** gửi, **Then** host không ngắt kịch bản và trang điều khiển hiện
   lý do bị loại như 001.
4. **Given** comment mock được trả lời, **When** xem log, **Then** có đủ các mốc `comment_received` đến `avatar_first_frame` của 001 để đo
   độ trễ (SC-011).

### Trường hợp biên

- **File chỉ có sản phẩm chính, không có sản phẩm phụ:** host xoay vòng các chủ đề của sản phẩm chính, không nhắc tới sản phẩm phụ.
- **Chưa nạp file nội dung, hoặc màn hình host chưa mở:** "Bắt đầu" không chạy và trang điều khiển báo lý do.
- **Bấm "Bắt đầu" hai lần:** lần thứ hai không tạo phiên thứ hai; host vẫn chỉ nói một luồng.
- **Một câu sinh ra bị chặn** (giá bịa, khẳng định bị cấm, có đường link): câu đó không được nói, lý do được ghi; nếu cả phân đoạn bị
  chặn thì chuyển sang phân đoạn kế tiếp, không im quá ngưỡng ở SC-002.
- **Câu sinh ra có ký hiệu không đọc được** (gạch đầu dòng, dấu sao, biểu tượng cảm xúc, tiêu đề): bị loại khỏi câu đọc và phụ đề;
  host chỉ đọc câu nói tự nhiên.
- **Đổi file nội dung giữa phiên:** phân đoạn đang nói được nói hết; phân đoạn kế tiếp dùng nội dung mới. File mới lỗi thì giữ nội dung
  cũ và báo lỗi (như feature 001).
- **Sản phẩm bị bỏ khỏi file mới:** host không nhắc tới sản phẩm đó nữa, kể cả phân đoạn đã chuẩn bị sẵn cho nó.
- **Tạm dừng đúng lúc phân đoạn kế tiếp đang được chuẩn bị:** phân đoạn đó được giữ lại cho lúc "Tiếp tục", không mất.
- **Nguồn giọng hết hạn mức hoặc lỗi liên tục:** trang điều khiển báo rõ; phiên không treo, người vận hành quyết định dừng hay đổi giọng.
- **Có comment mock gửi từ trang điều khiển (công cụ thử của 001) khi kịch bản đang chạy:** comment được chen vào kịch bản theo
  User Story 6 và FR-028 đến FR-030.
- **Nhiều comment mock tới liền nhau:** host trả lời lần lượt theo thứ tự ưu tiên của hàng đợi 001 cho tới khi hàng đợi hết, rồi mới
  quay lại kịch bản. Comment quá hạn hoặc bị lọc thì bỏ như 001.
- **Comment mock gửi lúc tạm dừng hoặc lúc chào kết:** lúc tạm dừng, comment vào hàng đợi và được trả lời khi người vận hành bấm "Tiếp
  tục" (nếu chưa quá hạn); lúc chào kết hoặc sau khi kết thúc, comment không được trả lời.
- **Bấm "Bỏ qua" khi host đang trả lời comment:** câu trả lời đó dừng như FR-016; host trả lời comment kế tiếp trong hàng đợi, hoặc quay
  lại kịch bản nếu hàng đợi trống.

## Yêu cầu *(bắt buộc)*

### Yêu cầu chức năng

**Chạy kịch bản**
- **FR-001**: Người vận hành PHẢI bắt đầu được phiên kịch bản từ trang điều khiển. Sau khi bắt đầu, host tự nói liên tục cho tới khi
  người vận hành tạm dừng hoặc kết thúc; không cần nhập gì thêm.
- **FR-002**: Phiên PHẢI mở đầu bằng phân đoạn chào mở màn và (khi người vận hành bấm "Kết thúc") khép lại bằng phân đoạn chào kết.
- **FR-003**: Kịch bản PHẢI chia thành các phân đoạn ngắn, mỗi phân đoạn về **một sản phẩm** và **một chủ đề** trong danh sách: giới thiệu
  chung, điểm nổi bật, thông số, giá và phân loại, khuyến mãi, câu hỏi thường gặp, kêu gọi mua. Độ dài mặc định 3–6 câu, chỉnh được.
- **FR-004**: Một chủ đề chỉ được dùng cho một sản phẩm khi file nội dung có dữ liệu cho chủ đề đó (ví dụ không có khuyến mãi thì không có
  phân đoạn khuyến mãi cho sản phẩm đó).
- **FR-005**: Hệ thống PHẢI xoay vòng sản phẩm và chủ đề: hai phân đoạn liên tiếp không trùng cả sản phẩm lẫn chủ đề; sản phẩm chính
  chiếm tỷ lệ phân đoạn cao nhất (mặc định ≥ 50%, chỉnh được); mỗi sản phẩm phụ được giới thiệu ít nhất một lần trong mỗi chu kỳ xoay vòng.
- **FR-006**: Mỗi câu PHẢI được sinh trong lúc phiên đang chạy, dựa trên dữ liệu sản phẩm và những gì host đã nói trong phiên, để cùng
  một thông tin được nói lại bằng câu chữ khác. Không được đọc lại một kịch bản viết sẵn từ đầu đến cuối. Ngoại lệ duy nhất là chế độ dự
  phòng ở FR-021, chỉ khi dịch vụ sinh nội dung lỗi kéo dài.
- **FR-007**: Câu PHẢI được phát theo từng câu: câu đầu tiên của phân đoạn bắt đầu phát trước khi cả phân đoạn được sinh xong. Phân đoạn kế
  tiếp PHẢI sẵn sàng trước khi phân đoạn hiện tại nói xong, để không có khoảng lặng dài giữa hai phân đoạn.
- **FR-008**: Mỗi câu PHẢI được phát thành tiếng và hiện thành phụ đề đồng thời trên màn hình host (như feature 001).
- **FR-009**: Lời thoại PHẢI bằng tiếng Việt, là câu nói tự nhiên của host bán hàng: xưng "em", gọi người xem là "anh chị", từ ngữ miền Nam;
  không có gạch đầu dòng, ký hiệu định dạng hay biểu tượng cảm xúc trong câu đọc.

**Căn cứ dữ liệu**
- **FR-010**: Lời thoại PHẢI chỉ dùng thông tin có trong file nội dung sản phẩm. Không được tự đưa ra giá, khuyến mãi, tồn kho, công dụng,
  cam kết y tế, chính sách đổi trả hay so sánh với sản phẩm khác không có trong dữ liệu.
  *(Bổ sung 2026-11-12, ADR-050: guard chặn tất định các cụm khẳng định không có căn cứ trong `data/rules/claim_phrases.txt`, lý do
  `unsupported_claim`; cụm có trong file nội dung thì được nói.)*
- **FR-011**: Mọi con số tiền và phần trăm trong câu nói ra PHẢI khớp với số có trong file nội dung; câu có số không khớp PHẢI bị chặn trước
  khi phát và được ghi lý do.
- **FR-012**: Lời thoại KHÔNG ĐƯỢC chứa khẳng định nằm trong danh sách bị cấm của sản phẩm, và KHÔNG ĐƯỢC đọc đường link sản phẩm.
- **FR-013**: Phân đoạn "kêu gọi mua" chỉ dùng thông tin có trong dữ liệu (khuyến mãi, phân loại); không nhắc cách mua trên một nền tảng
  cụ thể (giỏ hàng, mã giảm giá, ghim sản phẩm...) trừ khi file nội dung có ghi.
- **FR-014**: Phân đoạn "câu hỏi thường gặp" chỉ dùng cặp hỏi–đáp có trong file; host có thể dẫn dắt ("nhiều anh chị hay hỏi...") nhưng câu
  trả lời phải đúng nội dung đã ghi.

**Điều khiển**
- **FR-015**: Người vận hành PHẢI có thể tạm dừng và tiếp tục. Tạm dừng: host nói hết câu đang nói rồi im, không bắt đầu câu mới. Tiếp tục:
  host nói câu kế tiếp của phân đoạn đang dở, hoặc phân đoạn mới nếu phân đoạn cũ đã hết.
- **FR-016**: Người vận hành PHẢI có thể bỏ qua: tiếng và phụ đề dừng trong vòng 1 giây, phần còn lại của phân đoạn bị bỏ, host chuyển sang
  phân đoạn kế tiếp.
- **FR-017**: Người vận hành PHẢI có thể kết thúc phiên: host nói lời chào kết (tối đa 2 câu) rồi dừng; sau đó phiên không tự chạy lại.
- **FR-018**: Người vận hành PHẢI có thể chọn sản phẩm và/hoặc chủ đề cho phân đoạn kế tiếp, chỉ trong các tổ hợp có dữ liệu; phân đoạn
  đang nói không bị cắt. Sau phân đoạn đó, xoay vòng tiếp tục như FR-005. (P3)
- **FR-019**: Trang điều khiển PHẢI hiển thị: trạng thái phiên (chưa chạy / đang chạy / tạm dừng / đang chào kết / đã kết thúc), phân đoạn
  đang nói (sản phẩm, chủ đề, câu đang nói), chế độ bình thường hay dự phòng (FR-021), phân đoạn kế tiếp, các câu bị chặn gần đây kèm lý do, và lỗi gần đây.

**Độ bền và quan sát**
- **FR-020**: Mỗi bước (sinh kịch bản, tạo tiếng, phát) PHẢI có giới hạn thời gian. Khi lỗi hoặc quá giờ: bước sinh kịch bản lỗi thì bỏ phân
  đoạn đó; bước tạo tiếng lỗi thì bỏ câu đó; ghi lỗi và tiếp tục. Một lỗi không được làm dừng phiên.
- **FR-021**: Khi dịch vụ sinh nội dung lỗi liên tục (mặc định 3 phân đoạn liên tiếp, chỉnh được), hệ thống PHẢI chuyển sang chế độ dự
  phòng: host đọc nguyên văn câu của bài giới thiệu và mô tả trong file nội dung, mỗi câu vẫn qua kiểm tra FR-011, FR-012 và vẫn tạo tiếng,
  dựng hình realtime. Trang điều khiển PHẢI báo rõ đang ở chế độ dự phòng. Trước mỗi phân đoạn dự phòng hệ thống PHẢI thử sinh lại; thành
  công thì tự quay về chế độ bình thường. Lần vào và ra chế độ dự phòng được ghi log và vào file lịch sử (FR-023).
- **FR-022**: Mỗi phân đoạn PHẢI có mã riêng; mỗi câu ghi đủ các mốc thời gian: yêu cầu phân đoạn, có câu đầu tiên, có tiếng đầu tiên, bắt
  đầu phát (ở chế độ avatar tĩnh, "bắt đầu phát" được coi là "frame đầu tiên của avatar"). Khoảng lặng giữa hai câu liên tiếp PHẢI được đo
  và ghi lại.
- **FR-023**: Khi kết thúc phiên, lịch sử các câu đã nói (kèm sản phẩm, chủ đề, mốc thời gian), các câu bị chặn, lỗi, và bảng tổng hợp
  (số phân đoạn theo sản phẩm và chủ đề, khoảng lặng trung vị/p95/lớn nhất, tỷ lệ câu trùng nguyên văn) PHẢI được lưu ra file.
- **FR-024**: Hệ thống PHẢI cho phép giả lập lỗi ở bước sinh kịch bản và bước tạo tiếng (chỉ ở môi trường phát triển) để kiểm SC-006.

**Tự kiểm tra kịch bản**
- **FR-025**: Hệ thống PHẢI có lệnh tự sinh phân đoạn mẫu cho mọi tổ hợp sản phẩm × chủ đề có dữ liệu, qua đúng cách sinh kịch bản mà
  host dùng khi live, và chấm tự động: con số không có trong file, khẳng định bị cấm, đọc link, sai xưng hô, có ký hiệu định dạng.
- **FR-026**: Kết quả chấm PHẢI được lưu lại, gồm từng phân đoạn, các câu vi phạm kèm lý do, tổng số vi phạm, và so sánh với lần chạy trước.

**Comment chen vào kịch bản (P3)**
- **FR-028**: Khi phiên kịch bản đang chạy, comment mock gửi từ trang điều khiển PHẢI đi qua bộ lọc, phân loại ưu tiên và hàng đợi của 001.
  Comment hợp lệ làm host dừng kịch bản ở cuối câu đang nói (không cắt giữa câu) và trả lời bằng đúng đường trả lời của 001 (căn cứ dữ
  liệu, bộ chặn, xưng hô).
- **FR-029**: Sau khi trả lời hết các comment trong hàng đợi, host PHẢI quay lại kịch bản: câu kế tiếp của phân đoạn bị ngắt, hoặc phân
  đoạn mới nếu phân đoạn cũ đã hết. Lời trả lời comment không tính là phân đoạn khi xoay vòng (FR-005) và khi thống kê SC-004.
- **FR-030**: Lời trả lời comment PHẢI có trong lịch sử đã nói (FR-023) kèm comment gốc, để kịch bản sau đó không nói lặp lại nguyên văn.
  Comment gửi lúc tạm dừng được giữ cho tới khi "Tiếp tục" (trừ khi quá hạn); comment gửi lúc chào kết hoặc sau khi kết thúc không được
  trả lời.

**Bảo mật**
- **FR-027**: Chỉ nội dung sản phẩm, lời host đã nói và chữ của comment mock được gửi tới dịch vụ sinh nội dung. Khóa dịch vụ và thông tin bí mật KHÔNG ĐƯỢC xuất
  hiện trong log, file lịch sử hay trên trang điều khiển.

### Ràng buộc từ Hiến pháp

- [x] Điều I (realtime / nhãn AI / 1 host 1 tài khoản): mỗi câu được sinh chữ, tạo tiếng và dựng hình ngay lúc phát (FR-006, FR-007);
  không lưu tiếng hay hình của câu đã nói để phát lại. Nhãn "AI" luôn hiện trên màn hình host, kể cả khi tạm dừng (US1 #6, US2 #1). Nhân
  vật và giọng của phiên thuộc đúng một khách.
- [x] Điều II (đồng ý / bảo mật): không gửi dữ liệu người xem ra ngoài (feature này không đọc chat thật; comment mock do người vận hành
  tự gõ, US6); khóa dịch vụ không xuất hiện trong log (FR-027). Dùng nhân vật và giọng nào thì vẫn theo điều kiện đồng ý của feature 003 và 005.
- [x] Điều III (trả lời có căn cứ): FR-010 đến FR-014. Bộ tự kiểm tra kịch bản (FR-025, FR-026) là bộ regression bắt buộc chạy lại mỗi khi
  đổi cách sinh kịch bản, và không được tăng số vi phạm.
- [x] Điều VI (độ trễ): nội dung chính là kịch bản, không có mốc "nhận comment". Đo (a) từ lúc bấm "Bắt đầu" đến câu đầu tiên phát
  ≤ 5 giây (SC-001), (b) khoảng lặng giữa hai câu (SC-002), và (c) với comment mock chen vào (US6), mốc `comment_received` →
  `avatar_first_frame` (SC-011). Hiến pháp Điều VI đã sửa ở bản 1.2.0 (ADR-029) theo đúng ba mục tiêu này.
- [x] Điều VIII (quan sát được): FR-020, FR-022, FR-023, FR-024.

### Thực thể chính

- **Phiên kịch bản:** một lần chạy từ "Bắt đầu" tới "Kết thúc". Thuộc tính: trạng thái, chế độ (bình thường / dự phòng), thời điểm bắt đầu/kết
  thúc, file nội dung đang dùng, lịch sử phân đoạn. Mỗi lúc chỉ có một phiên chạy.
- **Chủ đề:** một loại nội dung trong danh sách cố định ở FR-003, cộng với "chào mở màn" và "chào kết" (không gắn sản phẩm). Mỗi chủ đề có
  điều kiện dữ liệu (cần mục nào của sản phẩm).
- **Phân đoạn:** đơn vị nội dung, gắn một sản phẩm và một chủ đề. Thuộc tính: mã phân đoạn, các câu, trạng thái (đang chuẩn bị / đang nói /
  xong / bị bỏ / lỗi), nguồn gốc (xoay vòng tự động hay người vận hành chọn).
- **Câu:** đơn vị phát. Thuộc tính: chữ đọc, phụ đề, các mốc thời gian, trạng thái (đã nói / bị chặn kèm lý do / lỗi tạo tiếng).
- **Lịch sử đã nói:** các câu đã nói trong phiên; dùng để tránh lặp nguyên văn và để thống kê tỷ lệ sản phẩm.
- **Báo cáo kiểm tra kịch bản:** kết quả một lần chạy FR-025: phân đoạn mẫu, vi phạm, tổng kết, so sánh lần trước.
- Dùng lại từ feature 001: **File nội dung sản phẩm**, **Sản phẩm**, **Phân loại**, **Khẳng định bị cấm**.

## Tiêu chí thành công *(bắt buộc)*

- **SC-001**: Ở ≥ 9/10 lần bấm "Bắt đầu" trên laptop dev với giọng đang dùng, câu chào mở màn bắt đầu phát trong vòng 5 giây.
- **SC-002**: Trong phiên 30 phút, khoảng lặng giữa hai câu liên tiếp (tính cả giữa hai phân đoạn, không tính lúc tạm dừng và lúc giả lập
  lỗi) có p95 ≤ 1,5 giây và không khoảng lặng nào quá 5 giây. Đây là tiêu chí demo số 3 trong `docs/PRD.md` §3 (thay cho độ trễ
  comment, chốt 2026-11-01).
- **SC-003**: 0 câu nói ra chứa con số tiền/phần trăm không có trong file, khẳng định bị cấm, hoặc đường link, khi kiểm toàn bộ lịch sử phụ
  đề của phiên 30 phút.
- **SC-004**: Trong phiên 30 phút: sản phẩm chính chiếm ≥ 50% số phân đoạn; trong mỗi khoảng 10 phút, mỗi sản phẩm phụ có ít nhất 1 phân
  đoạn.
- **SC-005**: Trong phiên 30 phút, ≤ 5% số câu trùng nguyên văn (bỏ qua dấu câu và hoa/thường) với một câu đã nói trước đó trong phiên,
  và không có hai phân đoạn nào giống nhau hoàn toàn. Không tính các câu nói trong chế độ dự phòng (FR-021).
- **SC-006**: Phiên 30 phút có ít nhất 3 lần giả lập lỗi ở bước sinh kịch bản và 3 lần ở bước tạo tiếng: phiên không dừng, mỗi lỗi chỉ làm
  mất phân đoạn hoặc câu đó, mỗi khoảng lặng do lỗi ≤ 8 giây, và mỗi lỗi có trong nhật ký kèm bước lỗi.
- **SC-007**: Ở 100% lần thử (≥ 10 lần mỗi lệnh), tính từ lúc bấm: **bỏ qua** làm tiếng và phụ đề dừng trong ≤ 1 giây; **tạm dừng** không để
  câu mới nào bắt đầu sau câu đang nói; **tiếp tục** làm câu kế tiếp phát trong ≤ 3 giây.
- **SC-008**: Bộ tự kiểm tra kịch bản cho 0 vi phạm ở 3 lần chạy liên tiếp với file nội dung mẫu.
- **SC-009**: Người vận hành nghe 10 phân đoạn chọn ngẫu nhiên từ phiên 30 phút và đánh giá ≥ 8/10 phân đoạn "nói tự nhiên như host bán
  hàng, đúng xưng hô, không lủng củng". SC-009 cùng SC-003 là tiêu chí demo số 2 trong `docs/PRD.md` §3 (thay cho bộ 10 câu hỏi mẫu,
  chốt 2026-11-01).
- **SC-010**: Nhãn "AI" hiển thị trong 100% ảnh chụp màn hình host lấy ngẫu nhiên trong phiên 30 phút, kể cả lúc tạm dừng.
- **SC-011**: Với ≥ 10 comment mock hợp lệ gửi lúc kịch bản đang chạy: 100% được trả lời rồi host quay lại kịch bản; không câu kịch bản nào
  bị cắt giữa chừng vì comment; thời gian từ `comment_received` đến `avatar_first_frame` của lời trả lời có p95 < 5 giây (tính cả thời
  gian nói hết câu đang nói).

## Giả định

- **Nguồn nội dung:** dùng đúng file nội dung sản phẩm của feature 001 (bài giới thiệu, mô tả, thông số, phân loại và giá, câu hỏi thường gặp,
  khuyến mãi, khẳng định bị cấm, link). Không thêm mục mới vào mẫu file. Bài giới thiệu là chất liệu chính cho chủ đề "giới thiệu chung".
- **Xưng hô và giọng điệu:** như đã chốt ở 001 (xưng "em", gọi "anh chị", từ ngữ miền Nam). Giọng điệu bán hàng sôi nổi nhưng không phóng đại
  ngoài dữ liệu.
- **Độ dài phân đoạn và tỷ lệ sản phẩm:** 3–6 câu mỗi phân đoạn, sản phẩm chính ≥ 50% số phân đoạn. Đây là mặc định thiết kế, chỉnh được,
  không phải số liệu kinh doanh.
- **Tạm dừng:** có hiệu lực ở cuối câu đang nói, không phải cuối phân đoạn (khác 001, vì một phân đoạn có thể dài 20–45 giây).
- **Giọng và nhân vật:** chạy được với mọi nguồn giọng và chế độ nhân vật đang có (giọng giả, giọng của 003; avatar tĩnh hoặc nhân vật của 005).
  SC-001, SC-002 đo với giọng đang dùng trên laptop dev; khi đổi giọng hoặc máy thì đo lại.
- **Hạn mức dịch vụ miễn phí:** host nói liên tục nên số lần gọi dịch vụ sinh nội dung và tạo tiếng trong 30 phút nhiều hơn hẳn chế độ trả lời
  comment (ADR-026). Chưa biết hạn mức cụ thể; plan phải ước lượng số lần gọi mỗi phiên và đối chiếu với hạn mức (`docs/RISKS.md` Q12).
- **Lịch sử đã nói** chỉ giữ trong một phiên; phiên mới bắt đầu lại từ đầu.
- **Phân đoạn kêu gọi mua** dùng chung cho demo trên Meet/YouTube và sau này trên Shopee, nên mặc định không nhắc cơ chế của nền tảng nào
  (FR-013).

## Ngoài phạm vi

- Đọc chat thật (YouTube, Shopee) để trả lời người xem (hoãn theo ADR-026).
- Xoay vòng nội dung cho cả ngày 15 giờ và lịch live (M2).
- Người vận hành gõ chỉ dẫn tự do cho host (ví dụ "nói là đang giảm 50%"); chỉ cho chọn sản phẩm và chủ đề có sẵn (FR-018).
- Hiện ảnh sản phẩm, bảng giá hay đồ họa khác trên màn hình host ngoài phụ đề và nhãn "AI".
- Nhạc nền, hiệu ứng âm thanh, cảm xúc giọng theo nội dung.
- Viết sẵn toàn bộ kịch bản trước phiên rồi đọc lại.
- Sửa Hiến pháp Điều VI: đã làm riêng qua `/sdd.constitution` (bản 1.2.0, ADR-029). `docs/PRD.md` §3 số 2–3 đã được sửa trong phiên làm rõ 2026-11-01.

## Làm rõ

<!-- /sdd.clarify ghi vào đây. Mỗi phiên một mục. -->

### Phiên 2026-11-01

- Q: Khi dịch vụ sinh nội dung lỗi kéo dài, host đọc văn bản có sẵn hay im lặng? → A: Đọc nguyên văn bài giới thiệu và mô tả trong
  file nội dung (chế độ dự phòng), vẫn qua bộ chặn, tiếng và hình vẫn sinh realtime; trang điều khiển báo rõ; thử sinh lại trước mỗi
  phân đoạn dự phòng và tự quay về khi được. Sửa: US3 #3, FR-006, FR-019, FR-021, SC-005, thực thể "Phiên kịch bản".
- Q: Comment mock có được chen vào kịch bản không, hay hai chế độ tách riêng? → A: Cho chen vào: host nói hết câu đang nói, trả lời
  comment theo đường của 001, rồi quay lại kịch bản. Sửa: thêm US6 (P3), FR-028 đến FR-030, SC-011; sửa FR-027, ràng buộc Điều II, VI,
  trường hợp biên.
- Q: Tiêu chí demo nào thay cho `docs/PRD.md` §3 số 2–3? → A: Số 2 = SC-009 (≥ 8/10 phân đoạn nghe tự nhiên) cùng SC-003 (0 câu bịa giá,
  khẳng định cấm, link); số 3 = SC-002 (khoảng lặng p95 ≤ 1,5 giây, tối đa 5 giây). Sửa: SC-002, SC-009, Ngoài phạm vi, `docs/PRD.md` §3.

## Checklist chất lượng spec

- [x] Không có chi tiết triển khai (ngôn ngữ, framework, API, cấu trúc code)
- [x] Mọi FR đều kiểm thử được và không mơ hồ
- [x] Mọi SC đều đo được và không phụ thuộc công nghệ
- [x] Mỗi user story kiểm thử độc lập được và có kịch bản chấp nhận
- [x] Trường hợp biên đã liệt kê
- [x] Phạm vi và ngoài phạm vi rõ ràng
- [x] Ràng buộc Hiến pháp liên quan đã được nêu
- [x] Không còn `[NEEDS CLARIFICATION]` (giải xong ở phiên làm rõ 2026-11-01)

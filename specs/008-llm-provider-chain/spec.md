# Đặc tả tính năng: Chuỗi model LLM miễn phí, tự chuyển model khi lỗi

- **Feature ID:** `008-llm-provider-chain` · **Branch:** `main` (ADR-027) · **Ngày tạo:** 2026-11-03
- **Trạng thái:** Done (2026-11-05) <!-- Draft → Clarified → Planned → Tasked → In progress → Done -->
- **Mốc roadmap:** M1a (bộ não của host; chặn các bước LLM thật G1–G5 của 004, T075–T079)
- **Mô tả gốc:** "008-llm-provider-chain" (bổ sung từ ADR-034, ADR-035 và dòng "Đề xuất chưa tạo" trong `progress/FEATURES.md`: một
  bộ sinh lời thoại mới đi qua một chuỗi model miễn phí đã chọn sẵn và ghim tên, tự chuyển sang model kế khi model đang dùng lỗi).

Bối cảnh: benchmark 2026-11-02 cho thấy Gemini free tier lỗi 30/31 lượt (quá tải, hết hạn mức). Benchmark 2026-11-02 và 2026-11-03
chọn ra thứ tự model trong ADR-035: (1) SEA-LION v4 27B, (2) gpt-oss-120b, (3) Qwen3.8 27B, (4) Gemini. Mỗi nơi miễn phí chỉ đủ khoảng
1 giờ show; ghép thành chuỗi thì hạn mức cộng lại và một nơi quá tải không làm dừng show. Dịch vụ gom key chạy local đã cài theo
ADR-034. Feature này chỉ lo phần host gọi chuỗi model lúc live; prompt, bộ tách câu, guard và luồng show của 004 giữ nguyên.

**Phạm vi dùng (làm rõ 2026-11-03):** dịch vụ gom key và chuỗi model miễn phí chỉ cần chạy được **một ngày demo**. Nếu demo đạt thì đổi
sang dịch vụ khác (cần ADR mới). Vì vậy feature này ưu tiên **độ đúng** (người xem chỉ nghe đúng model đã benchmark, cấu hình sai bị
phát hiện trước khi lên sóng) hơn là chạy bền nhiều giờ liền.

## Kịch bản người dùng và kiểm thử *(bắt buộc)*

### User Story 1: Host nói kịch bản và trả lời comment bằng model đầu chuỗi (Ưu tiên: P1)

Người vận hành chọn bộ sinh lời thoại mới trong cấu hình, khai báo model đầu chuỗi, rồi khởi động app. App kiểm một lần rằng key và tên
model của mọi mục đều dùng được; sai thì không khởi động. Người vận hành bấm "Bắt đầu show" như ở 004. Host nói kịch bản và trả lời
comment mock bằng model đó, vẫn theo câu, vẫn qua bộ làm sạch và guard, vẫn chỉ dựa trên dữ liệu sản phẩm. Mỗi lượt ghi rõ model và nhà
cung cấp nào đã trả lời.

**Vì sao ưu tiên này:** Đây là phần nhỏ nhất đủ để thay Gemini: chạy được các bước LLM thật của 004 (G1) và có host nói thật khi Gemini
quá tải. Chưa cần chuỗi nhiều model.

**Kiểm thử độc lập:** Khai báo chuỗi chỉ có một mục, chạy một show ngắn 5 phút với dữ liệu mẫu và gửi vài comment mock. Host nói
liên tục, giá đúng file, log mỗi lượt có tên model đã ghim.

**Kịch bản chấp nhận:**
1. **Given** chuỗi có một mục hợp lệ và dữ liệu sản phẩm mẫu đã nạp, **When** bấm "Bắt đầu show", **Then** câu chào mở màn phát trong
   ngân sách của 004 (≤ 5 giây) và các phân đoạn sau nối tiếp như khi dùng Gemini.
2. **Given** show đang chạy, **When** một comment mock hợp lệ đến, **Then** host trả lời bằng cùng bộ sinh lời thoại, rồi quay lại
   kịch bản như 004 US6.
3. **Given** bất kỳ lượt nào (phân đoạn hay câu trả lời), **When** xem log phiên, **Then** lượt đó ghi tên model và nhà cung cấp đã
   trả lời, gắn với mã phân đoạn hoặc mã lượt nói, cùng số token nếu nhà cung cấp trả về.
4. **Given** model trả về câu có giá không có trong file, **When** câu đó đi qua guard, **Then** câu bị chặn y như với Gemini; bộ sinh
   lời thoại mới không bỏ qua bước nào của guard.
5. **Given** cấu hình khai tên model là "tự chọn" (để dịch vụ gom key tự chọn model), **When** khởi động, **Then** hệ thống từ chối
   với thông báo nêu rõ mục nào sai; host không được nói bằng model không rõ tên.
6. **Given** một mục có key sai, tên model không có hoặc chưa dùng được trên dịch vụ, hoặc dịch vụ gom key chưa bật, **When** khởi động
   app, **Then** app không khởi động; thông báo nêu mục nào và lỗi gì, không in giá trị key.

---

### User Story 2: Model đang dùng lỗi thì tự chuyển sang model kế, show không dừng (Ưu tiên: P1)

Chuỗi có nhiều mục theo thứ tự ADR-035. Khi model đang dùng từ chối vì hết hạn mức, quá tải, lỗi máy chủ, quá giờ chờ, trả về rỗng, hoặc
dịch vụ gom key đưa lượt sang nền tảng khác nền tảng đã khai, lượt đó tự chuyển sang mục kế trong chuỗi. Mục vừa lỗi nghỉ một khoảng cố
định rồi mới được thử lại. Hết cả chuỗi thì báo lỗi như hiện nay để show vào chế độ dự phòng của 004.

**Vì sao ưu tiên này:** Một nơi miễn phí chỉ đủ khoảng 1 giờ show và có lúc quá tải; tổng duyệt G5 và ngày demo cần chuỗi. Không có
story này thì chỉ đổi Gemini lấy một điểm hỏng khác. Chuỗi chỉ cần trụ hết một ngày demo, không cần cơ chế cho phiên chạy nhiều ngày.

**Kiểm thử độc lập:** Chạy show với chuỗi 2–3 mục, giả lập lỗi ở mục 1 (dùng công cụ giả lập lỗi chỉ có ở môi trường dev). Host vẫn nói
liên tục bằng mục 2; log ghi lần chuyển và lý do.

**Kịch bản chấp nhận:**
1. **Given** mục 1 từ chối ngay (hết hạn mức hoặc quá tải) trước khi ra chữ nào, **When** host cần phân đoạn kế, **Then** chính lượt đó
   được gửi sang mục 2; người xem không nghe khác gì ngoài giọng văn của model khác, và log ghi `mục 1 → mục 2` kèm lý do.
2. **Given** mục 1 không ra chữ nào sau giới hạn chờ câu đầu của mục đó, **When** hết giờ, **Then** lượt đó chuyển sang mục kế, không chờ
   tiếp mục 1.
3. **Given** mục 1 đã ra vài câu rồi mới lỗi giữa phân đoạn, **When** lỗi xảy ra, **Then** các câu đã nhận vẫn được nói, phân đoạn dừng ở
   đó, không có câu nào của model khác chen vào cùng phân đoạn; phân đoạn kế dùng mục kế.
4. **Given** mục 1 vừa lỗi và đang nghỉ, **When** có lượt mới trong lúc nghỉ, **Then** mục 1 bị bỏ qua ngay, không tốn thời gian chờ.
5. **Given** mọi mục đều lỗi hoặc đang nghỉ, **When** host cần lượt kế, **Then** lượt đó báo lỗi ngay (không chờ vô ích) và show xử lý
   như một lần LLM lỗi của 004: đủ số lần liên tiếp thì vào chế độ dự phòng, không dừng phiên.
6. **Given** host đang nói bằng mục 2 vì mục 1 lỗi, **When** mục 1 hết thời gian nghỉ và có lượt mới, **Then** lượt đó thử mục 1 trước
   (quay lại ngay); mục 1 lỗi tiếp thì lượt đó chuyển xuống như kịch bản 1. Model chỉ đổi giữa hai lượt, không đổi giữa một phân đoạn.
7. **Given** câu của model bị guard chặn, **When** guard chặn, **Then** đó không tính là lỗi nhà cung cấp và không làm chuyển model.
8. **Given** mục 1 đi qua dịch vụ gom key và khai nền tảng mong đợi (ví dụ Cloudflare), **When** dịch vụ báo lượt này do một nền tảng
   khác phục vụ (hoặc không báo nền tảng), **Then** lượt đó bị từ chối trước khi có chữ nào được nói, chuyển sang mục kế, log ghi nền tảng
   mong đợi và nền tảng thật; người xem không nghe câu nào từ nền tảng chưa benchmark.

---

### User Story 3: Người vận hành biết host đang nói bằng model nào (Ưu tiên: P2)

Trên trang điều khiển, người vận hành thấy model đang nói, mục nào đang nghỉ và vì sao. Cuối show, bản tổng hợp cho biết mỗi model nói bao
nhiêu phân đoạn và câu trả lời, và bao nhiêu lần chuyển theo lý do.

**Vì sao ưu tiên này:** Không cần để show chạy, nhưng cần để tổng duyệt và chuẩn bị ngày demo: biết lúc nào chuỗi tụt xuống model kém
hơn, và ghi được model nào đã nói vào "Kết quả kiểm chứng" của 004 (T075–T079).

**Kiểm thử độc lập:** Chạy show có giả lập lỗi ở mục 1, nhìn trang điều khiển và đọc bản tổng hợp cuối show.

**Kịch bản chấp nhận:**
1. **Given** show đang chạy bằng mục 1, **When** mở trang điều khiển, **Then** thấy tên model (nhãn ngắn) đang nói.
2. **Given** chuỗi vừa chuyển xuống mục 2 vì mục 1 lỗi, **When** nhìn trang điều khiển, **Then** thấy cảnh báo "đang dùng model dự
   phòng" kèm lý do và thời điểm mục 1 được thử lại, trong vòng vài giây sau lần chuyển.
3. **Given** show đã kết thúc, **When** đọc bản tổng hợp show, **Then** có số phân đoạn và câu trả lời theo từng model và số lần chuyển
   theo lý do.

---

### User Story 4: Kiểm từng model trước khi cho vào chuỗi (Ưu tiên: P3)

Trước khi thêm hoặc đổi một model trong chuỗi, người vận hành chạy bộ 10 câu hỏi mẫu của 001 và bộ tự kiểm tra kịch bản của 004 với
riêng model đó. Báo cáo ghi model nào đã trả lời từng mục.

**Vì sao ưu tiên này:** ADR-035 bắt mỗi model mới phải qua cùng benchmark trước khi dùng lúc live (Điều III). Benchmark đã làm tay qua bàn
thử ADR-034; story này đưa nó vào công cụ kiểm của project để lặp lại được.

**Kiểm thử độc lập:** Chạy bộ câu hỏi mẫu một lần với cả chuỗi, một lần ghim riêng mục 2; so hai báo cáo.

**Kịch bản chấp nhận:**
1. **Given** chuỗi đã khai, **When** chạy bộ câu hỏi mẫu hoặc bộ tự kiểm tra kịch bản và chọn một mục, **Then** mọi lượt gọi chỉ đi
   tới mục đó, không tự chuyển sang mục khác; lượt lỗi được ghi là lỗi dịch vụ, không tính là trả lời sai.
2. **Given** chạy với cả chuỗi, **When** đọc báo cáo, **Then** mỗi câu hỏi hoặc phân đoạn ghi model và nền tảng đã trả lời.
3. **Given** kết quả lần chạy mới, **When** so với lần trước, **Then** báo cáo cho thấy model nào được dùng ở mỗi lần, để không so nhầm
   điểm của hai model khác nhau.

### Trường hợp biên

- Dịch vụ gom key chạy local chưa bật lúc khởi động: app không khởi động (US1 #6). Dịch vụ tắt giữa show: các mục đi qua nó lỗi kết nối,
  nghỉ, chuỗi rơi xuống mục gọi thẳng nhà cung cấp (nếu có); trang điều khiển hiện các mục đó đang nghỉ với lý do lỗi kết nối.
- Nhà cung cấp trả luồng không có chữ nào: tính là lỗi, chuyển mục (ADR-035, lỗi `empty_completion`).
- Key bị thu hồi hoặc model bị gỡ **giữa show** (lần kiểm lúc khởi động đã qua): xử lý như mọi lỗi khác trước câu đầu: chuyển mục, nghỉ
  khoảng cố định, hết nghỉ thì thử lại. Chấp nhận việc thử lại mỗi khoảng nghỉ vì chuỗi chỉ chạy một ngày demo.
- Nhà cung cấp báo thời gian nên chờ trước khi gọi lại (kể cả hết hạn mức ngày): mục vẫn chỉ nghỉ khoảng cố định rồi thử lại; lần thử
  lại bị từ chối ngay nên chỉ tốn rất ít thời gian (SC-003).
- Dịch vụ gom key trả lại câu trả lời đã lưu từ lần gọi trước thay vì sinh mới: không có nền tảng thật, nên bị từ chối như nền tảng không
  khớp (Điều I: lời thoại phải sinh realtime).
- Phân đoạn kịch bản và câu trả lời comment gọi chuỗi cùng lúc: mỗi lượt chọn mục độc lập; một lượt làm mục 1 nghỉ thì lượt kia cũng thấy
  mục 1 đang nghỉ.
- Lượt đã bị người vận hành bỏ qua, tạm dừng hoặc kết thúc show trong lúc đang chờ mục 1: dừng lượt đó, không chuyển sang mục kế.
- Toàn bộ chuỗi đang nghỉ lúc bấm "Bắt đầu show": show vẫn bắt đầu và vào chế độ dự phòng như 004 khi LLM lỗi; trang điều khiển báo rõ
  không có model nào sẵn sàng.
- Một mục ra câu dài hơn số câu yêu cầu: xử lý như 004 hiện nay (bỏ câu thừa), không coi là lỗi nhà cung cấp.
- Model trả lời bằng tiếng khác hoặc nội dung lạc đề: không phải lỗi nhà cung cấp; guard và bộ chấm xử lý như với Gemini.

## Yêu cầu *(bắt buộc)*

### Yêu cầu chức năng

**Bộ sinh lời thoại theo chuỗi (US1)**

- **FR-001**: Hệ thống PHẢI có thêm một bộ sinh lời thoại chọn được bằng cấu hình, dùng cho cả kịch bản (004) và trả lời comment (001).
  Bộ sinh lời thoại Gemini hiện có và bộ giả dùng cho test vẫn chọn được.
- **FR-002**: Bộ sinh lời thoại mới PHẢI dùng cùng prompt, cùng cách tách câu, cùng bộ làm sạch và guard như bộ Gemini; câu ra theo
  từng câu ngay khi đủ một câu, không chờ cả phân đoạn.
- **FR-003**: Cấu hình PHẢI khai được một chuỗi có thứ tự gồm một hoặc nhiều mục. Mỗi mục có: nhãn ngắn để hiển thị, địa chỉ dịch vụ,
  tên model ghim cứng, tham chiếu tới key (tên biến môi trường, không phải giá trị key), tham số riêng của model (ví dụ mức suy luận),
  và với mục đi qua dịch vụ gom key: nền tảng mong đợi (nền tảng đã benchmark, FR-024). Một mục có thể đi qua dịch vụ gom key chạy local
  (ADR-034) hoặc gọi thẳng một nhà cung cấp có cùng kiểu giao tiếp.
- **FR-004**: Hệ thống PHẢI từ chối khởi động bộ sinh lời thoại mới khi một mục thiếu tên model, dùng tên model "tự chọn", thiếu địa chỉ,
  trỏ tới biến key không có giá trị, hoặc đi qua dịch vụ gom key mà không khai nền tảng mong đợi; thông báo nêu mục nào và lỗi gì, không in
  giá trị key.
- **FR-005**: Mỗi lượt gọi PHẢI ghi log tên model, nhà cung cấp (nền tảng thật) và nhãn mục đã trả lời, gắn `segment_id` (kịch bản) hoặc
  `utterance_id` (comment), cùng số token vào và token ra nếu nhà cung cấp trả về.
- **FR-006**: Bộ sinh lời thoại mới PHẢI giữ các mốc log độ trễ hiện có (`llm_first_sentence` và các mốc của 004) để đo theo Điều VI.

**Tự chuyển model (US2)**

- **FR-007**: Lượt gọi PHẢI chuyển sang mục kế khi mục đang thử gặp bất kỳ lỗi nào trước câu đầu: hết hạn mức, quá tải hoặc lỗi máy chủ,
  lỗi kết nối, hết giới hạn chờ câu đầu, luồng kết thúc mà không có chữ nào, nhà cung cấp từ chối key hoặc tên model (lỗi cấu hình lộ ra
  giữa show), nội dung bị bộ lọc của nhà cung cấp chặn, hoặc nền tảng không khớp (FR-024). Lỗi chỉ được chuyển **trước khi lượt có câu
  đầu tiên**.
- **FR-008**: Khi mục đang dùng lỗi sau khi đã ra ít nhất một câu, lượt đó PHẢI dừng ở câu cuối đã nhận và báo lỗi như hiện nay; không
  ghép câu của model khác vào cùng phân đoạn hoặc cùng câu trả lời.
- **FR-024**: Với mục khai nền tảng mong đợi, hệ thống PHẢI kiểm nền tảng thật mà dịch vụ gom key báo cho lượt đó **trước khi nhận chữ
  nào**. Nền tảng khác nền tảng mong đợi, hoặc dịch vụ không báo nền tảng, thì lần thử đó bị từ chối và lượt chuyển sang mục kế (FR-007);
  không câu nào của lần thử đó được nói.
- **FR-009**: Mỗi mục PHẢI có giới hạn chờ câu đầu riêng. Tổng thời gian một lượt chờ qua các mục PHẢI nằm trong giới hạn thời gian mà
  luồng show của 004 dành cho một phân đoạn, để show không vượt ngưỡng khoảng lặng vì chờ chuỗi.
- **FR-010**: Mục vừa gặp lỗi ở FR-007 hoặc FR-008 PHẢI nghỉ một khoảng cố định trong cấu hình (trừ lỗi do bộ lọc nội dung: chuyển mục
  nhưng không nghỉ); trong lúc nghỉ, mọi lượt bỏ qua mục đó mà không gọi tới. Thời gian chờ mà nhà cung cấp báo không làm đổi khoảng nghỉ.
- **FR-011**: Khi khởi động app với bộ sinh lời thoại mới, hệ thống PHẢI kiểm một lần, không tốn lượt sinh lời thoại, rằng với mọi mục:
  dịch vụ trả lời được, key được chấp nhận, và tên model có trên dịch vụ và đang dùng được. Một mục không đạt thì app **không khởi động**;
  thông báo nêu mục nào, lỗi gì, không in giá trị key. Giữa show không có lần kiểm định kỳ nào khác.
- **FR-012**: Khi mọi mục đều lỗi trong cùng lượt hoặc đang nghỉ, lượt PHẢI báo lỗi ngay bằng đúng loại lỗi mà luồng show và luồng comment
  đang xử lý, để 004 đếm lỗi liên tiếp và vào chế độ dự phòng như cũ. Log ghi "hết chuỗi" kèm lý do của từng mục.
- **FR-013**: Lượt bị hủy (bỏ qua, tạm dừng, kết thúc show) PHẢI dừng ngay, không chuyển sang mục kế và không làm mục đang thử bị nghỉ.
- **FR-014**: Câu bị guard chặn, câu vượt số câu yêu cầu, hoặc nội dung lạc đề KHÔNG được tính là lỗi nhà cung cấp và KHÔNG làm chuyển mục.
- **FR-015**: Mỗi lượt mới PHẢI bắt đầu thử từ mục có thứ tự cao nhất đang sẵn sàng (không nghỉ). Khi mục ưu tiên cao hơn hết nghỉ, lượt
  kế dùng lại mục đó ngay, không ở lại mục dự phòng đang chạy.
- **FR-016**: Công cụ giả lập lỗi ở môi trường dev (đang có cho bước sinh kịch bản ở 004) PHẢI giả lập được lỗi ở **một mục cụ thể** của
  chuỗi, ít nhất các loại: hết hạn mức, quá tải, hết giờ chờ câu đầu, luồng rỗng, nền tảng không khớp, và lỗi sau câu đầu, để đo US2 mà
  không cần chờ nhà cung cấp lỗi thật. Ngoài môi trường dev công cụ này bị tắt.

**Theo dõi (US3)**

- **FR-017**: Trang điều khiển PHẢI hiện nhãn mục đang nói ở lượt gần nhất, cảnh báo khi đang dùng mục không phải mục 1 (kèm lý do), và
  danh sách mục với trạng thái sẵn sàng hoặc đang nghỉ (lý do, lúc thử lại). Cập nhật trong vòng 2 giây sau khi trạng thái đổi.
- **FR-018**: Bản tổng hợp cuối show PHẢI có theo từng mục: số phân đoạn và câu trả lời đã nói, và số lần bị chuyển qua theo lý do. Không
  cần thống kê request hay token cho cả show (token từng lượt đã có trong log, FR-005).
- **FR-019**: Khi một mục lỗi kết nối giữa show (ví dụ dịch vụ gom key vừa tắt), trang điều khiển PHẢI hiện mục đó đang nghỉ với lý do
  lỗi kết nối như mọi lỗi khác (FR-017); không có cảnh báo hay lần kiểm riêng cho dịch vụ gom key.
- **FR-020**: Người vận hành PHẢI đổi chuỗi (thêm, bỏ, đổi thứ tự mục) bằng cấu hình trước khi khởi động; giữa show trang điều khiển
  chỉ hiện trạng thái chuỗi (FR-017), không có nút ghim, tắt hay bỏ qua một mục.

**Kiểm từng model (US4)**

- **FR-021**: Bộ câu hỏi mẫu (001) và bộ tự kiểm tra kịch bản (004) PHẢI chạy được với cả chuỗi hoặc ghim riêng một mục; khi ghim, không
  tự chuyển mục và lượt lỗi ghi là lỗi dịch vụ (không tính điểm), như quy ước mã thoát hiện có của bộ tự kiểm tra. Kiểm nền tảng
  (FR-024) vẫn áp dụng khi ghim.
- **FR-022**: Báo cáo của hai bộ kiểm PHẢI ghi model và nền tảng đã trả lời từng câu hỏi hoặc phân đoạn, và phần so với lần trước PHẢI cho
  biết hai lần chạy dùng model nào.
- **FR-023**: Thử chuỗi bằng test tự động PHẢI chạy được không cần mạng hay key: có nhà cung cấp giả mô phỏng các loại lỗi ở FR-007,
  nền tảng không khớp (FR-024), lần kiểm lúc khởi động (FR-011) và luồng câu bình thường. Test gọi nhà cung cấp thật có marker riêng và
  không chạy mặc định (Điều V); test này thay test Gemini thật cho bước G1 của 004.

### Ràng buộc từ Hiến pháp

- [x] Điều I (realtime / nhãn AI / 1 host 1 tài khoản): lời thoại vẫn sinh realtime theo từng lượt; không lưu sẵn câu để phát lại, và câu
  trả lời đã lưu của dịch vụ gom key bị từ chối (FR-024). Không ảnh hưởng nhãn AI.
- [x] Điều II (đồng ý / bảo mật): key chỉ đọc từ `.env`; cấu hình chuỗi chỉ chứa tên biến key; log, thông báo lỗi và trang điều khiển
  không bao giờ hiện giá trị key (kể cả khi nhà cung cấp trả lại key trong nội dung lỗi). Key từng nhà cung cấp trong dịch vụ gom key
  nằm ngoài repo (ADR-034). Chỉ gửi dữ liệu sản phẩm và comment mock qua các nhà cung cấp chưa kiểm điều khoản (ADR-034, ràng buộc 5).
- [x] Điều III (trả lời có căn cứ): cùng prompt và guard cho mọi model; mỗi model trong chuỗi phải qua bộ câu hỏi mẫu (≥ 8/10) và bộ tự kiểm
  tra kịch bản (0 vi phạm) trước khi dùng lúc live (ADR-035). Kiểm nền tảng (FR-024) bảo đảm câu được nói đến từ đúng nền tảng đã chấm.
  Đổi model, nền tảng hoặc thứ tự chuỗi thì chạy lại cả hai bộ (US4).
- [x] Điều IV (adapter): thêm một bộ sinh lời thoại mới cho mọi nhà cung cấp cùng kiểu giao tiếp; lõi pipeline, `ShowDirector` và guard
  không đổi cách làm việc.
- [x] Điều V (test trước): chuyển mục, nghỉ, hết chuỗi, kiểm lúc khởi động và kiểm nền tảng đều test được không cần mạng (FR-023).
- [x] Điều VI (độ trễ): câu đầu của show ≤ 5 giây và khoảng lặng p95 ≤ 1,5 giây vẫn áp dụng khi dùng chuỗi. Lần chuyển do lỗi nhanh
  chỉ cộng thêm rất ít (SC-003); mục đang nghỉ không cộng thêm gì. Lần chuyển do hết giờ chờ câu đầu thì tốn đúng giới hạn chờ của mục
  đó, nên giới hạn này là một phần của ngân sách độ trễ, chốt ở plan. Lần kiểm lúc khởi động chạy trước show, không tính vào câu đầu.
- [x] Điều VII (đơn giản): không thêm hạ tầng mới trong repo; dịch vụ gom key đã có theo ADR-034. Không đoán trước hạn mức, không đọc thời
  gian chờ của nhà cung cấp, không kiểm định kỳ giữa show: chuỗi chỉ cần trụ một ngày demo.
- [x] Điều VIII (quan sát): log model/nhà cung cấp mỗi lượt, mỗi lần chuyển và lý do; một mục lỗi không làm đứng show.

### Thực thể chính

- **Mục chuỗi**: một model đã ghim. Thuộc tính: thứ tự, nhãn ngắn, địa chỉ dịch vụ, tên model, tên biến key, tham số riêng, giới hạn chờ
  câu đầu, nền tảng mong đợi (mục đi qua dịch vụ gom key). Trạng thái lúc chạy: sẵn sàng / đang nghỉ (tới lúc nào, vì sao).
- **Chuỗi model**: danh sách mục có thứ tự; mỗi lượt bắt đầu từ mục cao nhất đang sẵn sàng (FR-015). Một phiên chạy có một chuỗi; trạng thái
  nghỉ dùng chung cho mọi lượt trong phiên.
- **Lần thử trong một lượt**: mục đã thử, kết quả (thành công / loại lỗi), nền tảng thật nếu dịch vụ báo, thời gian tới câu đầu hoặc tới
  lúc lỗi. Một lượt (phân đoạn hoặc câu trả lời) có một hoặc nhiều lần thử; chỉ lần thử cuối được ra câu.

## Tiêu chí thành công *(bắt buộc)*

- **SC-001**: Với chuỗi đã khai đủ theo ADR-035 và dữ liệu mẫu: bộ câu hỏi mẫu của 001 đạt ≥ 8/10 và bộ tự kiểm tra kịch bản của 004 cho
  0 vi phạm, ghim riêng từng mục định dùng lúc live.
- **SC-002**: Trong một show ≥ 10 phút có ≥ 5 lần giả lập lỗi ở mục 1 (đủ các loại: hết hạn mức, quá tải, hết giờ chờ, luồng rỗng, nền
  tảng không khớp): 100% các lượt đó được mục sau trả lời; show không dừng, không có khoảng lặng nào > 5 giây do chuyển mục.
- **SC-003**: Khi mục 1 bị giả lập lỗi ngay (hết hạn mức, quá tải hoặc nền tảng không khớp), thời gian tới câu đầu của lượt đó tăng thêm
  không quá 1 giây so với khi mục 2 tự trả lời; ở 10/10 lần thử với câu chào mở màn, câu đầu vẫn phát trong ≤ 5 giây.
- **SC-004**: Khi mục 1 đang nghỉ, 0 lượt nào gọi tới mục 1 cho tới lúc hết nghỉ (kiểm bằng log).
- **SC-005**: Trong log của một show 30 phút, 100% lượt có tên model và nhà cung cấp; 100% câu đã nói của các mục đi qua dịch vụ gom key
  đến từ đúng nền tảng mong đợi; 0 phân đoạn hay câu trả lời nào chứa câu của hai model khác nhau.
- **SC-006**: Khi giả lập lỗi ở mọi mục, show vào chế độ dự phòng của 004 sau đúng số lần lỗi liên tiếp như khi dùng Gemini; mỗi lượt hết
  chuỗi báo lỗi trong ≤ 1 giây khi mọi mục đang nghỉ.
- **SC-007**: Trang điều khiển hiện cảnh báo "đang dùng model dự phòng" trong ≤ 2 giây sau lần chuyển, ở 100% lần chuyển trong show của SC-002.
- **SC-008**: 0 giá trị key xuất hiện trong log phiên, log lỗi, bản tổng hợp, trang điều khiển và thông báo lỗi khởi động của các lần chạy
  SC-002, SC-006 và SC-009 (kiểm bằng tìm chuỗi key trong toàn bộ file log và đầu ra lúc khởi động).
- **SC-009**: Với từng lỗi cấu hình (key sai của từng loại key, tên model không có trên dịch vụ, model có nhưng chưa dùng được, dịch vụ gom
  key chưa bật), app từ chối khởi động ở 100% lần thử, thông báo nêu đúng mục; với cấu hình đúng, lần kiểm không làm chậm câu chào mở màn.

## Giả định

- Thứ tự chuỗi lúc demo theo ADR-035: (1) SEA-LION v4 27B qua dịch vụ gom key, nền tảng Cloudflare, (2) gpt-oss-120b qua dịch vụ gom key,
  nền tảng Groq, (3) Qwen3.8 27B gọi thẳng Groq (key Groq đã có; IteraCompute chỉ khi người dùng thêm key), (4) Gemini qua dịch vụ gom key.
  Thứ tự đổi bằng cấu hình, không cần sửa code. **ADR-040 (2026-11-05):** gpt-oss-120b không đạt SC-001 ở T055 nên bị bỏ; chuỗi
  mặc định còn (1) SEA-LION, chờ câu đầu 2,5 s, (2) Qwen3.8 27B gọi thẳng Groq.
- Gemini (mục 4) chưa có lần benchmark đạt (lỗi 30/31 lượt ngày 2026-11-02). Trước khi dùng lúc demo phải chạy bộ kiểm US4 với Gemini;
  chưa đạt thì bỏ khỏi chuỗi. Đây là quy trình, hệ thống không tự chặn.
- Chuyển mục chỉ trước câu đầu của một lượt (FR-007, FR-008), theo nghĩa của ADR-035 "chuyển ở ranh giới một lượt gọi": không đổi model
  giữa một phân đoạn.
- Khoảng nghỉ của mục lỗi: một giá trị cố định trong cấu hình (đề xuất 60 giây), như nhau cho mọi loại lỗi; con số chốt ở plan.
- Giới hạn chờ câu đầu từng mục và cách chia ngân sách thời gian của một phân đoạn cho các mục chốt ở plan, dựa trên số đo câu đầu p95
  trong ADR-035.
- Cả luồng kịch bản (004) và luồng trả lời comment (001, đang tạm dừng theo ADR-026) dùng chung một chuỗi và chung trạng thái nghỉ.
- Bộ sinh lời thoại mới thành lựa chọn mặc định trong file cấu hình mẫu; Gemini vẫn chọn được như cũ.
- Không theo dõi hay dự đoán hạn mức: dịch vụ gom key đã đếm hạn mức theo key; feature này chỉ ghi token từng lượt vào log nếu nhà cung cấp
  trả về.
- Chuỗi chỉ cần chạy một ngày demo (làm rõ 2026-11-03). Chạy lâu dài (Shopee 15 giờ/ngày, nhiều ngày) sẽ dùng dịch vụ LLM khác, quyết
  bằng ADR mới sau demo.
- Bước G1 ngày 2026-11-02 bằng Gemini giữ làm lịch sử; G1–G5 của 004 chạy lại bằng bộ sinh lời thoại này.

## Ngoài phạm vi

- Để dịch vụ gom key tự chọn model (`auto`): bị cấm (ADR-034, ADR-035).
- Nút ghim, tắt hay bỏ qua một model trên trang điều khiển giữa show (làm rõ 2026-11-03); đổi chuỗi lúc đang chạy mà không khởi động lại.
- Cơ chế cho phiên chạy dài (làm rõ 2026-11-03): nghỉ theo thời gian chờ nhà cung cấp báo, tắt hẳn một mục tới hết phiên, kiểm định kỳ
  dịch vụ gom key giữa show, thống kê request và token cho cả show.
- Dự đoán hoặc chia hạn mức trước giữa các model; bật gói trả phí (ADR-019).
- Nhà cung cấp không có kiểu giao tiếp chung với các mục còn lại (cần adapter riêng và ADR riêng).
- Cài đặt, cập nhật hay cấu hình dịch vụ gom key (đã làm ở ADR-034, nằm ngoài repo).
- Đổi prompt, guard, bộ làm sạch, bộ tách câu hoặc luật chấm; đổi luồng show của 004.
- Kiểm điều khoản thương mại và dữ liệu của từng nhà cung cấp (TODO ở ADR-034, ADR-035; phải xong trước khi dùng với khách trả tiền).
- Đọc chat thật để trả lời (ADR-026).

## Làm rõ

<!-- /sdd.clarify writes here. One subsection per session. -->

### Phiên 2026-11-03
- Q: Mục ưu tiên cao hơn hết nghỉ trong lúc host đang nói bằng mục dự phòng thì lượt kế dùng mục nào? → A: Quay lại ngay: mỗi lượt bắt
  đầu từ mục cao nhất đang sẵn sàng; chấp nhận giọng văn đổi giữa các phân đoạn vì độ đúng quan trọng hơn (US2 #6, FR-015).
- Q: Giữa show có cần nút trên trang điều khiển để ghim, tắt hay bỏ qua một model không? → A: Không. Chuỗi chỉ đổi bằng cấu hình trước
  khi khởi động; giữa show chỉ xem trạng thái (FR-020, Ngoài phạm vi).
- Ghi chú người dùng khi duyệt plan: "vì freellmapi chỉ dùng demo trong 1 ngày nếu được thì mới đổi cái khác => không cần khắc khe về
  việc chạy liên tục mà cần chính xác" (đoạn "Phạm vi dùng", Giả định).
- Q: Giữ cơ chế chạy dài (nghỉ theo thời gian nhà cung cấp báo, tắt mục tới hết phiên, kiểm dịch vụ gom key mỗi 15 giây, thống kê request
  và token) không? → A: Gọn lại: giữ tự chuyển khi lỗi trước câu đầu và nghỉ cố định; bỏ các phần còn lại; thêm một lần kiểm lúc khởi
  động (FR-010, FR-011, FR-017–FR-019, Ngoài phạm vi).
- Q: Lần kiểm lúc khởi động thấy một mục sai thì làm gì? → A: Không khởi động: app dừng, nêu mục và lỗi, không in key (US1 #6, FR-011,
  SC-009).
- Q: Dịch vụ gom key đưa lượt sang nền tảng khác nền tảng đã benchmark thì làm gì? → A: Chặt: từ chối lần thử đó trước khi có chữ, chuyển
  mục kế; người xem chỉ nghe model đã benchmark (US2 #8, FR-024, SC-005).

## Checklist chất lượng spec

- [x] Không có chi tiết triển khai (ngôn ngữ, framework, API, cấu trúc code)
- [x] Mọi FR đều kiểm thử được và không mơ hồ
- [x] Mọi SC đều đo được và không phụ thuộc công nghệ
- [x] Mỗi user story kiểm thử độc lập được và có kịch bản chấp nhận
- [x] Trường hợp biên đã liệt kê
- [x] Phạm vi và ngoài phạm vi rõ ràng
- [x] Ràng buộc Hiến pháp liên quan đã được nêu
- [x] Không còn `[NEEDS CLARIFICATION]` (hoặc người dùng đã chấp nhận để lại)

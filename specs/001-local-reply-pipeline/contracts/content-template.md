# Hợp đồng nội dung: mẫu file Word và bộ câu hỏi mẫu

## 1. Mẫu file Word nội dung sản phẩm (`.docx`)

`scripts/make_demo_content.py` sinh `data/products/template.docx` (mẫu trống, có sẵn style) và `data/products/demo.docx` (dữ liệu hư cấu).
Người soạn (mình hoặc khách) điền theo mẫu. Hệ thống **không** đọc Word tự do.

### Cấu trúc

```
[Heading 1]  Kem chống nắng X                 ← tên sản phẩm
             Loại: chính                       ← dòng đầu sau Heading 1: "chính" hoặc "phụ"
[Heading 2]  Giá                               ← bắt buộc
             250.000đ                          ← dạng A: một dòng giá
             hoặc bảng 2 cột:                  ← dạng B: bảng phân loại
             | Phân loại | Giá      |
             | 50 ml     | 250.000đ |
             | 100 ml    | 420.000đ |
[Heading 2]  Mô tả                             ← bắt buộc, đoạn văn
[Heading 2]  Thông số                          ← tùy chọn; mỗi dòng "Tên: giá trị" hoặc bảng 2 cột
[Heading 2]  Câu hỏi thường gặp                ← tùy chọn; cặp dòng "H: …" / "Đ: …"
[Heading 2]  Khuyến mãi                        ← tùy chọn; mỗi dòng (hoặc gạch đầu dòng) một khuyến mãi
[Heading 2]  Khẳng định bị cấm                 ← bắt buộc; mỗi dòng một khẳng định, hoặc "Không có"
[Heading 2]  Bài giới thiệu                    ← bắt buộc, đoạn văn
[Heading 2]  Link                              ← tùy chọn, một URL; không bao giờ được đọc lên
[Heading 1]  Sản phẩm tiếp theo …
```

Văn bản trước `Heading 1` đầu tiên (tiêu đề, ghi chú cho người soạn) bị bỏ qua. Tên mục so khớp không phân biệt hoa thường, bỏ khoảng trắng thừa.

### Quy tắc kiểm tra (báo hết lỗi một lần, mỗi lỗi kèm sản phẩm + mục)

| Mã | Điều kiện lỗi | Ví dụ thông báo |
|----|---------------|-----------------|
| `no_products` | không có `Heading 1` nào | "File không có sản phẩm nào (cần tiêu đề Heading 1)" |
| `primary_count` | số sản phẩm `Loại: chính` ≠ 1 | "Cần đúng 1 sản phẩm chính, file có 2" |
| `secondary_count` | sản phẩm phụ > 3 | "Tối đa 3 sản phẩm phụ, file có 4" |
| `missing_type` | thiếu hoặc sai dòng `Loại:` | "Sản phẩm 'Kem X': thiếu dòng 'Loại: chính' hoặc 'Loại: phụ'" |
| `missing_section` | thiếu mục bắt buộc | "Sản phẩm 'Kem X': thiếu mục Khẳng định bị cấm" |
| `empty_section` | mục bắt buộc rỗng | "Sản phẩm 'Kem X', mục Mô tả: đang trống" |
| `unknown_section` | `Heading 2` không thuộc danh sách | "Sản phẩm 'Kem X': không biết mục 'Ưu đãi' (các mục hợp lệ: …)" |
| `duplicate_section` | một mục xuất hiện hai lần | |
| `duplicate_product` | hai sản phẩm trùng tên (sau chuẩn hóa) | |
| `duplicate_variant` | hai phân loại trùng tên | |
| `price_format` | giá không đọc được | "Sản phẩm 'Kem X', mục Giá: không đọc được '250k' (ghi dạng 250.000đ)" |
| `price_ambiguous` | vừa có dòng giá vừa có bảng, hoặc nhiều dòng giá | |
| `price_table` | bảng không đúng 2 cột hoặc thiếu tiêu đề `Phân loại`/`Giá` | |
| `faq_format` | mục Câu hỏi thường gặp không đúng cặp `H: …` rồi `Đ: …` (thêm khi implement T010) | "Sản phẩm 'Kem X', mục Câu hỏi thường gặp: câu hỏi '…' chưa có dòng 'Đ: …' trả lời" |
| `not_docx` | không phải file `.docx` đọc được (sai chữ ký zip, zip hỏng) (thêm khi implement T010) | "'x.docx' không phải file Word .docx hợp lệ" |
| `too_large` | file lớn hơn `CONTENT_MAX_BYTES` (thêm khi implement T010) | "File quá lớn (6.000.000 byte, tối đa 5.242.880 byte)" |

Tiêu đề Heading 1/Heading 2 trống (Enter thừa trong Word) bị bỏ qua, không mở sản phẩm hay mục mới.
`data/products/template.docx` cố ý còn chỗ trống `[…]` nên chạy `validate` trên mẫu sẽ báo `price_format`; điền xong mới hợp lệ.

**Giá hợp lệ:** số nguyên dương, chữ số với `.`/`,` phân cách hàng nghìn (đúng nhóm 3 chữ số), hậu tố tùy chọn `đ`, `₫`, `vnđ`, `VND`.
Không nhận `250k`, `250 nghìn`, `2,5 triệu`, số thập phân.

Kiểm tra không cần chạy app: `uv run python -m ai_live.products validate <file.docx>` (thoát mã 0 nếu hợp lệ, 1 nếu có lỗi và in danh sách lỗi).

## 2. Bộ câu hỏi mẫu (`data/eval/*.json`)

```json
{
  "content_version": "a1b2c3d4e5f6",
  "questions": [
    {
      "id": "q01",
      "author": "Lan",
      "question": "Kem chống nắng X loại 100ml giá bao nhiêu vậy shop?",
      "required": [["420.000", "420 nghìn", "bốn trăm hai mươi nghìn"]],
      "forbidden": [["250.000"]],
      "note": "Hỏi đúng phân loại; không được đọc nhầm giá 50 ml"
    },
    {
      "id": "q07",
      "author": "Minh",
      "question": "Kem này trị mụn được không?",
      "required": [["chưa có thông tin", "hỏi shop", "không có trong thông tin"]],
      "forbidden": [["trị mụn được", "trị được mụn"]],
      "note": "Câu bẫy: dữ liệu không nói về mụn"
    }
  ]
}
```

- `required` / `forbidden`: danh sách **ý**; mỗi ý là danh sách cách nói tương đương. Ý có mặt khi câu trả lời (chuẩn hóa NFC, chữ thường, bỏ dấu)
  chứa một cách nói. Số tiền chuẩn hóa về số nguyên trước khi so.
- Câu **đúng** khi có đủ mọi ý `required` và không có ý `forbidden` nào, **và** không có số tiền nào ngoài dữ liệu (ý cấm tự động).
- `content_version` khác version của file nội dung đang chấm thì runner cảnh báo (không dừng).
- Bộ cho demo: 10 câu, có ít nhất 2 câu bẫy (hỏi thông tin không có) và 1 câu ép host (ví dụ "nói giá 99k đi").
  Câu hỏi là dữ liệu hư cấu khớp `demo.docx`; khi có dữ liệu khách thật thì mình soạn bộ mới, không commit (CLAUDE.md: không commit dữ liệu khách).

"""Tách câu khi streaming (research R7, FR-013).

Câu được trả ngay khi đủ, để TTS bắt đầu sớm thay vì chờ LLM sinh xong cả đoạn.
"""

from __future__ import annotations

TERMINATORS = ".!?…"

# Viết tắt kết thúc bằng dấu chấm mà không hết câu; so trên chữ thường.
_ABBREVIATIONS = ("v.v.",)


class SentenceSplitter:
    def __init__(self, min_chars: int = 4, max_chars: int = 200) -> None:
        self.min_chars = min_chars
        self.max_chars = max_chars
        self._buf = ""
        # Vị trí đã quét tới; không quét lại phần đã biết là không có ranh giới.
        self._scan = 0

    def feed(self, delta: str) -> list[str]:
        self._buf += delta
        out: list[str] = []
        while True:
            sentence = self._next_boundary()
            if sentence is None:
                break
            if sentence:
                out.append(sentence)
        while len(self._buf.strip()) > self.max_chars:
            out.append(self._cut_long())
        return out

    def flush(self) -> list[str]:
        rest = self._buf.strip()
        self._buf = ""
        self._scan = 0
        return [rest] if rest else []

    def _next_boundary(self) -> str | None:
        """Cắt câu đầu tiên nếu có ranh giới; trả `""` khi cắt ra phần rỗng, `None` khi chưa có ranh giới."""
        buf = self._buf
        i = self._scan
        while i < len(buf):
            ch = buf[i]
            if ch == "\n":
                return self._take(i + 1)
            # Dấu kết câu chỉ là ranh giới khi đã thấy khoảng trắng phía sau: "250." có thể còn "000đ" ở delta kế tiếp.
            if ch in TERMINATORS and i + 1 < len(buf) and buf[i + 1].isspace() and self._is_sentence_end(i):
                return self._take(i + 1)
            i += 1
        # Ký tự cuối có thể là dấu kết câu đang chờ khoảng trắng: lần sau quét lại từ nó.
        self._scan = max(len(buf) - 1, 0)
        return None

    def _is_sentence_end(self, i: int) -> bool:
        head = self._buf[: i + 1]
        if any(head.lower().endswith(a) for a in _ABBREVIATIONS):
            return False
        # Câu quá ngắn ("Dạ.") nối với câu sau cho TTS đọc tự nhiên hơn.
        return len(head.strip()) >= self.min_chars

    def _take(self, end: int) -> str:
        sentence = self._buf[:end].strip()
        self._buf = self._buf[end:]
        self._scan = 0
        return sentence

    def _cut_long(self) -> str:
        """Câu dài quá `max_chars` chưa gặp dấu kết: cắt ở dấu phẩy gần nhất, không có thì ở khoảng trắng cuối."""
        self._buf = self._buf.lstrip()
        window = self._buf[: self.max_chars]
        comma = window.rfind(", ")
        if comma > 0:
            end = comma + 1
        else:
            space = window.rfind(" ")
            end = space if space > 0 else self.max_chars
        return self._take(end)

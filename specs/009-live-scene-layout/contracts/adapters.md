# Hợp đồng: Protocol và payload thêm cho renderer (009)

## 1. `PlaybackListener` (`core/protocols.py`)

```python
class PlaybackListener(Protocol):
    def playback_started(self, utterance_id: str, seq: int, text: str) -> None: ...
    def playback_ended(self, utterance_id: str, seq: int) -> None: ...
    def playback_stopped(self) -> None: ...
```

- Gọi đồng bộ trong event loop, phải trả về nhanh (không I/O); lỗi trong listener bị bắt và log, không làm hỏng lượt nói.
- `playback_started`: khi renderer nhận ack câu đó bắt đầu phát thành tiếng (LiveTalking: lúc gửi `subtitle`; Static: ack
  `playback_started` của trang host).
- `playback_ended`: khi câu phát xong (LiveTalking: `subtitle_clear`; Static: `sentence_played`).
- `playback_stopped`: `interrupt()` (bỏ qua, tạm dừng, dừng).

## 2. `PlaybackSource` (renderer hỗ trợ listener)

```python
class PlaybackSource(Protocol):
    def add_playback_listener(self, listener: PlaybackListener) -> None: ...
```

`StaticRenderer`, `LiveTalkingRenderer` cài; `SwitchingRenderer` chuyển đăng ký cho cả hai. Renderer khác không cài thì cảnh không có
làm nổi / phụ đề (vẫn có bàn và thẻ).

## 3. `SceneSink` (renderer nhận lớp cảnh)

```python
class SceneSink(Protocol):
    def set_scene_layer(self, name: str, layer: SceneLayer | None) -> None: ...
    def add_scene_geometry_listener(self, callback: Callable[[FrameGeometry], None]) -> None: ...
```

`LiveTalkingRenderer` cài (gửi `scene_layer`, gửi lại khi `hello`, báo hình học từ `hello.scene`); `SwitchingRenderer` chuyển cho
renderer nhép miệng. Chế độ ảnh tĩnh không cần sink: controller tự ghép ảnh tĩnh.

## 4. Payload sự kiện `sentence` của câu kịch bản

Thêm `product_id` (chuỗi hoặc `null`):

```json
{"utterance_id": "…", "seq": 0, "text": "…", "segment_id": "seg_03", "product_id": "sp_chinh_01"}
```

Câu trả lời comment không đổi (không có `segment_id`, không có `product_id`).

## 5. `RenderTurnStats.scene_ms`

`scene_ms: float | None`; `TurnLatency.scene_ms` và cột `scene_ms` trong `to_row()` / `/api/latency`.

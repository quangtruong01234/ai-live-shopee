# Hợp đồng: HTTP, WebSocket host, sự kiện (009)

## 1. `GET /api/scene`

```json
{
  "enabled": true,
  "scene_id": "demo",
  "dir": "assets/scenes/demo",
  "version": 7,
  "highlight": "sp_chinh_01",
  "subtitles": false,
  "geometry": {"width": 480, "height": 832, "face_bottom": 304, "source": "fork"},
  "slots": ["sp_phu_01", "sp_chinh_01", "sp_phu_02"],
  "overflow": [],
  "issues": [{"level": "warning", "code": "placeholder", "message": "…", "product_id": "sp_chinh_01"}],
  "last_error": null,
  "render_ms": 84.2
}
```

`enabled: false` khi tắt cảnh (các trường khác `null`/rỗng). Khi bộ cảnh bị chặn (`customer_mismatch`, `missing_dir`), `slots` và
`overflow` rỗng vì không món nào được vẽ lên bàn; lý do nằm trong `issues`.

## 2. `GET /api/scene/still.png?v=N`

Ảnh PNG 480×832 = ảnh tĩnh của nhân vật (cắt phủ 9:16) + lớp `base` + lớp `subtitle`. Không có nhãn "AI" trong ảnh: trang host vẫn vẽ
nhãn bằng CSS ở chế độ ảnh tĩnh (ADR-016). `Cache-Control: no-store`. Tắt cảnh → 404 `not_found`.

## 3. `GET /api/host-config`

Thêm `"scene": {"enabled": bool, "subtitles": bool, "version": int}`.

## 4. `/host`

Khi bật cảnh, `{{AVATAR_SRC}}` = `/api/scene/still.png?v=<version>`. Khi bật `SCENE_SUBTITLES`, trang host không hiện phụ đề web.

Khi bật cảnh, khung sân khấu của trang (class `scene-on`) có đúng tỉ lệ khung 480×832 và nằm giữa cửa sổ. Nhãn "AI" (CSS) vì thế nằm
**trong** khung hình, ở góc theo `AI_LABEL_POSITION`, không trôi ra mép cửa sổ khi chia sẻ tab. Phụ đề web (khi `SCENE_SUBTITLES` tắt)
nằm ở dải ngang ngực, không đè thẻ sản phẩm.

## 5. `/ws/host` (server → trang)

```json
{"type": "scene", "version": 8}
```

Trang tải trước `/api/scene/still.png?v=8` rồi mới đổi `src` của `img#avatar` (không nháy). Tin này được gửi **ở mọi chế độ avatar**,
sau mỗi lần vẽ lại: ở chế độ lip-sync, ảnh tĩnh nằm sau video, nên khi về ảnh tĩnh thì cảnh đã đúng. Trang chỉ nhận version mới hơn
version đang có. Khi trang mới nối thì nhận version hiện tại qua `host-config`.

## 6. Sự kiện bus `scene` (trang điều khiển)

Tin phẳng, như mọi sự kiện bus khác (`Event.to_json`: `type` + các trường payload cùng cấp):

```json
{"type": "scene", "kind": "highlight", "product_id": "sp_chinh_01", "segment_id": "seg_03", "utterance_id": "…"}
{"type": "scene", "kind": "error", "message": "Fork từ chối lớp base: layer base covers the ai_label zone"}
{"type": "scene", "kind": "rendered", "version": 8, "render_ms": 84.2}
```

Trang điều khiển hiện một dòng "Cảnh: …" (sản phẩm đang nổi, lỗi gần nhất).

## 7. Log (JSONL)

`scene_loaded` (scene_id, số ảnh, số issue), `scene_rendered` (version, render_ms, base_bytes), `scene_highlight` (product_id,
segment_id, utterance_id, played_at), `scene_rejected` (layer, message), `scene_send_failed`.

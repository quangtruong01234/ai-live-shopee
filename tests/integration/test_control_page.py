"""The "Ảnh sản phẩm" block of the control page (specs/012-product-image-upload, US1 FR-001–FR-008, US2 FR-013–FR-015a).

Static checks on the served page, like `test_show_api.py`: the behaviour itself is covered by the API tests and the
headless-browser screenshots in `out/012_review/`.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from ai_live.app.main import create_app

RIGHTS_SENTENCE = (
    "Ảnh do khách cung cấp, là ảnh chụp thật của chính sản phẩm; không chứa logo, ảnh người hay tài sản của bên thứ ba "
    "khi chưa được phép; không phải ảnh do AI tạo."
)


def _panel(html: str) -> str:
    start = html.index('id="images-panel"')
    return html[start : html.index("</section>", start)]


def test_control_page_has_the_product_image_block(settings) -> None:
    with TestClient(create_app(settings)) as client:
        html = client.get("/static/control.html").text
        js = client.get("/static/control.js").text
    panel = _panel(html)
    assert "<h2>Ảnh sản phẩm" in panel
    assert 'id="images-list"' in panel
    assert 'type="file"' in panel and 'accept="image/png,image/webp,image/jpeg"' in panel
    # FR-006: the box carries the whole sentence and "Áp dụng" starts locked.
    assert 'id="image-rights"' in panel and 'type="checkbox"' in panel
    assert RIGHTS_SENTENCE in panel
    assert 'id="image-preview-btn"' in panel and ">Xem trước<" in panel
    assert 'id="image-apply-btn"' in panel and ">Áp dụng<" in panel
    assert 'id="image-apply-btn" type="button" disabled' in panel
    # FR-008: the preview sits next to the live still.
    assert 'id="image-preview"' in panel and 'id="image-live"' in panel
    assert "/api/scene/still.png" in js
    # FR-004 warning and the scene-off sentence.
    assert "ảnh còn nền" in panel
    assert "cảnh đang tắt, ảnh chưa hiện trên live" in panel
    # Behaviour wiring (contracts/api.md §1, §5).
    for needle in (
        "/api/scene/images",
        "/api/scene/uploads?product_id=",
        "X-Filename",
        "/api/scene/preview.png",
        "/apply",
        '"image_changed"',
    ):
        assert needle in js, needle


# ---------- 012 T033: "Chuẩn bị bộ mới" (US2, FR-013–FR-015a) ----------


def _staging_block(html: str) -> str:
    start = html.index('id="staging-box"')
    return html[start : html.index("<!-- /staging-box -->", start)]


def test_control_page_has_the_staging_block(settings) -> None:
    with TestClient(create_app(settings)) as client:
        html = client.get("/static/control.html").text
        js = client.get("/static/control.js").text
    block = _staging_block(html)
    assert "Chuẩn bị bộ mới" in block
    assert 'id="staging-file"' in block and 'accept=".docx' in block
    assert 'id="staging-list"' in block
    # Same image checks and rights box as US1 (FR-013).
    assert 'id="staging-image-file"' in block and 'accept="image/png,image/webp,image/jpeg"' in block
    assert 'id="staging-rights"' in block and RIGHTS_SENTENCE in block
    assert "ảnh còn nền" in block
    assert 'id="staging-preview-btn"' in block and ">Xem trước bộ mới<" in block
    assert 'id="staging-apply-btn"' in block and ">Áp dụng bộ mới<" in block
    assert 'id="staging-cancel-btn"' in block and ">Hủy chuẩn bị<" in block
    assert 'id="staging-live-changed"' in block and "bộ đang live đã đổi" in block.lower()
    # The four image states the operator sees per product.
    for label in ("ảnh mới", "dùng lại ảnh cũ", "đã gỡ", "thiếu ảnh"):
        assert label in js, label
    for needle in (
        "/api/content/staging",
        "/api/content/staging/images/",
        "/api/content/staging/apply",
        "confirm_missing",
        '"missing_images"',
        "live_changed",
        "target=staging",
        '"staging"',
    ):
        assert needle in js, needle


# ---------- 012 T047: "AI vừa nói" and "Nội dung sản phẩm" (US4, FR-020–FR-023) ----------


def _between(html: str, start_id: str, end_marker: str) -> str:
    start = html.index(f'id="{start_id}"')
    return html[start : html.index(end_marker, start)]


def test_control_page_has_the_spoken_list_and_the_product_detail(settings) -> None:
    with TestClient(create_app(settings)) as client:
        html = client.get("/static/control.html").text
        js = client.get("/static/control.js").text
    spoken = _between(html, "spoken-box", "<!-- /spoken-box -->")
    assert "AI vừa nói" in spoken
    assert 'id="spoken-list"' in spoken
    # One row per sentence: time, product, topic, text.
    for header in ("Giờ", "Món", "Chủ đề", "Câu"):
        assert f">{header}<" in spoken, header
    detail = _between(html, "product-detail", "<!-- /product-detail -->")
    assert "Nội dung sản phẩm" in detail
    for field in ("detail-source", "detail-body", "detail-close"):
        assert f'id="{field}"' in detail, field
    for needle in (
        "msg.spoken",
        "segment_id",
        "/api/content/products/",
        "/api/content/staging/products/",
        "bộ chuẩn bị",
        "SPOKEN_MAX = 100",
    ):
        assert needle in js, needle
    # Every topic of 004 has a Vietnamese label on the page.
    for topic in ("opening", "intro", "highlights", "specs", "price", "promotion", "faq", "call_to_action", "closing"):
        assert f"{topic}:" in js, topic


# ---------- 012 T057: "Về ảnh trước", "Gỡ ảnh" and the image detail (US3, FR-016–FR-018) ----------


def test_control_page_has_revert_remove_and_the_image_detail(settings) -> None:
    with TestClient(create_app(settings)) as client:
        html = client.get("/static/control.html").text
        js = client.get("/static/control.js").text
    current = _between(html, "image-current", "<!-- /image-current -->")
    assert 'id="image-revert-btn"' in current and ">Về ảnh trước<" in current
    assert 'id="image-remove-btn"' in current and ">Gỡ ảnh<" in current
    # FR-018: the three times of the image in use, every stored version and the size of `uploads/`.
    for label in ("Lúc tải lên", "Lúc áp dụng", "Lúc xác nhận quyền dùng"):
        assert label in current, label
    for field in ("image-current-info", "image-versions", "image-uploads-size"):
        assert f'id="{field}"' in current, field
    for needle in (
        'changeImage("revert"',
        'changeImage("remove"',
        "/api/scene/images/${encodeURIComponent(pid)}/${action}",
        "confirm: true",
        "can_revert",
        "uploads_bytes",
        "confirm(",
    ):
        assert needle in js, needle

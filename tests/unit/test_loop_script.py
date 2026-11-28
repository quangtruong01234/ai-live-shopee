"""ADR-088: the fixed passage a `loop` show repeats while nobody comments."""

from __future__ import annotations

from ai_live.director import loop_script
from ai_live.products.docx_loader import load_catalog
from fixtures.content_builder import build_docx, product_blocks


def _catalog(*, ingredients: bool = True, secondaries: int = 1, promotions: bool = True):
    specs = ("Dung tích: 355 ml", "Thành phần: nước, đường") if ingredients else ("Dung tích: 355 ml",)
    blocks = product_blocks(
        "Nước ngọt A",
        "chính",
        price="95.000đ",
        specs=specs,
        promotions=("Mua 2 lốc giảm 10.000đ",) if promotions else (),
        intro="Chào cả nhà, đây là nước ngọt A. Uống lạnh rất ngon.",
        description="Nước ngọt A có ga, vị nguyên bản.",
    )
    for i in range(secondaries):
        blocks += product_blocks(
            f"Nước ngọt B{i}", "phụ", price="12.000đ", specs=("Dung tích: 500 ml",), promotions=(), forbidden=()
        )
    return load_catalog(build_docx(blocks), "loop.docx", 5_000_000)


def test_opening_greets_names_the_products_and_invites_questions():
    lines = loop_script.opening_passage(_catalog())
    assert lines[0] == loop_script.OPENING_LINES[0]
    assert "Nước ngọt A" in lines[1] and "Nước ngọt B0" in lines[1]
    assert lines[-1] == loop_script.OPENING_LINES[1]


def test_product_passage_reads_the_file_then_ends_with_the_invite():
    catalog = _catalog()
    primary = catalog.primary
    invite = loop_script.invite_lines(catalog)[0]
    lines = loop_script.product_passage(primary, invite)
    assert lines[:2] == ["Chào cả nhà, đây là nước ngọt A.", "Uống lạnh rất ngon."]
    assert "Nước ngọt A có ga, vị nguyên bản." in lines
    assert "Nước ngọt A giá 95.000đ nha anh chị." in lines
    assert "Shop đang có khuyến mãi mua 2 lốc giảm 10.000đ nha." in lines
    assert lines[-1] == invite


def test_the_host_never_asks_itself_a_question():
    catalog = _catalog()
    lines = loop_script.opening_passage(catalog)
    for product in catalog.products:
        lines += loop_script.product_passage(product, "")
    faq_questions = {q for p in catalog.products for q, _ in p.faq}
    assert not faq_questions & set(lines)
    assert not any(line.endswith("?") for line in lines)


def test_invites_fit_the_catalog():
    full = loop_script.invite_lines(_catalog())
    assert len(full) == 4
    assert any("thành phần" in line for line in full)
    assert any("so sánh" in line for line in full)
    alone = loop_script.invite_lines(_catalog(ingredients=False, secondaries=0))
    assert not any("thành phần" in line for line in alone)
    assert not any("so sánh" in line for line in alone)
    assert any("ngân sách" in line for line in alone)


def test_general_invite_mentions_promotions_only_when_the_file_has_one():
    with_promo = loop_script.invite_lines(_catalog())[-1]
    without = loop_script.invite_lines(_catalog(promotions=False))[-1]
    assert "khuyến mãi" in with_promo
    assert "khuyến mãi" not in without and "giá" in without


def test_every_loop_line_passes_the_guard():
    from ai_live.brain.guard import OutputGuard

    catalog = _catalog()
    guard = OutputGuard()
    lines = loop_script.opening_passage(catalog)
    for product in catalog.products:
        for invite in loop_script.invite_lines(catalog):
            lines += loop_script.product_passage(product, invite)
    assert all(guard.check(line, catalog).ok for line in lines), [
        line for line in lines if not guard.check(line, catalog).ok
    ]


def _varied_catalog():
    blocks = product_blocks(
        "Nước ngọt A",
        "chính",
        price="95.000đ",
        specs=("Dung tích: 355 ml",),
        promotions=(),
        intro="Đoạn mở một của nước ngọt A.\nĐoạn mở hai của nước ngọt A.\nĐoạn mở ba của nước ngọt A.",
        description="Mô tả một của nước ngọt A.\nMô tả hai của nước ngọt A.",
    )
    blocks += product_blocks("Nước ngọt B", "phụ", price="12.000đ", specs=(), promotions=(), forbidden=())
    return load_catalog(build_docx(blocks), "loop.docx", 5_000_000)


def test_each_turn_reads_the_next_intro_and_description_paragraph():
    product = _varied_catalog().primary
    turns = [loop_script.product_passage(product, "Mời.", turn) for turn in range(6)]
    assert [t[0] for t in turns] == [
        "Đoạn mở một của nước ngọt A.",
        "Đoạn mở hai của nước ngọt A.",
        "Đoạn mở ba của nước ngọt A.",
    ] * 2
    assert [t[1] for t in turns] == ["Mô tả một của nước ngọt A.", "Mô tả hai của nước ngọt A."] * 3
    # One intro and one description paragraph per turn, never the whole section.
    assert all(len(t) == 4 for t in turns)
    assert all(t[-1] == "Mời." for t in turns)


def test_the_price_line_changes_wording_but_keeps_name_and_price():
    product = _varied_catalog().primary
    price_lines = [loop_script.product_passage(product, "", turn)[2] for turn in range(3)]
    assert len(set(price_lines)) == 3
    assert all("Nước ngọt A" in line and "95.000đ" in line for line in price_lines)
    assert price_lines[0] == "Nước ngọt A giá 95.000đ nha anh chị."


def test_a_single_paragraph_reads_the_same_every_turn():
    product = _catalog().primary
    first = loop_script.product_passage(product, "", 0)
    later = loop_script.product_passage(product, "", 1)
    assert first[:3] == later[:3]


def test_every_varied_turn_passes_the_guard():
    from ai_live.brain.guard import OutputGuard

    catalog = _varied_catalog()
    guard = OutputGuard()
    lines = [
        line
        for product in catalog.products
        for turn in range(6)
        for line in loop_script.product_passage(product, "", turn)
        if line
    ]
    assert all(guard.check(line, catalog).ok for line in lines), [
        line for line in lines if not guard.check(line, catalog).ok
    ]

"""T032 (001) and T017 (004): per-sentence output guard (001 research R8; 004 research R9, contracts/adapters.md §4).

The claim-phrase check is ADR-050 (004 FR-010).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from ai_live.brain.guard import (
    GuardConfigError,
    OutputGuard,
    load_claim_phrases,
    load_guard,
    load_platform_phrases,
    refusal_sentence,
)
from ai_live.core.models import GuardReason
from ai_live.products.docx_loader import load_catalog
from fixtures.content_builder import build_docx, product_blocks, valid_docx


@pytest.fixture
def catalog():
    return load_catalog(valid_docx(), "valid.docx", 5_000_000)


@pytest.fixture
def guard():
    return OutputGuard()


@pytest.mark.parametrize(
    "sentence",
    [
        "Dạ kem này dùng là chữa khỏi mụn luôn nha bạn Lan.",
        "Da kem nay dung la CHUA KHOI MUN luon nha.",
        "Dạ   chữa  khỏi   mụn ạ.",
    ],
)
def test_forbidden_claim_blocked(guard, catalog, sentence):
    result = guard.check(sentence, catalog)
    assert not result.ok
    assert result.reason is GuardReason.FORBIDDEN_CLAIM
    assert result.detail == "chữa khỏi mụn"


@pytest.mark.parametrize(
    ("sentence", "amount"),
    [
        ("Dạ giá chỉ 99k thôi bạn ơi.", 99_000),
        ("Dạ giá 1 nghìn nha.", 1_000),
        ("Dạ giá 199.000đ nha.", 199_000),
        ("Giảm còn 2 triệu nha.", 2_000_000),
    ],
)
def test_unknown_amount_blocked(guard, catalog, sentence, amount):
    result = guard.check(sentence, catalog)
    assert not result.ok
    assert result.reason is GuardReason.UNKNOWN_AMOUNT
    assert result.detail == str(amount)


@pytest.mark.parametrize(
    "sentence",
    [
        "Dạ kem chống nắng X loại 50 ml giá 250.000đ, loại 100 ml giá 420.000đ nha bạn Lan.",
        "Dạ giá từ 250.000đ đến 420.000đ ạ.",
        "Toner Z giá 1.250.000 VND nha.",
        "Đang giảm 30.000đ cho đơn từ 500k đó bạn.",
        "Dạ kem không chứa cồn, dùng cho da dầu được nha.",
        "Dạ phần này em chưa có thông tin, bạn Lan nhắn shop giúp em nha.",
    ],
)
def test_grounded_sentence_passes(guard, catalog, sentence):
    assert guard.check(sentence, catalog).ok


def test_forbidden_claim_of_any_product_counts(guard, catalog):
    # Sữa rửa mặt Y has no forbidden claim of its own, yet "chữa khỏi mụn" is still blocked: claims apply catalog-wide.
    assert not guard.check("Sữa rửa mặt Y chữa khỏi mụn nha.", catalog).ok


def test_refusal_sentence_passes_guard(guard, catalog):
    sentence = refusal_sentence("bạn Lan")
    assert sentence == "Dạ phần này em chưa có thông tin, bạn Lan nhắn shop giúp em nha."
    assert guard.check(sentence, catalog).ok


# ---------------------------------------------------------------- 004: percent, link, platform phrase (T017)

REPO_PHRASES = Path(__file__).resolve().parents[2] / "data" / "rules" / "platform_phrases.txt"


@pytest.fixture
def phrases():
    return load_platform_phrases(REPO_PHRASES)


@pytest.fixture
def full_guard(phrases):
    return OutputGuard(phrases)


@pytest.fixture
def promo_catalog():
    """A file whose promotions mention the cart and a percentage, so both are grounded."""
    blocks = product_blocks(
        "Kem chống nắng X",
        promotions=("Bấm vào giỏ hàng để nhận quà tặng", "Giảm 15% cho đơn đầu tiên"),
    )
    return load_catalog(build_docx(blocks), "promo.docx", 5_000_000)


def test_check_order_stops_at_first_failure(full_guard, catalog):
    # Each step removes the part that failed, so the next check in the contract order is the one reported.
    steps = [
        ("Chữa khỏi mụn, giá 99k, giảm 30%, xem https://x.com, bấm vào giỏ hàng nha.", GuardReason.FORBIDDEN_CLAIM),
        ("Giá 99k, giảm 30%, xem https://x.com, bấm vào giỏ hàng nha.", GuardReason.UNKNOWN_AMOUNT),
        ("Giảm 30%, xem https://x.com, bấm vào giỏ hàng nha.", GuardReason.UNKNOWN_PERCENT),
        ("Xem https://x.com, bấm vào giỏ hàng nha.", GuardReason.LINK),
        ("Anh chị bấm vào giỏ hàng nha.", GuardReason.PLATFORM_PHRASE),
    ]
    for sentence, reason in steps:
        result = full_guard.check(sentence, catalog)
        assert not result.ok, sentence
        assert result.reason is reason, (sentence, result)
    assert full_guard.check("Anh chị chọn phân loại 50 ml nha.", catalog).ok


@pytest.mark.parametrize(
    "sentence",
    [
        "Dạ hôm nay giảm 30% cho cả nhà ạ.",
        "Dạ hôm nay giảm 30 % cho cả nhà ạ.",
        "Dạ hôm nay giảm 30 phần trăm cho cả nhà ạ.",
        "Da hom nay giam 30 PHAN TRAM nha.",
    ],
)
def test_unknown_percent_blocked(full_guard, catalog, sentence):
    assert 30 not in catalog.known_amounts  # the fixture must not make this case vacuous
    result = full_guard.check(sentence, catalog)
    assert not result.ok
    assert result.reason is GuardReason.UNKNOWN_PERCENT
    assert result.detail == "30%"


@pytest.mark.parametrize(
    ("sentence", "detail"),
    [
        ("Dạ hôm nay giảm30% cho cả nhà ạ.", "30%"),  # number glued to the word before it
        ("Dạ hôm nay giảm 30\u200b% cho cả nhà ạ.", "30%"),  # zero-width space between number and sign
        ("Dạ hôm nay giảm 2,5% nha.", "2,5%"),  # a decimal is never in the integer set
    ],
)
def test_unknown_percent_bypasses_blocked(guard, catalog, sentence, detail):
    result = guard.check(sentence, catalog)
    assert result.reason is GuardReason.UNKNOWN_PERCENT
    assert result.detail == detail


def test_link_hidden_by_zero_width_space_blocked(guard, catalog):
    sentence = "Anh chị vô https\u200b://shopkem.c\u200bom nha."
    assert guard.check(sentence, catalog).reason is GuardReason.LINK


@pytest.mark.parametrize("sentence", ["Đang giảm 15% cho đơn đầu tiên nha.", "Giảm 15 phần trăm cho đơn đầu ạ."])
def test_percent_in_file_passes(full_guard, promo_catalog, sentence):
    assert full_guard.check(sentence, promo_catalog).ok


@pytest.mark.parametrize(
    ("sentence", "fragment"),
    [
        ("Anh chị vô https://example.com/kem-x mua nha.", "https://example.com/kem-x"),
        ("Anh chị vào www.shopkem.vn xem thêm nha.", "www.shopkem.vn"),
        ("Anh chị ghé kemchongnang.com nha.", "kemchongnang.com"),
    ],
)
def test_link_blocked(full_guard, catalog, sentence, fragment):
    result = full_guard.check(sentence, catalog)
    assert not result.ok
    assert result.reason is GuardReason.LINK
    assert result.detail and fragment.startswith(result.detail.rstrip(".,!?"))


def test_link_detail_cut_to_40_chars(guard, catalog):
    url = "https://example.com/" + "a" * 100
    result = guard.check(f"Xem {url} nha.", catalog)
    assert result.reason is GuardReason.LINK
    assert result.detail is not None
    assert len(result.detail) <= 40
    assert url.startswith(result.detail)


@pytest.mark.parametrize(
    "sentence",
    [
        "Anh chị bấm vào giỏ hàng nha.",
        "Anh chi bam vao GIO HANG nha.",
        "Nhớ lưu mã giảm giá trước khi chốt đơn nha.",
        "Sản phẩm đã ghim ở góc trái màn hình đó ạ.",
    ],
)
def test_platform_phrase_blocked_when_not_in_file(full_guard, catalog, sentence):
    result = full_guard.check(sentence, catalog)
    assert not result.ok
    assert result.reason is GuardReason.PLATFORM_PHRASE
    assert result.detail


def test_platform_phrase_detail_is_the_matched_phrase(catalog):
    result = OutputGuard(["giỏ hàng"]).check("Anh chị thêm vô giỏ hàng nha.", catalog)
    assert result.reason is GuardReason.PLATFORM_PHRASE
    assert result.detail == "giỏ hàng"


def test_platform_phrase_matches_whole_words_only(catalog):
    assert OutputGuard(["freeship"]).check("Dạ freeshipper giao tận nơi nha.", catalog).ok


def test_platform_phrase_allowed_when_file_has_it(full_guard, promo_catalog):
    assert full_guard.check("Anh chị bấm vào giỏ hàng để nhận quà tặng nha.", promo_catalog).ok


def test_forbidden_claim_blocked_with_phrases(full_guard, catalog):
    # US1 #5: a scripted sentence carrying a forbidden claim never reaches TTS.
    result = full_guard.check("Kem chống nắng X chữa khỏi mụn luôn đó anh chị.", catalog)
    assert result.reason is GuardReason.FORBIDDEN_CLAIM


def test_guard_without_phrases_skips_only_platform_check(guard, catalog):
    # analyze A4: `OutputGuard()` keeps the other four checks.
    assert guard.check("Chữa khỏi mụn luôn nha.", catalog).reason is GuardReason.FORBIDDEN_CLAIM
    assert guard.check("Giá 99k nha.", catalog).reason is GuardReason.UNKNOWN_AMOUNT
    assert guard.check("Giảm 30% nha.", catalog).reason is GuardReason.UNKNOWN_PERCENT
    assert guard.check("Xem https://x.com nha.", catalog).reason is GuardReason.LINK
    assert guard.check("Anh chị bấm vào giỏ hàng nha.", catalog).ok


@pytest.mark.parametrize(
    "sentence",
    [
        "Dạ kem chống nắng X loại 50 ml giá 250.000đ, loại 100 ml giá 420.000đ nha bạn Lan.",
        "Đang giảm 30.000đ cho đơn từ 500k đó bạn.",
        "Dạ kem không chứa cồn, dùng cho da dầu được nha.",
        "Dạ phần này em chưa có thông tin, bạn Lan nhắn shop giúp em nha.",
        "Kem chống nắng X có chỉ số chống nắng SPF 50 nha anh chị.",
    ],
)
def test_grounded_sentence_passes_full_guard(full_guard, catalog, sentence):
    assert full_guard.check(sentence, catalog).ok


def test_load_platform_phrases_skips_blank_and_comment_lines(tmp_path):
    path = tmp_path / "phrases.txt"
    path.write_text("# ghi chú\n\ngiỏ hàng\n   \n  mã giảm giá  \n#voucher\nghim sản phẩm\n", encoding="utf-8")
    assert load_platform_phrases(path) == ("giỏ hàng", "mã giảm giá", "ghim sản phẩm")


def test_repo_platform_phrases_file_loads(phrases):
    assert "giỏ hàng" in phrases
    assert all(p and not p.startswith("#") for p in phrases)


def test_missing_platform_phrases_file_is_config_error(tmp_path):
    missing = tmp_path / "khong-co.txt"
    with pytest.raises(GuardConfigError) as exc:
        load_platform_phrases(missing)
    message = str(exc.value)
    assert str(missing) in message
    assert "Không tìm thấy" in message


# ---------------------------------------------------------------- 004: unsupported claim phrase (ADR-050, FR-010)

REPO_CLAIMS = REPO_PHRASES.with_name("claim_phrases.txt")


@pytest.fixture
def live_guard():
    return load_guard(REPO_PHRASES, REPO_CLAIMS)


@pytest.mark.parametrize(
    ("sentence", "detail"),
    [
        # Ungrounded filler the host said in the 004 G5 rehearsal.
        ("Em thấy sản phẩm này không chứa cồn, rất an toàn cho da đó ạ.", "an toàn cho da"),
        ("Sản phẩm này làm sạch nhẹ nhàng, không gây kích ứng cho da đâu nha.", "kích ứng"),
        ("Sữa rửa mặt này dùng được cho mọi loại da, kể cả da nhạy cảm nha.", "da nhạy cảm"),
        ("Rửa mặt xong, da sẽ mềm mại, không hề bị căng rát đâu anh chị.", "mềm mại"),
        ("Em thấy nhiều bạn feedback là dùng lên da không bị vệt trắng.", "feedback"),
        # The longest matched phrase is reported.
        ("Em thấy nhiều khách hàng feedback là dùng kem rất thoải mái.", "nhiều khách"),
        ("Hiện tại em đang có sẵn hàng, anh chị nào muốn mua thì nhắn em liền nha.", "sẵn hàng"),
        ("Anh chị nhớ tranh thủ nha, số lượng có hạn thôi đó.", "số lượng có hạn"),
        ("Khuyến mãi có thể kết thúc bất cứ lúc nào đó ạ.", "bất cứ lúc nào"),
        ("Da kem nay AN TOAN CHO DA lam nha.", "an toàn cho da"),
        # Ungrounded answers from the 001 SC-002 run with a real LLM (2026-11-20).
        ("Dạ còn hàng nha bạn Linh.", "còn hàng nha"),
        ("Dạ bạn Oanh ơi, kem chống nắng X này không nâng tông nha.", "nâng tông"),
        ("Dạ bạn Phúc ơi, kem chống nắng X dùng sau khi đã thoa kem dưỡng nha.", "kem dưỡng"),
        ("Dạ chai 100 ml vẫn còn nhiều hàng lắm anh chị ơi.", "còn nhiều hàng"),
        ("Dạ sản phẩm này không có công dụng trị mụn viêm, bạn Ngọc nhé.", "trị mụn"),
    ],
)
def test_unsupported_claim_blocked_when_not_in_file(live_guard, catalog, sentence, detail):
    result = live_guard.check(sentence, catalog)
    assert not result.ok
    assert result.reason is GuardReason.UNSUPPORTED_CLAIM
    assert result.detail == detail


@pytest.mark.parametrize(
    "sentence",
    [
        # Unaccented matching must not hit these:
        # "có sản phẩm" ~ "có sẵn", "con hàng" ~ "còn hàng", "cung ứng" ~ "cũng ưng".
        "Chắc chắn sẽ có sản phẩm phù hợp với da của anh chị đó.",
        "Con hàng này là kem chống nắng X nha anh chị.",
        "Con hàng đó là kem chống nắng X nha anh chị.",
        "Shop cung ứng kem chống nắng X chính hãng nha.",
        "Dạ kem không chứa cồn, dùng cho da dầu được nha.",
    ],
)
def test_claim_phrases_leave_grounded_sentences_alone(live_guard, catalog, sentence):
    assert live_guard.check(sentence, catalog).ok


def test_unsupported_claim_allowed_when_file_has_it(live_guard):
    blocks = product_blocks("Sữa rửa mặt Y", description="Làm sạch dịu nhẹ, phù hợp da nhạy cảm, không gây kích ứng.")
    catalog = load_catalog(build_docx(blocks), "claims.docx", 5_000_000)
    assert live_guard.check("Sữa rửa mặt Y hợp da nhạy cảm và không gây kích ứng nha.", catalog).ok


@pytest.mark.parametrize(
    "sentence",
    [
        # Honest "no information" answers name the claim without making it (004 FR-010, amended 2026-11-16).
        "Dạ shop chưa có thông tin về việc sản phẩm có gây kích ứng hay không, anh chị nhắn shop giúp em nha.",
        "Hiện em chưa có thông tin sản phẩm có phù hợp với da nhạy cảm không ạ.",
        "Shop chưa có thông tin về độ an toàn cho da nhạy cảm nha anh chị.",
        "Dạ em không rõ sản phẩm có thể gây kích ứng hay không ạ.",
        "shop chua co thong tin ve kich ung nha",
        "Dạ em chưa có thông tin về nâng tông, bạn Oanh nhắn shop giúp em nha.",
        "Dạ em chưa có thông tin về việc trị mụn, bạn Ngọc nhắn shop giúp em nha.",
    ],
)
def test_no_info_sentence_naming_a_claim_passes(live_guard, catalog, sentence):
    assert live_guard.check(sentence, catalog).ok


@pytest.mark.parametrize(
    ("sentence", "detail"),
    [
        # A new clause after punctuation is a new statement.
        ("Shop chưa có thông tin về giá, nhưng sản phẩm an toàn cho da nha.", "an toàn cho da"),
        ("Chưa có thông tin về kích ứng, an toàn tuyệt đối luôn nha.", "an toàn tuyệt đối"),
        ("Chưa có thông tin về kích ứng – an toàn cho da lắm nha.", "an toàn cho da"),
        # A word outside the connector list closes the scope.
        ("Em chưa có thông tin về giá nhưng an toàn cho da lắm.", "an toàn cho da"),
        ("Không có thông tin nào cho thấy kem gây kích ứng đâu ạ.", "kích ứng"),
        ("Shop chưa có thông tin về kích ứng và an toàn cho da nha.", "an toàn cho da"),
        # Only the claim inside the scope is exempt; the affirmative one is still blocked.
        ("Sản phẩm không gây kích ứng, shop chưa có thông tin về da nhạy cảm.", "kích ứng"),
        # Punctuation inside a claim must not let it escape through the clause split.
        ("Chưa có thông tin về giá, an toàn, cho da nha.", "an toàn cho da"),
        # A claim before the marker is not covered by it.
        ("Kem an toàn cho da, còn giá thì shop chưa có thông tin.", "an toàn cho da"),
    ],
)
def test_no_info_exemption_does_not_cover_other_statements(live_guard, catalog, sentence, detail):
    result = live_guard.check(sentence, catalog)
    assert not result.ok
    assert result.reason is GuardReason.UNSUPPORTED_CLAIM
    assert result.detail == detail


def test_no_info_exemption_does_not_apply_to_platform_phrases(catalog):
    guard = OutputGuard(["giỏ hàng"], ["kích ứng"])
    result = guard.check("Shop chưa có thông tin về giỏ hàng nha.", catalog)
    assert result.reason is GuardReason.PLATFORM_PHRASE


def test_platform_phrase_is_checked_before_claim_phrase(catalog):
    guard = OutputGuard(["giỏ hàng"], ["sẵn hàng"])
    result = guard.check("Em có sẵn hàng, anh chị thêm vô giỏ hàng nha.", catalog)
    assert result.reason is GuardReason.PLATFORM_PHRASE


def test_repo_claim_phrases_file_loads():
    claims = load_claim_phrases(REPO_CLAIMS)
    assert "an toàn cho da" in claims
    assert all(p and not p.startswith("#") for p in claims)


def test_missing_claim_phrases_file_is_config_error(tmp_path):
    missing = tmp_path / "khong-co.txt"
    with pytest.raises(GuardConfigError) as exc:
        load_guard(REPO_PHRASES, missing)
    assert str(missing) in str(exc.value)
    assert "CLAIM_PHRASES_PATH" in str(exc.value)

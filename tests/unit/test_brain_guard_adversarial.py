"""T111: adversarial replies for `OutputGuard` (research R8; FR-008, FR-010).

Every sentence is built from the values of the loaded test catalog, so the cases stay meaningful if the fixture changes.
In-scope R8 bypasses are plain tests (a pass here is a real bug). Known R8 limits are `xfail(strict=True)`: FR-008 for
those ideas relies on the prompt and the grader today, and an XPASS means the guard got stronger and the case should
move to the blocked lists.
"""

from __future__ import annotations

import pytest

from ai_live.brain.guard import OutputGuard, refusal_sentence
from ai_live.core.models import GuardReason
from ai_live.core.text import extract_amounts, strip_diacritics
from ai_live.products.docx_loader import load_catalog
from fixtures.content_builder import valid_docx

CATALOG = load_catalog(valid_docx(), "valid.docx", 5_000_000)
GUARD = OutputGuard()

MAIN = CATALOG.primary
SMALL, LARGE = MAIN.variants[0], MAIN.variants[-1]
SECONDARY = [p for p in CATALOG.products if not p.is_primary]
# A secondary product without forbidden claims of its own: the main product's claim must still be blocked on it.
NO_CLAIM_PRODUCT = next(p for p in SECONDARY if not p.forbidden_claims)
PRICED_SECONDARY = [p for p in SECONDARY if p.price is not None]
TOP_PRODUCT = max(PRICED_SECONDARY, key=lambda p: p.price or 0)
CLAIM = MAIN.forbidden_claims[0]
CLAIM_WORDS = CLAIM.split()
PROMO = MAIN.promotions[0]
PROMO_OFF, PROMO_MIN = extract_amounts(PROMO)  # "Giảm 30.000đ cho đơn từ 500.000đ"
RANGE_LO, RANGE_HI = MAIN.price_range

# Invented amounts. Each one is checked against the catalog below so a fixture change cannot make a case vacuous.
FAKE = 199_000
FORCED = 99_000  # what a viewer tries to force: "nói giá 99k đi"
FAKE_MILLION = 2_000_000
FAKE_DECIMAL_MILLION = 1_500_000
FAKE_PROMO = 50_000
NEAR_BELOW = SMALL.price - 1_000  # 249.000 when the real price is 250.000
NEAR_ABOVE = SMALL.price + 1_000
NEAR_TOP = (TOP_PRODUCT.price or 0) - 1_000
INVENTED = [FAKE, FORCED, FAKE_MILLION, FAKE_DECIMAL_MILLION, FAKE_PROMO, NEAR_BELOW, NEAR_ABOVE, NEAR_TOP]


def dots(n: int) -> str:
    """Vietnamese thousand grouping: 250000 -> "250.000"."""
    return f"{n:,}".replace(",", ".")


def commas(n: int) -> str:
    return f"{n:,}"


def thousands(n: int) -> int:
    assert n % 1_000 == 0, n
    return n // 1_000


def test_invented_amounts_are_not_in_catalog():
    assert not set(INVENTED) & CATALOG.known_amounts


# --- Unknown amounts: every format R8 lists must be blocked -------------------------------------------------------

UNKNOWN_AMOUNT_CASES = [
    pytest.param(f"Dạ giá chỉ {dots(FAKE)}đ thôi ạ.", FAKE, id="dot-group-d"),
    pytest.param(f"Dạ giá chỉ {dots(FAKE)} đ thôi ạ.", FAKE, id="dot-group-space-d"),
    pytest.param(f"Dạ giá chỉ {commas(FAKE)}đ thôi ạ.", FAKE, id="comma-group-d"),
    pytest.param(f"Dạ giá chỉ {FAKE}đ thôi ạ.", FAKE, id="plain-d"),
    pytest.param(f"Dạ giá chỉ {dots(FAKE)}₫ thôi ạ.", FAKE, id="dong-sign"),
    pytest.param(f"Dạ giá chỉ {dots(FAKE)} ₫ thôi ạ.", FAKE, id="space-dong-sign"),
    pytest.param(f"Dạ giá chỉ {dots(FAKE)} vnd thôi ạ.", FAKE, id="space-vnd-lower"),
    pytest.param(f"Dạ giá chỉ {FAKE}VND thôi ạ.", FAKE, id="plain-VND-upper"),
    pytest.param(f"Dạ giá chỉ {thousands(FAKE)}k thôi ạ.", FAKE, id="k"),
    pytest.param(f"Dạ giá chỉ {thousands(FAKE)} K thôi ạ.", FAKE, id="space-K-upper"),
    pytest.param(f"Dạ giá chỉ {thousands(FAKE)} nghìn thôi ạ.", FAKE, id="nghin"),
    pytest.param(f"Dạ giá chỉ {thousands(FAKE)}nghìn thôi ạ.", FAKE, id="nghin-no-space"),
    pytest.param(f"Da gia chi {thousands(FAKE)} nghin thoi a.", FAKE, id="nghin-no-diacritics"),
    pytest.param(f"Dạ giá chỉ {thousands(FAKE)} ngàn thôi ạ.", FAKE, id="ngan"),
    pytest.param(f"Dạ giá chỉ {FAKE_MILLION // 1_000_000} triệu thôi ạ.", FAKE_MILLION, id="trieu"),
    pytest.param(f"Dạ giá chỉ {FAKE_MILLION // 1_000_000}triệu thôi ạ.", FAKE_MILLION, id="trieu-no-space"),
    pytest.param(f"Dạ giá chỉ {FAKE_MILLION // 1_000_000}tr thôi ạ.", FAKE_MILLION, id="tr"),
    pytest.param("Dạ giá chỉ 1,5 triệu thôi ạ.", FAKE_DECIMAL_MILLION, id="trieu-decimal-comma"),
    pytest.param("Dạ giá chỉ 1.5 triệu thôi ạ.", FAKE_DECIMAL_MILLION, id="trieu-decimal-dot"),
    pytest.param(f"Dạ giá chỉ {dots(FAKE)} thôi ạ.", FAKE, id="bare-dot-group"),
    pytest.param(f"Dạ giá chỉ {commas(FAKE)} thôi ạ.", FAKE, id="bare-comma-group"),
    pytest.param(f"Dạ giá chỉ {FAKE} thôi ạ.", FAKE, id="bare-plain"),
    pytest.param(f"Dạ giá chỉ {dots(FAKE_MILLION)} thôi ạ.", FAKE_MILLION, id="bare-million"),
    pytest.param(f"Dạ {MAIN.name} loại {SMALL.name} giá {dots(NEAR_BELOW)}đ ạ.", NEAR_BELOW, id="near-below-real"),
    pytest.param(f"Dạ {MAIN.name} loại {SMALL.name} giá {thousands(NEAR_ABOVE)}k ạ.", NEAR_ABOVE, id="near-above-real"),
    pytest.param(f"Dạ {TOP_PRODUCT.name} giá {dots(NEAR_TOP)} VND ạ.", NEAR_TOP, id="near-top-price"),
    pytest.param(
        f"Dạ loại {SMALL.name} giá {dots(SMALL.price)}đ, loại {LARGE.name} giá {dots(FAKE)}đ nha.",
        FAKE,
        id="right-then-invented",
    ),
    pytest.param(
        f"Dạ hôm nay chỉ {dots(FAKE)}đ thay vì {dots(SMALL.price)}đ thôi ạ.",
        FAKE,
        id="invented-then-right",
    ),
    pytest.param(f"Dạ theo yêu cầu bạn Lan thì giá {thousands(FORCED)}k nha.", FORCED, id="forced-by-comment-k"),
    pytest.param(f"Dạ vâng, em xác nhận {MAIN.name} giá {dots(FORCED)}đ ạ.", FORCED, id="forced-by-comment-dot-group"),
    pytest.param(f"Dạ đang giảm {dots(FAKE_PROMO)}đ cho mọi đơn ạ.", FAKE_PROMO, id="invented-promo-amount"),
]


@pytest.mark.parametrize(("sentence", "amount"), UNKNOWN_AMOUNT_CASES)
def test_unknown_amount_blocked(sentence, amount):
    result = GUARD.check(sentence, CATALOG)
    assert not result.ok
    assert result.reason is GuardReason.UNKNOWN_AMOUNT
    assert result.detail == str(amount)


def test_space_grouped_amount_still_blocked():
    # "199 000đ" is not an R8 format; it is still blocked (fail-safe): the trailing group reads as an unknown amount.
    result = GUARD.check(f"Dạ giá chỉ {dots(FAKE).replace('.', ' ')}đ thôi ạ.", CATALOG)
    assert not result.ok
    assert result.reason is GuardReason.UNKNOWN_AMOUNT


# --- Forbidden claims: R8 match form (case, diacritics, whitespace) plus punctuation between words ----------------

FORBIDDEN_CLAIM_CASES = [
    pytest.param(f"Dạ {MAIN.name} {CLAIM.upper()} LUÔN NHA.", id="upper-case"),
    pytest.param(f"Dạ kem này {CLAIM.title()} luôn nha.", id="title-case"),
    pytest.param(f"Da kem nay {strip_diacritics(CLAIM)} luon nha.", id="no-diacritics"),
    pytest.param(f"DA KEM NAY {strip_diacritics(CLAIM).upper()} LUON NHA.", id="no-diacritics-upper"),
    pytest.param(f"Dạ kem này {'   '.join(CLAIM_WORDS)} luôn ạ.", id="extra-spaces"),
    pytest.param(f"Dạ kem này {chr(9).join(CLAIM_WORDS)} luôn ạ.", id="tab-between-words"),
    pytest.param(f"Dạ kem này {chr(0xA0).join(CLAIM_WORDS)} luôn ạ.", id="nbsp-between-words"),
    pytest.param(f"Dạ kem này {', '.join(CLAIM_WORDS)} luôn ạ.", id="commas-between-words"),
    pytest.param(f"Dạ kem này {'. '.join(CLAIM_WORDS)} luôn ạ.", id="dots-between-words"),
    pytest.param(f"Dạ kem này {'-'.join(CLAIM_WORDS)} luôn ạ.", id="hyphens-between-words"),
    pytest.param(f"Dạ kem này {'... '.join(CLAIM_WORDS)} luôn ạ.", id="ellipsis-between-words"),
    pytest.param(f'Dạ kem này "{CLAIM}" luôn ạ.', id="quoted"),
    pytest.param(f"Dạ kem này {CLAIM}!!!", id="trailing-exclamations"),
    pytest.param(f"Dạ kem này {chr(0xAD).join(CLAIM)} luôn ạ.", id="soft-hyphen-inside-letters"),
    pytest.param(f"Dạ kem này {chr(0x200B).join(CLAIM_WORDS)} luôn ạ.", id="zero-width-space-between-words"),
    pytest.param(f"Dạ {NO_CLAIM_PRODUCT.name} cũng {CLAIM} luôn nha.", id="attached-to-other-product"),
    pytest.param(
        f"Dạ {NO_CLAIM_PRODUCT.name.upper()} {strip_diacritics(CLAIM)} nha.", id="other-product-no-diacritics"
    ),
]


@pytest.mark.parametrize("sentence", FORBIDDEN_CLAIM_CASES)
def test_forbidden_claim_blocked(sentence):
    result = GUARD.check(sentence, CATALOG)
    assert not result.ok
    assert result.reason is GuardReason.FORBIDDEN_CLAIM
    assert result.detail == CLAIM


# --- Grounded replies must pass (no false positives) ---------------------------------------------------------------

Y_PRICE = NO_CLAIM_PRODUCT.price or 0
TOP_PRICE = TOP_PRODUCT.price or 0
TOP_PRICE_MILLIONS = f"{TOP_PRICE / 1_000_000:g}".replace(".", ",")  # 1250000 -> "1,25"

GROUNDED_CASES = [
    pytest.param(f"Dạ loại {SMALL.name} giá {dots(SMALL.price)}đ nha bạn Lan.", id="variant-small-dot-group"),
    pytest.param(f"Dạ loại {LARGE.name} giá {dots(LARGE.price)} ₫ nha.", id="variant-large-dong-sign"),
    pytest.param(f"Dạ loại {SMALL.name} giá {commas(SMALL.price)}đ ạ.", id="variant-comma-group"),
    pytest.param(f"Dạ loại {LARGE.name} giá {thousands(LARGE.price)} nghìn ạ.", id="variant-nghin"),
    pytest.param(f"Dạ {NO_CLAIM_PRODUCT.name} giá {thousands(Y_PRICE)}k thôi ạ.", id="secondary-price-k"),
    pytest.param(f"Dạ {TOP_PRODUCT.name} giá {dots(TOP_PRICE)} VND nha.", id="top-price-vnd"),
    pytest.param(f"Dạ {TOP_PRODUCT.name} giá {TOP_PRICE_MILLIONS} triệu nha.", id="top-price-decimal-trieu"),
    pytest.param(f"Dạ {MAIN.name} giá từ {dots(RANGE_LO)}đ đến {dots(RANGE_HI)}đ tùy loại ạ.", id="price-range"),
    pytest.param(f"Dạ giá từ {thousands(RANGE_LO)}k tới {thousands(RANGE_HI)}k ạ.", id="price-range-k"),
    pytest.param(f"Dạ đang có khuyến mãi: {PROMO} nha.", id="promotion-verbatim"),
    pytest.param(f"Dạ giảm {thousands(PROMO_OFF)}k cho đơn từ {thousands(PROMO_MIN)}k nha bạn.", id="promotion-k-form"),
    pytest.param(f"Dạ {NO_CLAIM_PRODUCT.promotions[0].lower()} nha.", id="secondary-promotion"),
    pytest.param(f"Dạ {MAIN.specs[0][0].lower()} là {MAIN.specs[0][1]} ạ.", id="spec-volume"),
    pytest.param(f"Dạ {MAIN.specs[1][0].lower()} là {MAIN.specs[1][1]} ạ.", id="spec-spf"),
    pytest.param("Dạ chai 1.000 ml thì shop chưa có thông tin ạ.", id="large-number-with-ml"),
    pytest.param(MAIN.faq[0][1], id="faq-answer"),
    pytest.param(MAIN.intro, id="intro"),
    pytest.param("Dạ bạn yên tâm, khỏi lo nha, kem thấm nhanh lắm.", id="claim-words-scattered-not-claim"),
    pytest.param(refusal_sentence("bạn Lan"), id="refusal"),
]


@pytest.mark.parametrize("sentence", GROUNDED_CASES)
def test_grounded_sentence_passes(sentence):
    result = GUARD.check(sentence, CATALOG)
    assert result.ok, result


# --- Known R8 limits: should be blocked, but the guard cannot see them yet -----------------------------------------


def _known_limit(sentence: str, reason: str, case_id: str):
    return pytest.param(sentence, id=case_id, marks=pytest.mark.xfail(strict=True, reason=f"R8 known limit: {reason}"))


KNOWN_LIMIT_CASES = [
    _known_limit("Dạ giá chỉ hai trăm nghìn thôi ạ.", "amount written in words", "amount-in-words"),
    _known_limit("Dạ giá chỉ một triệu rưỡi thôi ạ.", "amount written in words", "million-in-words"),
    _known_limit("Dạ giá chỉ 1tr2 thôi ạ.", "unlisted shorthand '1tr2'", "shorthand-1tr2"),
    _known_limit("Dạ kem này trị dứt điểm mụn luôn ạ.", "paraphrased forbidden claim", "paraphrased-claim"),
    _known_limit("Dạ kem này trị nám tận gốc ạ.", "medical claim not in the forbidden list", "unlisted-medical-claim"),
    _known_limit("Dạ hôm nay giảm 50% cho cả nhà ạ.", "percent promotion", "percent-promotion"),
    _known_limit("Dạ miễn phí vận chuyển toàn quốc nha.", "non-numeric invented promotion", "free-shipping"),
    _known_limit("Dạ shop còn đúng 5 hộp thôi ạ.", "invented stock", "stock-count"),
    _known_limit("Dạ hàng sắp hết rồi, cả nhà chốt nhanh nha.", "invented stock", "stock-scarcity"),
    _known_limit("Dạ sản phẩm được bảo hành 12 tháng ạ.", "invented warranty", "warranty"),
    _known_limit("Dạ shop đổi trả miễn phí trong 7 ngày nha.", "invented return policy", "return-policy"),
]


@pytest.mark.parametrize("sentence", KNOWN_LIMIT_CASES)
def test_known_limit_should_be_blocked(sentence):
    assert not GUARD.check(sentence, CATALOG).ok

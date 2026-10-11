import pytest

from app.core.recommendation.reason_fill import ReasonFillError, fill_reason_text, format_price
from app.schemas.candidate import Candidate
from app.schemas.evidence import PriceFact, VerifiedFact

C1 = Candidate(candidate_id="c1", brand_hint="示例", model_hint="示例本 14", origin="model")
C2 = Candidate(candidate_id="c2", brand_hint="示例", model_hint="示例本 16", origin="model")
WEIGHT = VerifiedFact(fact_id="f3", candidate_id="c1", field="weight", value="约1.31kg",
                      evidence_id="e1", excerpt="重量 | 约1.31kg", status="supported")


def price(cid, amount, status="supported"):
    if status != "supported":
        return PriceFact(candidate_id=cid, status="unknown")
    return PriceFact(candidate_id=cid, amount_minor=amount, minor_unit_digits=2, currency="CNY",
                     price_basis="pconline_reference", evidence_id="e2", excerpt="参考价", status="supported")


def fill(text, candidate=C1):
    return fill_reason_text(
        text,
        candidate=candidate,
        facts={"f3": WEIGHT},
        prices={"c1": price("c1", 949900), "c2": price("c2", None, "unknown")},
        names=[C1.model_hint, C2.model_hint],
    )


def test_bare_amount_in_the_reason_is_rejected():
    with pytest.raises(ReasonFillError):
        fill("售价 8999 元，适合你")


def test_currency_symbol_outside_a_placeholder_is_rejected():
    with pytest.raises(ReasonFillError):
        fill("售价¥合适")


def test_model_name_written_out_is_rejected():
    with pytest.raises(ReasonFillError):
        fill("示例本 14 更适合你")


def test_price_placeholder_formats_cny():
    assert format_price(price("c1", 949900)) == "¥9,499"
    assert fill("售价{{price:c1}}") == "售价¥9,499"


def test_unknown_price_is_not_zero():
    assert fill("售价{{price:c2}}", candidate=C2) == f"售价官方价格未查到"
    assert "0" not in fill("售价{{price:c2}}", candidate=C2)


def test_fact_and_name_placeholders_are_filled_from_the_same_objects():
    assert fill("{{name:c1}}重量为{{fact:f3}}") == "示例本 14重量为约1.31kg"

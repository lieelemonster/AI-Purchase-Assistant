from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from app.schemas.evidence import EvidenceDocument, PriceFact, VerifiedFact

NOW = datetime(2026, 10, 11, 12, 0, tzinfo=timezone.utc)


def price(**overrides):
    data = {
        "candidate_id": "c1",
        "amount_minor": 949900,
        "minor_unit_digits": 2,
        "currency": "CNY",
        "price_basis": "list_price",
        "evidence_id": "e1",
        "excerpt": "¥9,499",
        "status": "supported",
    }
    data.update(overrides)
    return data


def test_supported_cny_price_is_valid():
    assert PriceFact(**price()).amount_minor == 949900


def test_float_amount_is_rejected():
    with pytest.raises(ValidationError):
        PriceFact(**price(amount_minor=9499.0))


def test_negative_amount_is_rejected():
    with pytest.raises(ValidationError):
        PriceFact(**price(amount_minor=-1))


def test_status_verified_is_not_a_valid_status():
    with pytest.raises(ValidationError):
        PriceFact(**price(status="verified"))


def test_unknown_price_without_amount_is_valid():
    fact = PriceFact(candidate_id="c1", status="unknown")
    assert fact.amount_minor is None


@pytest.mark.parametrize("missing", ["amount_minor", "evidence_id", "excerpt"])
def test_supported_price_requires_amount_and_evidence(missing):
    data = price()
    del data[missing]
    with pytest.raises(ValidationError):
        PriceFact(**data)


def test_amount_requires_currency():
    with pytest.raises(ValidationError):
        PriceFact(**price(currency=None))


def test_supported_fact_requires_evidence():
    VerifiedFact(fact_id="f1", candidate_id="c1", field="memory", value="16", unit="GB",
                 evidence_id="e1", excerpt="16GB 统一内存", status="supported")
    with pytest.raises(ValidationError):
        VerifiedFact(fact_id="f1", candidate_id="c1", field="memory", value="16", status="supported")


def test_unknown_fact_without_value_is_valid():
    assert VerifiedFact(fact_id="f2", candidate_id="c1", field="weight", status="unknown").value is None


def test_evidence_page_date_may_be_unknown():
    doc = EvidenceDocument(evidence_id="e1", url="https://www.apple.com.cn/macbook-air/",
                           final_url="https://www.apple.com.cn/macbook-air/", fetched_at=NOW,
                           fetch_status="ok", content_hash="abc", text="MacBook Air")
    assert doc.page_date is None


def test_failed_fetch_requires_a_reason():
    with pytest.raises(ValidationError):
        EvidenceDocument(evidence_id="e1", url="https://example.com", fetched_at=NOW,
                         fetch_status="unavailable")

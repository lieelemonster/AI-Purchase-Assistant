import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.schemas.result import Reason, RecommendationResult

SAMPLE_FILE = Path(__file__).parent / "fixtures" / "result_sample.json"


def sample():
    return json.loads(SAMPLE_FILE.read_text(encoding="utf-8"))


def all_keys(value):
    if isinstance(value, dict):
        for key, child in value.items():
            yield key
            yield from all_keys(child)
    elif isinstance(value, list):
        for child in value:
            yield from all_keys(child)


def test_sample_file_matches_the_schema():
    result = RecommendationResult.model_validate(sample())
    assert result.alternatives[1].price.amount_minor is None


def test_success_requires_exactly_two_alternatives():
    data = sample()
    data["alternatives"] = data["alternatives"][:1]
    with pytest.raises(ValidationError, match="首选 1 款"):
        RecommendationResult.model_validate(data)


def test_success_requires_a_primary():
    data = sample()
    data["primary"] = None
    with pytest.raises(ValidationError):
        RecommendationResult.model_validate(data)


def test_non_success_status_may_have_no_items():
    RecommendationResult(request_id="r", status="timeout", checked_at="2026-10-11T12:00:00Z")


def test_reason_without_need_refs_is_rejected():
    with pytest.raises(ValidationError):
        Reason(need_refs=[], fact_refs=["f1"], conclusion_type="fact", text="x")


def test_fact_reason_without_fact_refs_is_rejected():
    with pytest.raises(ValidationError):
        Reason(need_refs=["r1"], conclusion_type="fact", text="x")


def test_result_has_no_purchase_fields():
    keys = set(all_keys(RecommendationResult.model_validate(sample()).model_dump()))
    assert not [k for k in keys if "buy" in k or "purchase" in k or "link" in k]


def test_unexpected_buy_url_field_is_rejected():
    data = sample()
    data["primary"]["buy_url"] = "https://example.com/buy"
    with pytest.raises(ValidationError):
        RecommendationResult.model_validate(data)

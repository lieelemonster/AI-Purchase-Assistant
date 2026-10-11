import pytest
from pydantic import ValidationError

from app.schemas.candidate import Candidate
from app.schemas.need import NeedProfile, Requirement


def requirement(**overrides):
    data = {
        "requirement_id": "r1",
        "topic": "usage",
        "statement": "主要写文档",
        "source": {"kind": "free_text", "quote": "主要写文档"},
    }
    data.update(overrides)
    return data


def candidate(**overrides):
    data = {"candidate_id": "c1", "brand_hint": "Apple", "model_hint": "MacBook Air", "origin": "model"}
    data.update(overrides)
    return data


def test_valid_need_profile_with_unknown_budget():
    need = NeedProfile(
        category_id="laptop",
        free_text="我想买笔记本，主要写文档，预算还没想好",
        requirements=[requirement()],
        unknowns=["budget"],
    )
    assert need.unknowns == ["budget"]
    assert need.requirements[0].strictness == "unknown"
    assert need.market_context.region is None


def test_unknown_category_is_rejected():
    with pytest.raises(ValidationError, match="car"):
        NeedProfile(category_id="car")


def test_requirement_without_source_is_rejected():
    data = requirement()
    del data["source"]
    with pytest.raises(ValidationError, match="source"):
        Requirement(**data)


def test_free_text_source_needs_a_quote():
    with pytest.raises(ValidationError):
        Requirement(**requirement(source={"kind": "free_text", "quote": ""}))


def test_option_source_needs_question_and_option_ids():
    Requirement(**requirement(source={"kind": "option", "question_id": "usage", "option_id": "office"}))
    with pytest.raises(ValidationError):
        Requirement(**requirement(source={"kind": "option", "question_id": "usage"}))


def test_valid_candidate():
    assert Candidate(**candidate()).origin == "model"


@pytest.mark.parametrize("extra_field", [{"price": 7999}, {"verified": True}])
def test_candidate_rejects_price_and_verified(extra_field):
    with pytest.raises(ValidationError):
        Candidate(**candidate(**extra_field))


def test_candidate_id_format_is_enforced():
    with pytest.raises(ValidationError):
        Candidate(**candidate(candidate_id="macbook"))

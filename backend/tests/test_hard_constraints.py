import asyncio
import json

from app.adapters.model.fake import FakeModelGateway
from app.core.needs.normalize import normalize_needs
from app.core.recommendation.hard_constraints import check_hard_constraints
from app.schemas.evidence import PriceFact
from app.schemas.need import NeedProfile, OptionAnswer, Requirement


def budget(strictness="hard", max_minor=600000, min_minor=None):
    return Requirement(requirement_id="r1", topic="budget", statement="预算不超过6000", strictness=strictness,
                       source={"kind": "free_text", "quote": "预算不超过6000"},
                       budget_max_minor=max_minor, budget_min_minor=min_minor)


def price(amount, basis="pconline_reference"):
    if amount is None:
        return PriceFact(candidate_id="c1", status="unknown")
    return PriceFact(candidate_id="c1", amount_minor=amount, minor_unit_digits=2, currency="CNY", price_basis=basis,
                     evidence_id="e2", excerpt="参考价", status="supported")


def check(requirement, p):
    need = NeedProfile(category_id="laptop", requirements=[requirement])
    return check_hard_constraints(need, {"c1": p})["c1"]


def test_hard_budget_excludes_a_more_expensive_candidate():
    result = check(budget(), price(699900))
    assert (result.status, result.notes) == ("excluded", ["over_budget:r1"])


def test_candidate_within_hard_budget_passes():
    assert check(budget(), price(599900)).status == "pass"


def test_budget_is_hard_even_when_strictness_is_unknown():
    assert check(budget(strictness="unknown"), price(699900)).status == "excluded"


def _priced(candidate_id, amount):
    item = price(amount)
    return item.model_copy(update={"candidate_id": candidate_id})


def test_laptop_budget_allows_five_hundred_yuan_outside_each_end():
    need = NeedProfile(
        category_id="laptop",
        option_answers=[OptionAnswer(question_id="budget", option_ids=["5000_8000"])],
    )
    result = check_hard_constraints(need, {
        "c1": _priced("c1", 850000),
        "c2": _priced("c2", 850100),
        "c3": _priced("c3", 450000),
        "c4": _priced("c4", 449900),
    })
    assert result["c1"].status == "pass"
    assert result["c2"].status == "excluded"
    assert result["c3"].status == "pass"
    assert result["c4"].status == "excluded"


def test_headphones_allow_one_hundred_fifty_yuan():
    for category_id, option_id, low, high in (
        ("headphones", "300_1000", 30000, 100000),
    ):
        need = NeedProfile(
            category_id=category_id,
            option_answers=[OptionAnswer(question_id="budget", option_ids=[option_id])],
        )
        result = check_hard_constraints(need, {
            "c1": _priced("c1", high + 15000),
            "c2": _priced("c2", high + 15100),
            "c3": _priced("c3", low - 15000),
            "c4": _priced("c4", low - 15100),
        })
        assert result["c1"].status == "pass"
        assert result["c2"].status == "excluded"
        assert result["c3"].status == "pass"
        assert result["c4"].status == "excluded"


def test_unknown_price_is_neither_excluded_nor_treated_as_within_budget():
    result = check(budget(), price(None))
    assert (result.status, result.notes) == ("unverified", ["budget_unverified:r1"])


def test_starting_price_within_budget_carries_a_note():
    result = check(budget(), price(419900, "pconline_reference_starting"))
    assert (result.status, result.notes) == ("pass", ["starting_price_within_budget:r1"])


def test_starting_price_over_budget_is_excluded():
    assert check(budget(), price(699900, "pconline_reference_starting")).status == "excluded"


def normalize(extraction, answers=(), free_text=""):
    model = FakeModelGateway([json.dumps(extraction, ensure_ascii=False)])
    return asyncio.run(normalize_needs("laptop", list(answers), free_text, model))


def test_budget_option_range_comes_from_the_option_id():
    profile = normalize(
        {"requirements": [{"topic": "budget", "statement": "预算5000-8000", "budget_max_yuan": 99999,
                           "source": {"kind": "option", "question_id": "budget", "option_id": "5000_8000"}}]},
        answers=[OptionAnswer(question_id="budget", option_ids=["5000_8000"])],
    )
    r = profile.requirements[0]
    assert (r.budget_min_minor, r.budget_max_minor) == (500000, 800000)


def test_amount_from_free_text_must_appear_in_the_quote():
    text = "预算不超过6000，最好轻一点"
    good = normalize({"requirements": [{"topic": "budget", "statement": "预算上限6000", "strictness": "hard",
                                        "budget_max_yuan": 6000, "source": {"kind": "free_text", "quote": "预算不超过6000"}}]},
                     free_text=text)
    bad = normalize({"requirements": [{"topic": "budget", "statement": "预算上限7000", "strictness": "hard",
                                       "budget_max_yuan": 7000, "source": {"kind": "free_text", "quote": "预算不超过6000"}}]},
                    free_text=text)
    assert good.requirements[0].budget_max_minor == 600000
    assert bad.requirements[0].budget_max_minor is None


def test_amount_must_match_a_whole_number_in_the_quote():
    def max_for(amount, quote):
        profile = normalize({"requirements": [{"topic": "budget", "statement": quote, "budget_max_yuan": amount,
                                               "source": {"kind": "free_text", "quote": quote}}]}, free_text=quote)
        return profile.requirements[0].budget_max_minor

    assert max_for(6000, "预算不超过16000") is None
    assert max_for(10000, "11万以内") is None
    assert max_for(12000, "预算12,000以内") == 1200000


def test_wan_amount_in_the_quote_is_accepted():
    profile = normalize({"requirements": [{"topic": "budget", "statement": "1万以内", "budget_max_yuan": 10000,
                                           "source": {"kind": "free_text", "quote": "1万以内"}}]},
                        free_text="剪视频，1万以内")
    assert profile.requirements[0].budget_max_minor == 1000000

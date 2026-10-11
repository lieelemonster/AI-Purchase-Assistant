import asyncio
import json

import pytest

from app.adapters.model.base import ModelGatewayError
from app.adapters.model.fake import FakeModelGateway
from app.core.recommendation.ranking import RankingError, rank_and_explain
from app.schemas.candidate import Candidate
from app.schemas.evidence import PriceFact, VerifiedFact
from app.schemas.need import NeedProfile, Requirement

NEED = NeedProfile(
    category_id="laptop",
    requirements=[Requirement(requirement_id="r1", topic="portability", statement="经常带出门",
                              source={"kind": "option", "question_id": "portability", "option_id": "often"})],
    unknowns=["budget"],
)
CANDIDATES = [Candidate(candidate_id=f"c{i}", brand_hint="示例品牌", model_hint=f"示例本 {i}", origin="model") for i in range(1, 5)]
FACTS = {f"c{i}": [VerifiedFact(fact_id=f"f{i}", candidate_id=f"c{i}", field="weight", value=f"约1.{i}kg",
                                evidence_id="e1", excerpt="重量 | x", status="supported")] for i in range(1, 5)}
PRICES = {"c1": PriceFact(candidate_id="c1", amount_minor=599900, minor_unit_digits=2, currency="CNY",
                          price_basis="pconline_reference", evidence_id="e2", excerpt="参考价", status="supported")}


def reason(cid, fact_refs=None, need_refs=("r1",), text=None, kind="fact"):
    fid = f"f{cid[1:]}"
    return {"need_refs": list(need_refs), "fact_refs": [fid] if fact_refs is None else fact_refs,
            "conclusion_type": kind, "text": text or f"{{{{name:{cid}}}}}重量为{{{{fact:{fid}}}}}，适合经常带出门。"}


def draft(ranking, reasons=None):
    return json.dumps({"ranking": ranking, "reasons": reasons or {c: [reason(c)] for c in ranking}}, ensure_ascii=False)


def rank(*replies, candidates=CANDIDATES):
    model = FakeModelGateway(list(replies))
    return asyncio.run(rank_and_explain(NEED, candidates, FACTS, PRICES, model)), model


def test_valid_ranking_is_accepted():
    result, model = rank(draft(["c2", "c1", "c3"]))
    assert result.order == ["c2", "c1", "c3"]
    assert result.reasons["c2"][0].fact_refs == ["f2"]
    assert len(model.calls) == 1


def test_model_receives_only_supplied_facts_and_prices():
    _, model = rank(draft(["c1", "c2", "c3"]))
    payload = model.calls[0]["payload"]
    c1 = payload["candidates"][0]
    assert c1["facts"] == [{"fact_id": "f1", "field": "重量", "value": "约1.1kg"}]
    assert c1["price"] == {"ref": "price:c1", "yuan": 5999.0, "basis": "pconline_reference"}
    assert payload["candidates"][1]["price"] == {"ref": None, "status": "unknown"}


def test_candidate_outside_the_allowed_set_is_rejected_then_retried():
    result, model = rank(draft(["c9", "c1", "c2"]), draft(["c1", "c2", "c3"]))
    assert result.order == ["c1", "c2", "c3"]
    assert "c9" in " ".join(model.calls[1]["payload"]["previous_problems"])


def test_reference_to_a_missing_fact_fails_after_retry():
    bad = draft(["c1", "c2", "c3"], {c: [reason(c, fact_refs=["f99"])] for c in ["c1", "c2", "c3"]})
    with pytest.raises(RankingError, match="f99"):
        rank(bad, bad)


def test_fact_of_another_candidate_cannot_be_cited():
    bad = draft(["c1", "c2", "c3"], {"c1": [reason("c1", fact_refs=["f2"])], "c2": [reason("c2")], "c3": [reason("c3")]})
    with pytest.raises(RankingError, match="不属于它"):
        rank(bad, bad)


def test_reason_without_need_refs_is_rejected():
    bad = draft(["c1", "c2", "c3"], {c: [reason(c, need_refs=())] for c in ["c1", "c2", "c3"]})
    with pytest.raises(RankingError, match="不存在的需求"):
        rank(bad, bad)


def test_unknown_topic_can_be_referenced_as_a_limitation():
    reasons = {c: [reason(c), reason(c, fact_refs=[], need_refs=("unknown:budget",), kind="judgment",
                                     text="预算未知，如果预算有限可以考虑其他款。")] for c in ["c1", "c2", "c3"]}
    result, _ = rank(draft(["c1", "c2", "c3"], reasons))
    assert result.reasons["c1"][1].need_refs == ["unknown:budget"]


def test_price_placeholder_for_unknown_price_is_rejected():
    bad = draft(["c2", "c1", "c3"], {"c2": [reason("c2", text="价格{{price:c2}}很合适")], "c1": [reason("c1")], "c3": [reason("c3")]})
    with pytest.raises(RankingError, match="price:c2"):
        rank(bad, bad)


def test_fewer_than_three_allowed_candidates_means_shorter_ranking():
    result, _ = rank(draft(["c2", "c1"]), candidates=CANDIDATES[:2])
    assert result.order == ["c2", "c1"]


def test_invalid_json_is_retried():
    result, _ = rank("不是 JSON", draft(["c1", "c2", "c3"]))
    assert result.order == ["c1", "c2", "c3"]


def test_service_errors_are_not_retried():
    with pytest.raises(ModelGatewayError):
        rank(ModelGatewayError("quota"))

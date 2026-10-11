import asyncio
import json

import pytest

from app.adapters.model.base import ModelGatewayError
from app.adapters.model.fake import FakeModelGateway
from app.core.candidates.generate import propose_candidates
from app.schemas.need import NeedProfile

NEED = NeedProfile(category_id="laptop", free_text="主要写文档，预算还没想好", unknowns=["budget"])


def reply(candidates):
    return json.dumps({"candidates": candidates}, ensure_ascii=False)


def fictional(i, **extra):
    return {"brand_hint": "示例品牌", "model_hint": f"轻薄本 {i}", **extra}


def propose(gateway, max_candidates=6):
    return asyncio.run(propose_candidates(NEED, gateway, max_candidates))


def test_candidates_are_truncated_to_the_limit():
    candidates = propose(FakeModelGateway([reply([fictional(i) for i in range(10)])]), max_candidates=6)
    assert len(candidates) == 6


def test_ids_and_origin_are_assigned_by_the_program():
    gateway = FakeModelGateway([reply([fictional(1, candidate_id="c9", origin="search"), fictional(2, id="x")])])
    candidates = propose(gateway)
    assert [c.candidate_id for c in candidates] == ["c1", "c2"]
    assert all(c.origin == "model" for c in candidates)


def test_prices_and_verified_claims_from_the_model_are_dropped():
    gateway = FakeModelGateway([reply([fictional(1, price=7999, verified=True)])])
    candidate = propose(gateway)[0]
    dumped = candidate.model_dump()
    assert "price" not in dumped
    assert "verified" not in dumped
    assert candidate.model_hint == "轻薄本 1"


def test_model_receives_the_need_and_the_limit():
    gateway = FakeModelGateway([reply([])])
    propose(gateway, max_candidates=4)
    call = gateway.calls[0]
    assert call["payload"]["max_candidates"] == 4
    assert call["payload"]["need"]["unknowns"] == ["budget"]
    assert "4" in call["task"]


def test_malformed_model_output_is_reported():
    gateway = FakeModelGateway([reply([{"brand_hint": "", "model_hint": "轻薄本"}])])
    with pytest.raises(ModelGatewayError) as e:
        propose(gateway)
    assert e.value.kind == "invalid_output"

import asyncio

import pytest
from pydantic import ValidationError

from app.adapters.search.base import SearchGatewayError, SearchHit
from app.adapters.search.fake import FakeSearchGateway
from app.schemas.evidence import EvidenceDocument, VerifiedFact

HIT = SearchHit(url="https://example.com/laptop-a", title="轻薄本 A", snippet="售价 ¥9,499 起")


def test_fake_returns_scripted_hits_and_records_the_call():
    gateway = FakeSearchGateway({"轻薄本 A 官网": [HIT]})
    hits = asyncio.run(gateway.search("轻薄本 A 官网", region="示例地区", language="zh", limit=5))
    assert hits == [HIT]
    assert gateway.calls == [{"query": "轻薄本 A 官网", "region": "示例地区", "language": "zh", "limit": 5}]


def test_unscripted_query_returns_no_hits():
    assert asyncio.run(FakeSearchGateway().search("任意查询")) == []


def test_limit_is_applied():
    gateway = FakeSearchGateway({"q": [HIT] * 5})
    assert len(asyncio.run(gateway.search("q", limit=2))) == 2


def test_scripted_error_keeps_its_kind():
    gateway = FakeSearchGateway({"q": SearchGatewayError("auth")})
    with pytest.raises(SearchGatewayError) as e:
        asyncio.run(gateway.search("q"))
    assert e.value.kind == "auth"


@pytest.mark.parametrize("target", [EvidenceDocument, VerifiedFact])
def test_search_hit_cannot_become_evidence_or_fact(target):
    with pytest.raises(ValidationError):
        target.model_validate(HIT.model_dump())

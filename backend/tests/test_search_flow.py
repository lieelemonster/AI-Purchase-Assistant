import asyncio
import json

from app.adapters.model.fake import FakeModelGateway
from app.adapters.search.base import SearchGatewayError, SearchHit
from app.adapters.search.fake import FakeSearchGateway
from app.core.verification.source_search import SearchBudget, find_sources, write_queries
from app.schemas.candidate import Candidate
from app.schemas.need import NeedProfile

OFFICIAL = SearchHit(url="https://www.vmall.com/product/10086.html", title="华为商城")
JD_OFFICIAL_ITEM = SearchHit(url="https://item.jd.com/100012345.html", title="京东商品")
NON_OFFICIAL_SHOP = SearchHit(url="https://mall.jd.com/index-999.html", title="某店铺")
FORUM = SearchHit(url="https://bbs.example.com/thread/1", title="论坛")


def candidate(candidate_id="c1", brand="华为", model="MateBook 14"):
    return Candidate(candidate_id=candidate_id, brand_hint=brand, model_hint=model, origin="model")


def by_stage(official=(), jd=(), tmall=()):
    """按 include_sites 判断当前是哪个渠道的搜索。"""
    def responder(query, sites):
        if "item.jd.com" in sites:
            return jd
        if "detail.tmall.com" in sites:
            return tmall
        return official
    return responder


def find(gateway, cand=None, budget=None):
    return asyncio.run(find_sources(cand or candidate(), "华为 MateBook 14", gateway, budget or SearchBudget(10), "CN"))


def test_only_official_channel_hits_are_kept_with_official_site_first():
    gateway = FakeSearchGateway(responder=by_stage(official=[JD_OFFICIAL_ITEM, NON_OFFICIAL_SHOP, FORUM, OFFICIAL]))
    result = find(gateway)
    assert result.status == "found"
    assert [h.url for h in result.hits] == [OFFICIAL.url, JD_OFFICIAL_ITEM.url]
    assert [h.check.status for h in result.hits] == ["official", "store_check_required"]
    assert {s.url for s in result.skipped} == {NON_OFFICIAL_SHOP.url, FORUM.url}


def test_official_site_found_means_no_jd_or_tmall_search():
    gateway = FakeSearchGateway(responder=by_stage(official=[OFFICIAL], jd=[JD_OFFICIAL_ITEM]))
    result = find(gateway)
    assert len(gateway.calls) == 1
    assert result.searched_channels == ["official"]
    assert gateway.calls[0]["include_sites"] == ["consumer.huawei.com", "consumer.huawei.cn", "vmall.com"]
    assert gateway.calls[0]["region"] == "CN"
    assert gateway.calls[0]["language"] == "zh"


def test_jd_is_searched_only_when_official_site_has_nothing():
    gateway = FakeSearchGateway(responder=by_stage(jd=[JD_OFFICIAL_ITEM]))
    result = find(gateway)
    assert result.searched_channels == ["official", "jd"]
    assert "huawei.jd.com" in gateway.calls[1]["include_sites"]
    assert [h.check.channel for h in result.hits] == ["jd"]


def test_tmall_is_searched_last():
    gateway = FakeSearchGateway(responder=by_stage())
    result = find(gateway)
    assert result.searched_channels == ["official", "jd", "tmall"]
    assert "huaweistore.tmall.com" in gateway.calls[2]["include_sites"]
    assert (result.status, result.reason) == ("unknown", "no_official_page")


def test_channels_the_brand_does_not_have_are_skipped():
    gateway = FakeSearchGateway(responder=by_stage())
    find(gateway, candidate(brand="vivo", model="X200"))
    assert len(gateway.calls) == 2


def test_search_limit_is_shared_across_candidates():
    gateway = FakeSearchGateway(responder=by_stage())
    budget = SearchBudget(3)
    first = find(gateway, candidate("c1", "vivo", "X200"), budget)
    second = find(gateway, candidate("c2", "vivo", "X200 Pro"), budget)
    assert len(gateway.calls) == 3
    assert first.reason == "no_official_page"
    assert (second.status, second.reason) == ("unknown", "search_limit")


def test_brand_outside_the_channel_list_is_not_searched():
    gateway = FakeSearchGateway(responder=by_stage(official=[OFFICIAL]))
    result = find(gateway, candidate(brand="某杂牌"))
    assert gateway.calls == []
    assert (result.status, result.reason) == ("unknown", "brand_not_in_channel_list")


def test_search_error_moves_on_to_the_next_channel():
    def responder(query, sites):
        if "item.jd.com" in sites:
            return [JD_OFFICIAL_ITEM]
        return SearchGatewayError("timeout")

    result = find(FakeSearchGateway(responder=responder))
    assert result.errors == ["official: timeout"]
    assert result.status == "found"


def test_queries_come_from_the_model_with_fallback():
    gateway = FakeModelGateway([json.dumps({"queries": [
        {"candidate_id": "c1", "query": "华为 MateBook 14 2024 参数"},
        {"candidate_id": "c9", "query": "不存在的候选"},
    ]}, ensure_ascii=False)])
    candidates = [candidate("c1"), Candidate(candidate_id="c2", brand_hint="小米", model_hint="Redmi Book 16",
                                             generation_hint="2025", origin="model")]
    queries = asyncio.run(write_queries(candidates, NeedProfile(category_id="laptop"), gateway))
    assert queries == {"c1": "华为 MateBook 14 2024 参数", "c2": "小米 Redmi Book 16 2025"}

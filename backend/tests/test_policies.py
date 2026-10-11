import asyncio
import json

from app.adapters.catalog.pconline import CatalogHit
from app.adapters.model.fake import FakeModelGateway
from app.core.verification.budget import SearchBudget
from app.core.verification.catalog_match import CatalogMatch
from app.core.verification.catalog_policies import (
    base_model,
    dedupe_same_model,
    discover_candidates,
    match_with_retry,
    result_status,
)
from app.schemas.candidate import Candidate
from app.schemas.need import NeedProfile

NEED = NeedProfile(category_id="laptop")


def hit(product_id, name, discontinued=False):
    return CatalogHit(product_id=product_id, name=name, url=f"https://product.pconline.com.cn/notebook/demo/{product_id}.html",
                      category_dir="notebook", brand_dir="demo", discontinued=discontinued)


def candidate(cid, model="示例本 14", generation=None):
    return Candidate(candidate_id=cid, brand_hint="示例品牌", model_hint=model, generation_hint=generation, origin="model")


def matched(cid, h, alternatives=()):
    return CatalogMatch(candidate_id=cid, status="matched", hit=h, alternatives=list(alternatives))


class FakeCatalog:
    def __init__(self, results):
        self.results = results
        self.keywords = []

    async def search(self, keyword):
        self.keywords.append(keyword)
        return self.results.get(keyword, [])


def test_unmatched_candidate_is_retried_once_with_a_broader_keyword():
    catalog = FakeCatalog({"示例品牌 示例本 14": [hit("1", "示例品牌 示例本 14(16GB/512GB)")]})
    model = FakeModelGateway([
        json.dumps({"keywords": [{"candidate_id": "c1", "keyword": "示例本14 2026 16GB"}]}, ensure_ascii=False),
        json.dumps({"choices": [{"candidate_id": "c1", "product_id": "1"}]}),
    ])
    [match] = asyncio.run(match_with_retry([candidate("c1", generation="2026")], NEED, model, catalog, SearchBudget(10)))
    assert catalog.keywords == ["示例本14 2026 16GB", "示例品牌 示例本 14"]
    assert (match.status, match.hit.product_id) == ("matched", "1")


def test_retry_happens_at_most_once():
    catalog = FakeCatalog({})
    model = FakeModelGateway([json.dumps({"keywords": [{"candidate_id": "c1", "keyword": "示例本14 2026"}]}, ensure_ascii=False)])
    [match] = asyncio.run(match_with_retry([candidate("c1")], NEED, model, catalog, SearchBudget(10)))
    assert len(catalog.keywords) == 2
    assert (match.status, match.reason) == ("unknown", "not_in_catalog")


def test_retry_counts_against_the_search_limit():
    catalog = FakeCatalog({})
    model = FakeModelGateway([json.dumps({"keywords": [{"candidate_id": "c1", "keyword": "示例本14 2026"}]}, ensure_ascii=False)])
    [match] = asyncio.run(match_with_retry([candidate("c1")], NEED, model, catalog, SearchBudget(1)))
    assert len(catalog.keywords) == 1
    assert match.reason == "search_limit"


def test_base_model_strips_the_configuration():
    assert base_model("华为 MateBook 14 鸿蒙版(32GB/1TB)") == base_model("华为MateBook 14 鸿蒙版（24GB/512GB）")
    assert base_model("华为 MateBook 14 鸿蒙版(32GB/1TB)") != base_model("华为 MateBook GT 14(16GB/1TB)")


def test_two_configurations_of_the_same_model_take_one_slot():
    matches = dedupe_same_model([
        matched("c1", hit("1", "示例本 14(16GB/512GB)")),
        matched("c2", hit("2", "示例本 14(32GB/1TB)")),
        matched("c3", hit("3", "示例本 16(16GB/1TB)")),
    ])
    assert [(m.status, m.reason) for m in matches] == [("matched", None), ("unknown", "same_model_duplicate"), ("matched", None)]


def test_discovered_models_fill_up_to_three_and_are_labelled():
    cands = [candidate("c1"), candidate("c2", "示例本 16")]
    matches = [
        matched("c1", hit("1", "示例本 14(16GB/512GB)"), alternatives=[
            hit("2", "示例本 14(32GB/1TB)"),
            hit("3", "示例本 Air(16GB/512GB)", discontinued=True),
            hit("4", "示例本 Pro 14(32GB/1TB)"),
            hit("5", "示例本 X(16GB/1TB)"),
        ]),
        CatalogMatch(candidate_id="c2", status="unknown", reason="not_in_catalog"),
    ]
    new_candidates, new_matches = discover_candidates(cands, matches)
    assert [(c.candidate_id, c.model_hint, c.origin) for c in new_candidates] == [
        ("c3", "示例本 Pro 14(32GB/1TB)", "search_discovered"),
        ("c4", "示例本 X(16GB/1TB)", "search_discovered"),
    ]
    assert [m.hit.product_id for m in new_matches] == ["4", "5"]


def test_no_discovery_when_three_are_already_matched():
    cands = [candidate(f"c{i}") for i in range(1, 4)]
    matches = [matched(f"c{i}", hit(str(i), f"型号{i}(8GB)"), alternatives=[hit("9", "型号9(8GB)")]) for i in range(1, 4)]
    assert discover_candidates(cands, matches) == ([], [])


def test_still_short_after_discovery_is_not_padded():
    cands = [candidate("c1")]
    matches = [matched("c1", hit("1", "示例本 14(16GB/512GB)"))]
    new_candidates, new_matches = discover_candidates(cands, matches)
    assert new_candidates == []
    assert result_status(1 + len(new_matches)) == "insufficient_candidates"


def test_three_valid_items_is_success():
    assert result_status(3) == "success"
    assert result_status(2) == "insufficient_candidates"

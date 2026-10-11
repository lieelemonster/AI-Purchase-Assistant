import asyncio
import json

from app.adapters.catalog.pconline import CatalogHit, CatalogSearchError
from app.adapters.model.fake import FakeModelGateway
from app.core.verification.catalog_match import match_candidates
from app.core.verification.budget import SearchBudget
from app.schemas.candidate import Candidate
from app.schemas.need import NeedProfile

NEED = NeedProfile(category_id="laptop")


def hit(product_id, name="示例本 14(16GB/512GB)", category="notebook", discontinued=False):
    return CatalogHit(product_id=product_id, name=name, url=f"https://product.pconline.com.cn/{category}/demo/{product_id}.html",
                      category_dir=category, brand_dir="demo", discontinued=discontinued)


class FakeCatalog:
    def __init__(self, results):
        self.results = results
        self.keywords = []

    async def search(self, keyword):
        self.keywords.append(keyword)
        result = self.results.get(keyword, [])
        if isinstance(result, Exception):
            raise result
        return result


def candidate(cid, model="示例本 14"):
    return Candidate(candidate_id=cid, brand_hint="示例品牌", model_hint=model, origin="model")


def model_replies(keywords, choices=None):
    replies = [json.dumps({"keywords": [{"candidate_id": c, "keyword": k} for c, k in keywords.items()]}, ensure_ascii=False)]
    if choices is not None:
        replies.append(json.dumps({"choices": [{"candidate_id": c, "product_id": p} for c, p in choices.items()]}))
    return FakeModelGateway(replies)


def run(cands, model, catalog, budget=10):
    return asyncio.run(match_candidates(cands, NEED, model, catalog, SearchBudget(budget)))


def test_model_choice_inside_the_results_is_matched():
    catalog = FakeCatalog({"示例本14": [hit("1"), hit("2", "示例本 14(32GB/1TB)")]})
    model = model_replies({"c1": "示例本14"}, {"c1": "2"})
    [match] = run([candidate("c1")], model, catalog)
    assert (match.status, match.hit.product_id, match.keyword) == ("matched", "2", "示例本14")
    assert catalog.keywords == ["示例本14"]


def test_choice_not_in_this_candidates_results_is_rejected():
    model = model_replies({"c1": "示例本14"}, {"c1": "999"})
    [match] = run([candidate("c1")], model, FakeCatalog({"示例本14": [hit("1")]}))
    assert (match.status, match.reason) == ("unknown", "choice_not_in_results")


def test_discontinued_results_are_not_offered_and_cannot_be_chosen():
    model = model_replies({"c1": "示例本14"}, {"c1": "1"})
    [match] = run([candidate("c1")], model, FakeCatalog({"示例本14": [hit("1", discontinued=True), hit("2")]}))
    assert (match.status, match.reason) == ("unknown", "discontinued")
    offered = [r["product_id"] for r in model.calls[1]["payload"]["results"]["c1"]]
    assert offered == ["2"]


def test_all_results_discontinued_skips_the_selection_call():
    model = model_replies({"c1": "示例本14"})
    [match] = run([candidate("c1")], model, FakeCatalog({"示例本14": [hit("1", discontinued=True)]}))
    assert (match.status, match.reason) == ("unknown", "all_discontinued")
    assert len(model.calls) == 1


def test_model_says_none_means_not_in_catalog():
    model = model_replies({"c1": "示例本14"}, {"c1": None})
    [match] = run([candidate("c1")], model, FakeCatalog({"示例本14": [hit("1")]}))
    assert (match.status, match.reason) == ("unknown", "not_in_catalog")


def test_result_from_another_category_is_rejected():
    model = model_replies({"c1": "示例本14"}, {"c1": "7"})
    [match] = run([candidate("c1")], model, FakeCatalog({"示例本14": [hit("7", category="mobile"), hit("1")]}))
    assert (match.status, match.reason) == ("unknown", "category_mismatch")


def test_search_limit_stops_later_candidates():
    keywords = {f"c{i}": f"k{i}" for i in range(1, 5)}
    catalog = FakeCatalog({f"k{i}": [hit(str(i))] for i in range(1, 5)})
    model = model_replies(keywords, {f"c{i}": str(i) for i in range(1, 4)})
    matches = run([candidate(f"c{i}") for i in range(1, 5)], model, catalog, budget=3)
    assert catalog.keywords == ["k1", "k2", "k3"]
    assert [m.status for m in matches] == ["matched", "matched", "matched", "unknown"]
    assert matches[3].reason == "search_limit"


def test_search_failure_is_reported_per_candidate():
    model = model_replies({"c1": "k1"})
    [match] = run([candidate("c1")], model, FakeCatalog({"k1": CatalogSearchError("timeout")}))
    assert (match.status, match.reason) == ("unknown", "search_unavailable:timeout")


def test_missing_keyword_falls_back_to_candidate_hints():
    catalog = FakeCatalog({})
    run([candidate("c1", "示例本 16")], model_replies({}), catalog)
    assert catalog.keywords == ["示例品牌 示例本 16"]

from datetime import datetime, timezone

from app.adapters.catalog.pconline import CatalogHit
from app.core.verification.catalog_evidence import CatalogPages
from app.core.verification.catalog_identity import verify_catalog_identity
from app.core.verification.catalog_match import CatalogMatch
from app.schemas.evidence import EvidenceDocument, VerifiedFact

NOW = datetime(2026, 10, 11, tzinfo=timezone.utc)
BASE = "https://product.pconline.com.cn/notebook/demo/"
NAME = "示例品牌 示例本 14(16GB/512GB)"


def doc(evidence_id, url, title, text="正文", status="ok"):
    if status != "ok":
        return EvidenceDocument(evidence_id=evidence_id, url=url, fetched_at=NOW, fetch_status=status, failure_reason="timeout")
    return EvidenceDocument(evidence_id=evidence_id, url=url, final_url=url, title=title, fetched_at=NOW,
                            fetch_status="ok", content_hash="h", text=text)


def fact(field, value, fact_id="f1"):
    return VerifiedFact(fact_id=fact_id, candidate_id="c1", field=field, value=value, evidence_id="e1",
                        excerpt=f"{field} | {value}", status="supported")


def check(detail_title=f"示例品牌示例本 14(16GB/512GB)参数_太平洋产品报价", price_title=f"示例品牌示例本 14(16GB/512GB)价格",
          detail_url=BASE + "100_detail.html", price_url=BASE + "100_price.html", price_text="参考价：￥5999（行货价格）",
          facts=None, discontinued=False, price_status="ok"):
    hit = CatalogHit(product_id="100", name=NAME, url=BASE + "100.html", category_dir="notebook",
                     brand_dir="demo", discontinued=discontinued)
    match = CatalogMatch(candidate_id="c1", status="matched", hit=hit)
    pages = CatalogPages(candidate_id="c1", product_id="100", detail_evidence_id="e1", price_evidence_id="e2")
    documents = {"e1": doc("e1", detail_url, detail_title), "e2": doc("e2", price_url, price_title, price_text, price_status)}
    return verify_catalog_identity(match, pages, documents, facts if facts is not None else [fact("memory", "16GB")])


def test_matching_pages_pass_and_keep_facts():
    result = check()
    assert (result.status, result.price_page_ok, result.multi_config) == ("ok", True, False)
    assert result.facts[0].status == "supported"


def test_detail_page_for_a_different_configuration_is_rejected():
    result = check(detail_title="示例品牌示例本 14(16GB/1TB)参数")
    assert (result.status, result.reason) == ("rejected", "detail_title_mismatch")
    assert all(f.status != "supported" for f in result.facts)


def test_pages_from_different_products_are_both_rejected():
    result = check(price_url=BASE + "999_price.html")
    assert (result.status, result.reason) == ("rejected", "product_id_mismatch")
    assert result.facts[0].status == "unknown"


def test_discontinued_page_is_excluded():
    result = check(price_text="参考价：停产")
    assert (result.status, result.reason) == ("rejected", "discontinued")


def test_discontinued_flag_from_search_is_respected():
    assert check(discontinued=True).reason == "discontinued"


def test_multi_value_memory_marks_a_multi_config_page():
    result = check(facts=[fact("memory", "12GB , 16GB", "f1"), fact("storage", "256GB，512GB", "f2"), fact("usb", "2个USB3.2 , 1个USB-C", "f3")])
    assert result.multi_config is True
    values = {f.field: f.value for f in result.facts}
    assert values["memory"] == "12GB / 16GB 可选"
    assert values["storage"] == "256GB / 512GB 可选"
    assert values["usb"] == "2个USB3.2 , 1个USB-C"


def test_unreadable_price_page_is_flagged_but_specs_still_usable():
    result = check(price_status="unavailable")
    assert (result.status, result.price_page_ok) == ("ok", False)

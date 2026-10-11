from datetime import datetime, timezone

from app.core.recommendation.assemble import assemble_result, build_comparison
from app.schemas.candidate import Candidate
from app.schemas.evidence import EvidenceDocument, PriceFact, VerifiedFact
from app.schemas.result import Reason

NOW = datetime(2026, 10, 11, 12, tzinfo=timezone.utc)


def candidate(cid, name):
    return Candidate(candidate_id=cid, brand_hint="示例", model_hint=name, origin="model")


def price(cid, amount, basis="list_price", evidence="e2"):
    if amount is None:
        return PriceFact(candidate_id=cid, price_basis=basis, status="unknown")
    return PriceFact(candidate_id=cid, amount_minor=amount, minor_unit_digits=2, currency="CNY",
                     price_basis=basis, evidence_id=evidence, excerpt="参考价", status="supported")


def doc(eid, url):
    return EvidenceDocument(evidence_id=eid, url=url, final_url=url, title="参数页", fetched_at=NOW,
                            fetch_status="ok", content_hash="h", text="重量 | 1.2kg")


def reason(cid):
    return Reason(need_refs=["r1"], fact_refs=["f1"], conclusion_type="fact", text="重量{{fact:f1}}")


def test_same_currency_list_prices_subtract_as_integers():
    prices = [price("c1", 949900), price("c2", 899900)]
    compared = {entry.candidate_id: entry for entry in build_comparison(prices[0], prices)}
    assert 949900 - 899900 == 50000
    assert compared["c2"].comparable is True
    assert compared["c2"].difference_minor_vs_primary == 899900 - 949900
    assert abs(compared["c2"].difference_minor_vs_primary) == 50000


def test_starting_price_is_not_directly_comparable():
    compared = {entry.candidate_id: entry for entry in build_comparison(
        price("c1", 949900),
        [price("c1", 949900), price("c3", 419900, "pconline_reference_starting")],
    )}
    assert compared["c3"].comparable is False
    assert compared["c3"].not_comparable_reason


def test_pconline_reference_prices_compare_and_keep_source():
    facts = {
        "c1": [VerifiedFact(fact_id="f1", candidate_id="c1", field="weight", value="1.2kg",
                            evidence_id="e1", excerpt="重量 | 1.2kg", status="supported")],
        "c2": [],
    }
    result = assemble_result(
        request_id="req-1",
        status="insufficient_candidates",
        ordered=[candidate("c1", "示例本 14"), candidate("c2", "示例本 16")],
        facts=facts,
        prices={"c1": price("c1", 949900, "pconline_reference", "e1"),
                "c2": price("c2", 899900, "pconline_reference", "e2")},
        reasons={"c1": [reason("c1")], "c2": []},
        documents={
            "e1": doc("e1", "https://product.pconline.com.cn/notebook/demo/1_detail.html"),
            "e2": doc("e2", "https://product.pconline.com.cn/notebook/demo/2_price.html"),
            "e9": doc("e9", "https://product.pconline.com.cn/notebook/demo/unused.html"),
        },
        checked_at=NOW,
    )
    compared = {entry.candidate_id: entry for entry in result.comparison}
    assert compared["c1"].comparable and compared["c2"].comparable
    assert abs(compared["c2"].difference_minor_vs_primary) == 50000
    assert {source.evidence_id for source in result.evidence_sources} == {"e1", "e2"}
    assert {source.source_name for source in result.evidence_sources} == {"太平洋电脑网"}
    assert all(source.fetched_at == NOW for source in result.evidence_sources)
    dumped = result.model_dump()
    assert "buy_url" not in dumped
    assert "purchase" not in dumped

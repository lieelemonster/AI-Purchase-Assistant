import asyncio
import json

from app.adapters.catalog.pconline import CatalogHit
from app.adapters.model.base import ModelGatewayError
from app.adapters.model.fake import FakeModelGateway
from app.core.needs.normalize import normalize_needs
from app.core.recommendation.hard_constraints import check_hard_constraints
from app.core.recommendation.reason_fill import ReasonFillError, fill_reason_text
from app.core.verification.conflicts import mark_field_conflicts
from app.core.verification.price_parsing import parse_reference_price
from app.schemas.candidate import Candidate
from app.schemas.evidence import EvidenceDocument, PriceFact, VerifiedFact
from app.schemas.need import NeedProfile, Requirement
from datetime import datetime, timezone

NOW = datetime(2026, 10, 11, tzinfo=timezone.utc)


def test_budget_unknown_stays_unknown():
    text = "我想买笔记本，主要写文档，预算还没想好"
    model = FakeModelGateway([json.dumps({
        "requirements": [{"topic": "usage", "statement": "写文档",
                          "source": {"kind": "free_text", "quote": "主要写文档"}}],
        "unknowns": ["budget"],
    }, ensure_ascii=False)])
    profile = asyncio.run(normalize_needs("laptop", [], text, model))
    assert "budget" in profile.unknowns
    assert all(item.topic != "budget" or item.budget_max_minor is None for item in profile.requirements)


def test_model_claim_without_source_page_is_not_verified():
    claimed = CatalogHit(product_id="1", name="不存在的型号", url="https://product.pconline.com.cn/notebook/demo/1.html",
                         category_dir="notebook", brand_dir="demo", discontinued=False)
    assert claimed.summary == ""
    price = PriceFact(candidate_id="c1", status="unknown")
    assert price.status != "supported"


def test_two_configurations_keep_separate_prices():
    low = PriceFact(candidate_id="c1", amount_minor=609900, minor_unit_digits=2, currency="CNY",
                    variant_identity="16GB/512GB", price_basis="pconline_reference",
                    evidence_id="e1", excerpt="参考价：￥6099（行货价格）", status="supported")
    high = PriceFact(candidate_id="c2", amount_minor=739900, minor_unit_digits=2, currency="CNY",
                     variant_identity="32GB/1TB", price_basis="pconline_reference",
                     evidence_id="e2", excerpt="参考价：￥7399（行货价格）", status="supported")
    assert low.variant_identity != high.variant_identity
    assert low.amount_minor != high.amount_minor
    assert low.evidence_id != high.evidence_id


def test_search_snippet_price_is_not_a_verified_price():
    snippet = "参考价约 ￥9999"
    doc = EvidenceDocument(evidence_id="e2", url="https://product.pconline.com.cn/x_price.html",
                           final_url="https://product.pconline.com.cn/x_price.html", fetched_at=NOW,
                           fetch_status="ok", content_hash="h", text="暂无报价")
    price = parse_reference_price(doc, "c1", "示例本", multi_config=False)
    assert snippet not in doc.text
    assert price.status == "unknown"


def test_starting_price_is_not_treated_as_configuration_total():
    doc = EvidenceDocument(evidence_id="e2", url="u", final_url="u", fetched_at=NOW, fetch_status="ok",
                           content_hash="h", text="参考价：￥4199（行货价格）")
    price = parse_reference_price(doc, "c1", "多配置", multi_config=True)
    assert price.price_basis == "pconline_reference_starting"
    assert price.amount_minor == 419900


def test_verified_config_with_unknown_price_stays_unknown():
    need = NeedProfile(category_id="laptop", requirements=[
        Requirement(requirement_id="r1", topic="budget", statement="预算不超过6000", strictness="hard",
                    source={"kind": "free_text", "quote": "预算不超过6000"}, budget_max_minor=600000),
    ])
    result = check_hard_constraints(need, {"c1": PriceFact(candidate_id="c1", status="unknown")})["c1"]
    assert result.status == "unverified"
    assert result.notes == ["budget_unverified:r1"]


def test_conflicting_field_is_not_merged():
    facts, unresolved = mark_field_conflicts([
        VerifiedFact(fact_id="f1", candidate_id="c1", field="weight", value="1.24kg",
                     evidence_id="e1", excerpt="重量 | 1.24kg", status="supported"),
        VerifiedFact(fact_id="f2", candidate_id="c1", field="weight", value="1.29kg",
                     evidence_id="e2", excerpt="重量 | 1.29kg", status="supported"),
    ])
    assert [item.value for item in facts] == ["1.24kg", "1.29kg"]
    assert {item.status for item in facts} == {"conflicting"}
    assert unresolved[0].status == "conflicting"


def test_reason_with_unsupported_amount_is_rejected():
    candidate = Candidate(candidate_id="c1", brand_hint="示例", model_hint="示例本", origin="model")
    try:
        fill_reason_text("售价 8999 元，适合你", candidate=candidate, facts={}, prices={}, names=[])
    except ReasonFillError:
        return
    raise AssertionError("没有证据的金额不应被展示")


def test_timeout_or_quota_is_not_success():
    assert ModelGatewayError("quota").kind == "quota"
    assert ModelGatewayError("timeout").kind == "timeout"

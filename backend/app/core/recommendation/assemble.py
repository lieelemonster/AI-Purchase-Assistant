from datetime import datetime
from typing import Dict, List, Optional
from urllib.parse import urlsplit

from app.schemas.candidate import Candidate
from app.schemas.evidence import EvidenceDocument, PriceFact, VerifiedFact
from app.schemas.result import (
    ComparisonEntry,
    EvidenceSource,
    RecommendationItem,
    RecommendationResult,
    ResultStatus,
)

# 同一口径、可以相减的价格类型。起售价只表示最低配置，不能和具体配置价直接比。
COMPARABLE_BASES = {"pconline_reference", "list_price"}
PCONLINE_SOURCE = "太平洋电脑网"


def _source_name(url: str) -> Optional[str]:
    host = (urlsplit(url).hostname or "").lower()
    if host == "product.pconline.com.cn" or host.endswith(".pconline.com.cn"):
        return PCONLINE_SOURCE
    return None


def _not_comparable_reason(price: PriceFact) -> str:
    if price.status != "supported" or price.amount_minor is None:
        return "未查到参考价"
    if price.price_basis in {"pconline_reference_starting", "starting_price"}:
        return "这是起售价，不能代表所选配置的总价"
    if price.price_basis not in COMPARABLE_BASES:
        return f"价格口径为{price.price_basis}，不能直接比较"
    return "币种或价格口径与首选不同"


def _comparable(price: PriceFact, primary: PriceFact) -> bool:
    return (
        price.status == "supported"
        and primary.status == "supported"
        and price.amount_minor is not None
        and primary.amount_minor is not None
        and price.currency == primary.currency
        and price.price_basis == primary.price_basis
        and price.price_basis in COMPARABLE_BASES
    )


def build_comparison(primary: PriceFact, prices: List[PriceFact]) -> List[ComparisonEntry]:
    entries = []
    for price in prices:
        if _comparable(price, primary):
            entries.append(ComparisonEntry(
                candidate_id=price.candidate_id,
                comparable=True,
                difference_minor_vs_primary=price.amount_minor - primary.amount_minor,
            ))
        else:
            entries.append(ComparisonEntry(
                candidate_id=price.candidate_id,
                comparable=False,
                not_comparable_reason=_not_comparable_reason(price),
            ))
    return entries


def _cited_evidence_ids(items: List[RecommendationItem]) -> List[str]:
    ids = []
    for item in items:
        for fact in item.facts:
            if fact.evidence_id:
                ids.append(fact.evidence_id)
        if item.price.evidence_id:
            ids.append(item.price.evidence_id)
        for reason in item.reasons:
            for ref in reason.fact_refs:
                if ref.startswith("f"):
                    matched = next((fact.evidence_id for fact in item.facts if fact.fact_id == ref), None)
                    if matched:
                        ids.append(matched)
    seen = []
    for evidence_id in ids:
        if evidence_id not in seen:
            seen.append(evidence_id)
    return seen


def assemble_result(
    *,
    request_id: str,
    status: ResultStatus,
    ordered: List[Candidate],
    facts: Dict[str, List[VerifiedFact]],
    prices: Dict[str, PriceFact],
    reasons: Dict[str, list],
    documents: Dict[str, EvidenceDocument],
    checked_at: datetime,
) -> RecommendationResult:
    """名称、参数和价格都从本次证据对象取值；来源只保留结果实际引用过的页面。"""
    def item(candidate: Candidate) -> RecommendationItem:
        return RecommendationItem(
            candidate_id=candidate.candidate_id,
            name=candidate.model_hint,
            facts=list(facts.get(candidate.candidate_id, [])),
            price=prices[candidate.candidate_id],
            reasons=list(reasons.get(candidate.candidate_id, [])),
        )

    shown = [item(candidate) for candidate in ordered]
    primary = shown[0] if shown else None
    alternatives = shown[1:]
    comparison = build_comparison(primary.price, [entry.price for entry in shown]) if primary else []
    sources = []
    for evidence_id in _cited_evidence_ids(shown):
        doc = documents.get(evidence_id)
        if doc is None or doc.fetch_status != "ok":
            continue
        sources.append(EvidenceSource(
            evidence_id=doc.evidence_id,
            url=doc.final_url or doc.url,
            title=doc.title,
            fetched_at=doc.fetched_at,
            source_name=_source_name(doc.final_url or doc.url),
        ))
    return RecommendationResult(
        request_id=request_id,
        status=status,
        primary=primary,
        alternatives=alternatives,
        comparison=comparison,
        evidence_sources=sources,
        checked_at=checked_at,
    )

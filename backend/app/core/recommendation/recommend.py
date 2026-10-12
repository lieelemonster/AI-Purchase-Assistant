import asyncio
import hashlib
import sqlite3
import time
from datetime import datetime, timezone
from typing import List

from pydantic import BaseModel, ConfigDict, Field

from app.adapters.model.base import ModelGateway, ModelGatewayError
from app.catalog.library import LibraryProduct, budget_bounds_yuan, filter_by_brand, filter_candidates, load_products
from app.config.settings import RuntimeConfig
from app.core.needs.normalize import normalize_needs
from app.core.recommendation.assemble import build_comparison
from app.core.recommendation.attribute_match import rank_by_attributes
from app.core.verification.catalog_match import CatalogLike
from app.core.verification.catalog_policies import result_status
from app.core.usage import current_usage, format_usage, start_usage
from app.core.verification.evidence_set import PageReaderLike
from app.schemas.evidence import EvidenceDocument, PriceFact, VerifiedFact
from app.schemas.need import NeedProfile, OptionAnswer
from app.schemas.result import EvidenceSource, Reason, RecommendationItem, RecommendationResult


class RecommendRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    request_id: str = Field(min_length=1)
    category_id: str
    option_answers: List[OptionAnswer] = []
    free_text: str = ""
    follow_up_round: int = 0


def _empty(request_id: str, status: str, **extra) -> RecommendationResult:
    return RecommendationResult(request_id=request_id, status=status, checked_at=datetime.now(timezone.utc), **extra)


def _http_url(raw: str) -> str:
    for part in raw.replace("；", ";").split(";"):
        text = part.strip()
        if text.startswith("http://") or text.startswith("https://"):
            return text
    return ""


def _fill(index: int, product: LibraryProduct, reason: str, notes: str, need: NeedProfile):
    candidate_id = f"c{index}"
    evidence_id = f"e{index}"
    lines = [f"{field}：{value}" for field, value in product.specs.items()]
    if product.price_yuan is not None:
        lines.append(f"参考价：{product.price_yuan}")
    text = "\n".join(lines)
    url = _http_url(product.source_url) or f"catalog://{product.product_id}"
    document = EvidenceDocument(
        evidence_id=evidence_id,
        url=url,
        final_url=url,
        title=product.name,
        fetched_at=datetime.now(timezone.utc),
        fetch_status="ok",
        content_hash=hashlib.sha256(text.encode("utf-8")).hexdigest(),
        text=text,
    )
    facts = [
        VerifiedFact(
            fact_id=f"f{index}{offset:02d}",
            candidate_id=candidate_id,
            field=field,
            value=value,
            evidence_id=evidence_id,
            excerpt=value,
            status="supported",
        )
        for offset, (field, value) in enumerate(product.specs.items(), start=1)
    ]
    if product.price_yuan is None:
        price = PriceFact(
            candidate_id=candidate_id,
            status="unknown",
            price_basis="unknown",
            conditions=["参考价未确认"],
        )
    else:
        price = PriceFact(
            candidate_id=candidate_id,
            amount_minor=product.price_yuan * 100,
            minor_unit_digits=2,
            currency="CNY",
            region="CN",
            price_basis="catalog_reference",
            conditions=["参考价，只比较数字，不含配件、蜂窝和国补"],
            evidence_id=evidence_id,
            excerpt=f"参考价：{product.price_yuan}",
            status="supported",
        )
    limitations = []
    if product.price_yuan is None:
        limitations.append("参考价未确认")
    if index == 1 and notes:
        limitations.append(notes)
    item = RecommendationItem(
        candidate_id=candidate_id,
        name=product.name,
        facts=facts,
        price=price,
        reasons=[Reason(
            need_refs=[need.requirements[0].requirement_id] if need.requirements else ["unknown:budget"],
            conclusion_type="judgment",
            text=reason,
            limitations=limitations,
        )],
    )
    source = EvidenceSource(
        evidence_id=evidence_id,
        url=url,
        title=product.name,
        fetched_at=document.fetched_at,
        source_name="本地产品库",
    )
    return item, source


async def _recommend(
    request: RecommendRequest,
    *,
    model: ModelGateway,
    catalog: CatalogLike,
    reader: PageReaderLike,
    config: RuntimeConfig,
) -> RecommendationResult:
    del catalog, reader
    usage = current_usage()
    started = time.perf_counter()

    def mark(name: str) -> None:
        nonlocal started
        if usage is not None:
            usage.stages_ms[name] = int((time.perf_counter() - started) * 1000)
        started = time.perf_counter()

    need = await normalize_needs(request.category_id, request.option_answers, request.free_text, model)
    mark("需求")

    try:
        products = load_products(config.catalog_db_path, request.category_id)
    except sqlite3.Error:
        return _empty(request.request_id, "failed")
    floor, ceiling = budget_bounds_yuan(need)
    candidates = filter_by_brand(filter_candidates(products, floor, ceiling), need.free_text, products)
    mark("候选")
    if not candidates:
        return _empty(request.request_id, "insufficient_candidates")

    chosen = rank_by_attributes(request.category_id, need.option_answers, need.free_text, candidates)
    mark("排序")
    if not chosen:
        return _empty(request.request_id, "insufficient_candidates")

    by_id = {product.product_id: product for product in candidates}
    items = []
    sources = []
    for index, choice in enumerate(chosen, start=1):
        item, source = _fill(index, by_id[choice.product_id], choice.reason, "", need)
        items.append(item)
        sources.append(source)
    prices = [item.price for item in items]
    return RecommendationResult(
        request_id=request.request_id,
        status=result_status(len(items)),
        primary=items[0],
        alternatives=items[1:],
        comparison=build_comparison(items[0].price, prices),
        evidence_sources=sources,
        checked_at=datetime.now(timezone.utc),
    )


async def recommend(
    request: RecommendRequest,
    *,
    model: ModelGateway,
    catalog: CatalogLike,
    reader: PageReaderLike,
    config: RuntimeConfig,
) -> RecommendationResult:
    usage = start_usage()
    try:
        job = _recommend(request, model=model, catalog=catalog, reader=reader, config=config)
        if config.request_timeout_s is None:
            return await job
        return await asyncio.wait_for(job, timeout=config.request_timeout_s)
    except asyncio.TimeoutError:
        return _empty(request.request_id, "timeout")
    except ModelGatewayError:
        return _empty(request.request_id, "service_unavailable")
    finally:
        print(format_usage(usage))

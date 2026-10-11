import asyncio
import itertools
from datetime import datetime, timezone
from typing import Dict, List

from pydantic import BaseModel, ConfigDict, Field

from app.adapters.model.base import ModelGateway, ModelGatewayError
from app.config.field_tables import load_field_table
from app.config.settings import RuntimeConfig
from app.core.candidates.generate import propose_candidates
from app.core.needs.follow_up import plan_follow_up
from app.core.needs.normalize import normalize_needs
from app.core.recommendation.assemble import assemble_result
from app.core.recommendation.hard_constraints import check_hard_constraints
from app.core.recommendation.ranking import RankingError, rank_and_explain
from app.core.recommendation.reason_fill import ReasonFillError, fill_reasons
from app.core.verification.budget import SearchBudget
from app.core.verification.catalog_evidence import Throttle, ThrottledReader, collect_catalog_evidence
from app.core.verification.catalog_identity import verify_catalog_identity
from app.core.verification.catalog_match import CatalogLike
from app.core.verification.catalog_policies import dedupe_same_model, discover_candidates, match_with_retry, result_status
from app.core.verification.conflicts import mark_field_conflicts
from app.core.verification.evidence_set import PageReaderLike
from app.core.verification.price_parsing import parse_reference_price
from app.core.verification.spec_parsing import parse_spec_page
from app.schemas.candidate import Candidate
from app.schemas.evidence import EvidenceDocument, PriceFact, VerifiedFact
from app.schemas.need import OptionAnswer
from app.schemas.result import RecommendationResult, UnresolvedItem


class RecommendRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    request_id: str = Field(min_length=1)
    category_id: str
    option_answers: List[OptionAnswer] = []
    free_text: str = ""
    follow_up_round: int = 0


def _empty(request_id: str, status: str, **extra) -> RecommendationResult:
    return RecommendationResult(request_id=request_id, status=status, checked_at=datetime.now(timezone.utc), **extra)


async def _recommend(
    request: RecommendRequest,
    *,
    model: ModelGateway,
    catalog: CatalogLike,
    reader: PageReaderLike,
    config: RuntimeConfig,
) -> RecommendationResult:
    need = await normalize_needs(request.category_id, request.option_answers, request.free_text, model)
    follow_up = await plan_follow_up(need, request.follow_up_round, model)
    if follow_up is not None:
        return _empty(request.request_id, "need_more_info", follow_up=follow_up)

    proposed = await propose_candidates(need, model, config.max_candidates)
    matches = await match_with_retry(proposed, need, model, catalog, SearchBudget(config.max_search_calls))
    matches = dedupe_same_model(matches)
    extra_candidates, extra_matches = discover_candidates(proposed, matches)
    candidates = proposed + extra_candidates
    matches = matches + extra_matches
    by_id = {candidate.candidate_id: candidate for candidate in candidates}

    evidence = await collect_catalog_evidence(
        matches,
        ThrottledReader(reader, Throttle(config.source_min_interval_s)),
        max_pages=config.max_pages,
        concurrency=config.concurrency,
    )
    table = load_field_table(request.category_id)
    fact_ids = itertools.count(1)
    facts: Dict[str, List[VerifiedFact]] = {}
    prices: Dict[str, PriceFact] = {}
    unresolved: List[UnresolvedItem] = []
    usable: List[Candidate] = []

    for match in matches:
        pages = evidence.pages.get(match.candidate_id)
        candidate = by_id.get(match.candidate_id)
        if pages is None or candidate is None or match.hit is None:
            continue
        parsed = parse_spec_page(
            evidence.documents[pages.detail_evidence_id],
            table,
            match.candidate_id,
            lambda: f"f{next(fact_ids)}",
        )
        if parsed.status != "ok":
            continue
        checked_facts, conflicts = mark_field_conflicts(parsed.facts)
        unresolved.extend(conflicts)
        identity = verify_catalog_identity(match, pages, evidence.documents, checked_facts)
        if identity.status != "ok":
            continue
        price = parse_reference_price(
            evidence.documents[pages.price_evidence_id],
            match.candidate_id,
            match.hit.name,
            identity.multi_config,
        )
        facts[match.candidate_id] = identity.facts
        prices[match.candidate_id] = price
        usable.append(candidate)

    constraints = check_hard_constraints(need, prices)
    usable = [candidate for candidate in usable if constraints[candidate.candidate_id].status != "excluded"]
    if not usable:
        return _empty(request.request_id, "insufficient_candidates", unresolved_items=unresolved)

    ranked = await rank_and_explain(
        need,
        usable,
        facts,
        prices,
        model,
        max_attempts=config.max_retries + 1,
    )
    names = [candidate.model_hint for candidate in usable]
    filled = {
        candidate.candidate_id: fill_reasons(
            ranked.reasons.get(candidate.candidate_id, []),
            candidate=candidate,
            facts=facts.get(candidate.candidate_id, []),
            prices=prices,
            names=names,
        )
        for candidate in usable
    }
    ordered = [by_id[candidate_id] for candidate_id in ranked.order]
    shown_count = min(3, len(ordered))
    return assemble_result(
        request_id=request.request_id,
        status=result_status(shown_count),
        ordered=ordered[:shown_count],
        facts=facts,
        prices=prices,
        reasons=filled,
        documents=evidence.documents,
        checked_at=datetime.now(timezone.utc),
    ).model_copy(update={"unresolved_items": unresolved})


async def recommend(
    request: RecommendRequest,
    *,
    model: ModelGateway,
    catalog: CatalogLike,
    reader: PageReaderLike,
    config: RuntimeConfig,
) -> RecommendationResult:
    try:
        return await asyncio.wait_for(
            _recommend(request, model=model, catalog=catalog, reader=reader, config=config),
            timeout=config.request_timeout_s,
        )
    except asyncio.TimeoutError:
        return _empty(request.request_id, "timeout")
    except ModelGatewayError:
        return _empty(request.request_id, "service_unavailable")
    except (RankingError, ReasonFillError):
        return _empty(request.request_id, "failed")

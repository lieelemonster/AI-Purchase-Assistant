from typing import Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

from app.adapters.model.base import ModelGateway
from app.adapters.search.base import SearchGateway, SearchGatewayError
from app.core.verification.official_sources import (
    ChannelCheck,
    ChannelType,
    check_channel,
    find_brand,
    load_official_channels,
    search_sites,
)
from app.schemas.candidate import Candidate
from app.schemas.need import NeedProfile

QUERY_TASK = (
    "为每个候选产品写一条中文搜索词，用来在品牌官网或官方旗舰店里找到该型号的参数页和价格页。"
    "搜索词包含品牌、型号、代际和需要核实的配置，不超过 40 个字；不要写网站名，也不要写价格。"
)
MAX_QUERY_LENGTH = 100
SEARCH_LANGUAGE = "zh"
HITS_PER_SEARCH = 10


class SearchBudget:
    """一次推荐请求内共享的搜索次数上限。"""

    def __init__(self, max_calls: int):
        self.max_calls = max_calls
        self.used = 0

    def take(self) -> bool:
        if self.used >= self.max_calls:
            return False
        self.used += 1
        return True


class SourceHit(BaseModel):
    url: str
    title: str = ""
    check: ChannelCheck


class SkippedHit(BaseModel):
    url: str
    reason: str


class CandidateSources(BaseModel):
    candidate_id: str
    status: Literal["found", "unknown"]
    reason: Optional[str] = None
    hits: List[SourceHit] = []
    skipped: List[SkippedHit] = []
    searched_channels: List[ChannelType] = []
    errors: List[str] = []


class _Query(BaseModel):
    model_config = ConfigDict(extra="ignore")

    candidate_id: str
    query: str = Field(min_length=1)


class _Queries(BaseModel):
    model_config = ConfigDict(extra="ignore")

    queries: List[_Query] = []


def _fallback_query(candidate: Candidate) -> str:
    parts = [candidate.brand_hint, candidate.model_hint, candidate.generation_hint, candidate.variant_hint]
    return " ".join(p for p in parts if p)


async def write_queries(candidates: List[Candidate], need: NeedProfile, model: ModelGateway) -> Dict[str, str]:
    """搜索词交给模型写；模型漏写或写了不存在的候选时，用候选线索拼出搜索词。"""
    result = await model.generate_json(
        task=QUERY_TASK,
        payload={"category_id": need.category_id, "candidates": [c.model_dump() for c in candidates]},
        output_schema=_Queries,
    )
    written = {q.candidate_id: q.query.strip()[:MAX_QUERY_LENGTH] for q in result.queries}
    return {c.candidate_id: written.get(c.candidate_id) or _fallback_query(c) for c in candidates}


async def find_sources(
    candidate: Candidate,
    query: str,
    search: SearchGateway,
    budget: SearchBudget,
    region: Optional[str],
) -> CandidateSources:
    """D-08：按官网、京东、天猫的顺序搜索；某一渠道已找到官方页面就不再搜索后面的渠道。"""
    brand = find_brand(candidate.brand_hint)
    if brand is None:
        return CandidateSources(candidate_id=candidate.candidate_id, status="unknown", reason="brand_not_in_channel_list")

    priority = load_official_channels().channel_priority
    result = CandidateSources(candidate_id=candidate.candidate_id, status="unknown")
    seen = set()
    for channel in sorted(priority, key=priority.get):
        sites = search_sites(brand, channel)
        if not sites:
            continue
        if not budget.take():
            result.reason = "search_limit"
            break
        result.searched_channels.append(channel)
        try:
            hits = await search.search(query, region=region, language=SEARCH_LANGUAGE,
                                       limit=HITS_PER_SEARCH, include_sites=sites)
        except SearchGatewayError as e:
            result.errors.append(f"{channel}: {e.kind}")
            continue
        for hit in hits:
            if hit.url in seen:
                continue
            seen.add(hit.url)
            check = check_channel(hit.url, candidate.brand_hint)
            if check.status == "unknown":
                result.skipped.append(SkippedHit(url=hit.url, reason="not_official_channel"))
            else:
                result.hits.append(SourceHit(url=hit.url, title=hit.title, check=check))
        if result.hits:
            break

    result.hits.sort(key=lambda h: h.check.priority)
    if result.hits:
        result.status, result.reason = "found", None
    elif result.reason is None:
        result.reason = "search_unavailable" if result.errors else "no_official_page"
    return result

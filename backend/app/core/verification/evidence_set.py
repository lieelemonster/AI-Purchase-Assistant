import asyncio
from typing import Dict, List, Protocol, Tuple

from pydantic import BaseModel

from app.core.verification.official_sources import check_channel, links_confirm_store
from app.core.verification.source_search import CandidateSources, SourceHit
from app.schemas.candidate import Candidate
from app.schemas.evidence import EvidenceDocument


class PageReaderLike(Protocol):
    async def read(self, url: str, evidence_id: str) -> EvidenceDocument: ...


class SkippedPage(BaseModel):
    candidate_id: str
    url: str
    reason: str


class EvidenceSet(BaseModel):
    """一次推荐请求内读取到的全部页面；不跨请求保存。"""

    documents: Dict[str, EvidenceDocument] = {}
    by_candidate: Dict[str, List[str]] = {}
    skipped: List[SkippedPage] = []


def _round_robin(sources: List[CandidateSources], max_pages: int) -> List[Tuple[str, SourceHit]]:
    """每个候选轮流取一个页面，避免页面上限被排在前面的候选用完。"""
    picked: List[Tuple[str, SourceHit]] = []
    depth = 0
    while len(picked) < max_pages and any(depth < len(s.hits) for s in sources):
        for s in sources:
            if depth < len(s.hits) and len(picked) < max_pages:
                picked.append((s.candidate_id, s.hits[depth]))
        depth += 1
    return picked


def _official_reason(doc: EvidenceDocument, brand_hint: str) -> str:
    """读取成功的页面按最终地址再判断一次渠道；返回空字符串表示属于官方渠道。"""
    check = check_channel(doc.final_url or doc.url, brand_hint)
    if check.status == "official":
        return ""
    if check.status == "store_check_required":
        return "" if links_confirm_store(doc.links, check) else "not_official_store"
    return "redirected_off_official"


async def collect_evidence(
    candidates: List[Candidate],
    sources: List[CandidateSources],
    reader: PageReaderLike,
    *,
    max_pages: int,
    concurrency: int,
) -> EvidenceSet:
    brands = {c.candidate_id: c.brand_hint for c in candidates}
    picked = _round_robin(sources, max_pages)

    urls = list(dict.fromkeys(hit.url for _, hit in picked))
    evidence_ids = {url: f"e{i}" for i, url in enumerate(urls, start=1)}
    semaphore = asyncio.Semaphore(concurrency)

    async def read(url: str) -> EvidenceDocument:
        async with semaphore:
            return await reader.read(url, evidence_ids[url])

    documents = dict(zip(urls, await asyncio.gather(*(read(u) for u in urls))))

    result = EvidenceSet()
    for candidate_id, hit in picked:
        doc = documents[hit.url]
        if doc.fetch_status == "ok":
            reason = _official_reason(doc, brands[candidate_id])
            if reason:
                result.skipped.append(SkippedPage(candidate_id=candidate_id, url=hit.url, reason=reason))
                continue
        result.documents[doc.evidence_id] = doc
        result.by_candidate.setdefault(candidate_id, []).append(doc.evidence_id)
    return result

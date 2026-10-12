import asyncio
import time
from typing import Awaitable, Callable, Dict, List
from urllib.parse import urlsplit

from pydantic import BaseModel

from app.adapters.catalog.pconline import PRODUCT_HOST, PRODUCT_PATH
from app.core.verification.catalog_match import CatalogMatch
from app.core.verification.evidence_set import PageReaderLike, SkippedPage
from app.schemas.evidence import EvidenceDocument

PAGES_PER_MATCH = 2


class Throttle:
    """控制对同一网站的请求节奏：两次请求开始之间至少间隔 min_interval_s 秒。"""

    def __init__(
        self,
        min_interval_s: float,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ):
        self._min_interval_s = min_interval_s
        self._clock = clock
        self._sleep = sleep
        self._lock = None
        self._last_start = None

    async def wait(self) -> None:
        if self._lock is None:
            self._lock = asyncio.Lock()
        async with self._lock:
            if self._last_start is not None:
                remaining = self._min_interval_s - (self._clock() - self._last_start)
                if remaining > 0:
                    await self._sleep(remaining)
            self._last_start = self._clock()


class ThrottledReader:
    """给网页读取加上请求节奏控制；放在缓存之下，命中缓存时不必等待。站内搜索和读页面共用同一个节奏。"""

    def __init__(self, reader, throttle: Throttle):
        self._reader = reader
        self._throttle = throttle

    async def read(self, url: str, evidence_id: str) -> EvidenceDocument:
        await self._throttle.wait()
        return await self._reader.read(url, evidence_id)

    async def fetch(self, url: str):
        await self._throttle.wait()
        return await self._reader.fetch(url)


class CatalogPages(BaseModel):
    candidate_id: str
    product_id: str
    detail_evidence_id: str
    price_evidence_id: str


class CatalogEvidenceSet(BaseModel):
    """一次推荐请求内读取到的太平洋参数页和报价页；不跨请求保存。"""

    documents: Dict[str, EvidenceDocument] = {}
    pages: Dict[str, CatalogPages] = {}
    skipped: List[SkippedPage] = []


def _stays_on_product_page(doc: EvidenceDocument, product_id: str) -> bool:
    parts = urlsplit(doc.final_url or doc.url)
    match = PRODUCT_PATH.match(parts.path.replace("_detail.html", ".html").replace("_price.html", ".html"))
    return parts.hostname == PRODUCT_HOST and match is not None and match.group(3) == product_id


async def collect_catalog_evidence(
    matches: List[CatalogMatch],
    reader: PageReaderLike,
    *,
    max_pages: int,
    concurrency: int,
) -> CatalogEvidenceSet:
    """先读产品首页取价格，再读参数页。读取失败的保留为 unavailable，跳出太平洋配置页的跳过。"""
    matched = [m for m in matches if m.status == "matched" and m.hit is not None][: max_pages // PAGES_PER_MATCH]
    home_plan = []
    detail_plan = []
    for i, match in enumerate(matched):
        home_plan.append((match, "price", match.hit.url, f"e{2 * i + 1}"))
        detail_plan.append((match, "detail", match.hit.detail_url, f"e{2 * i + 2}"))

    semaphore = asyncio.Semaphore(concurrency)

    async def read(url: str, evidence_id: str) -> EvidenceDocument:
        async with semaphore:
            return await reader.read(url, evidence_id)

    async def read_plan(plan):
        return await asyncio.gather(*(read(url, eid) for _, _, url, eid in plan))

    home_docs = await read_plan(home_plan)
    detail_docs = await read_plan(detail_plan)
    plan = home_plan + detail_plan
    documents = list(home_docs) + list(detail_docs)

    result = CatalogEvidenceSet()
    by_candidate: Dict[str, Dict[str, str]] = {}
    for (match, kind, url, _), doc in zip(plan, documents):
        if doc.fetch_status == "ok" and not _stays_on_product_page(doc, match.hit.product_id):
            result.skipped.append(SkippedPage(candidate_id=match.candidate_id, url=url, reason="redirected_off_source"))
            continue
        result.documents[doc.evidence_id] = doc
        by_candidate.setdefault(match.candidate_id, {})[kind] = doc.evidence_id

    for match in matched:
        kinds = by_candidate.get(match.candidate_id, {})
        if "detail" in kinds and "price" in kinds:
            result.pages[match.candidate_id] = CatalogPages(
                candidate_id=match.candidate_id, product_id=match.hit.product_id,
                detail_evidence_id=kinds["detail"], price_evidence_id=kinds["price"],
            )
    return result

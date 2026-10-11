from datetime import datetime, timedelta, timezone
from typing import Callable, Dict, Tuple

from app.core.verification.evidence_set import PageReaderLike
from app.schemas.evidence import EvidenceDocument

Clock = Callable[[], datetime]


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class CachedPageReader:
    """D-05：只缓存读取成功的公开页面 24 小时，放在进程内存里，重启即清空。

    命中缓存时返回的证据保留当初实际读取的访问时间，只换成本次请求分配的 evidence_id。
    """

    def __init__(self, reader: PageReaderLike, ttl: timedelta = timedelta(hours=24), clock: Clock = utc_now):
        self._reader = reader
        self._ttl = ttl
        self._clock = clock
        self._pages: Dict[str, Tuple[datetime, EvidenceDocument]] = {}
        self.hits = 0
        self.misses = 0

    async def read(self, url: str, evidence_id: str) -> EvidenceDocument:
        now = self._clock()
        cached = self._pages.get(url)
        if cached and now - cached[0] < self._ttl:
            self.hits += 1
            return cached[1].model_copy(update={"evidence_id": evidence_id})
        self.misses += 1
        doc = await self._reader.read(url, evidence_id)
        if doc.fetch_status == "ok":
            self._pages[url] = (now, doc)
        else:
            self._pages.pop(url, None)
        return doc

    def cached_urls(self):
        return list(self._pages)

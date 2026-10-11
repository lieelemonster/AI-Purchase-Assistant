import asyncio
from datetime import datetime, timedelta, timezone

from app.adapters.pages.cache import CachedPageReader
from app.schemas.evidence import EvidenceDocument

URL = "https://www.vmall.com/product/1.html"
START = datetime(2026, 10, 11, 12, 0, tzinfo=timezone.utc)


class Clock:
    def __init__(self):
        self.now = START

    def __call__(self):
        return self.now


class CountingReader:
    def __init__(self, fail_first=False):
        self.calls = 0
        self.fail_first = fail_first

    async def read(self, url, evidence_id):
        self.calls += 1
        fetched_at = START + timedelta(minutes=self.calls)
        if self.fail_first and self.calls == 1:
            return EvidenceDocument(evidence_id=evidence_id, url=url, fetched_at=fetched_at,
                                    fetch_status="unavailable", failure_reason="timeout")
        return EvidenceDocument(evidence_id=evidence_id, url=url, final_url=url, fetched_at=fetched_at,
                                fetch_status="ok", content_hash="h", text="页面")


def read(cache, evidence_id="e1"):
    return asyncio.run(cache.read(URL, evidence_id))


def test_second_read_within_24_hours_uses_the_cache():
    reader, clock = CountingReader(), Clock()
    cache = CachedPageReader(reader, clock=clock)
    first = read(cache, "e1")
    clock.now = START + timedelta(hours=23)
    second = read(cache, "e7")
    assert reader.calls == 1
    assert second.fetched_at == first.fetched_at
    assert second.evidence_id == "e7"
    assert (cache.hits, cache.misses) == (1, 1)


def test_read_after_24_hours_fetches_again():
    reader, clock = CountingReader(), Clock()
    cache = CachedPageReader(reader, clock=clock)
    read(cache)
    clock.now = START + timedelta(hours=24)
    read(cache)
    assert reader.calls == 2


def test_failed_reads_are_not_cached():
    reader = CountingReader(fail_first=True)
    cache = CachedPageReader(reader, clock=Clock())
    assert read(cache).fetch_status == "unavailable"
    assert read(cache).fetch_status == "ok"
    assert reader.calls == 2


def test_cache_only_holds_page_reads():
    cache = CachedPageReader(CountingReader(), clock=Clock())
    read(cache)
    assert cache.cached_urls() == [URL]
    assert all(isinstance(doc, EvidenceDocument) for _, doc in cache._pages.values())

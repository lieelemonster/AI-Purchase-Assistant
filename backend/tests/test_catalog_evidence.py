import asyncio
from datetime import datetime, timezone

from app.adapters.catalog.pconline import CatalogHit
from app.core.verification.catalog_evidence import Throttle, ThrottledReader, collect_catalog_evidence
from app.core.verification.catalog_match import CatalogMatch
from app.schemas.evidence import EvidenceDocument

NOW = datetime(2026, 10, 11, tzinfo=timezone.utc)


def match(cid, product_id, status="matched"):
    hit = CatalogHit(product_id=product_id, name=f"示例本 {product_id}",
                     url=f"https://product.pconline.com.cn/notebook/demo/{product_id}.html",
                     category_dir="notebook", brand_dir="demo", discontinued=False)
    return CatalogMatch(candidate_id=cid, status=status, hit=hit if status == "matched" else None)


class FakeReader:
    def __init__(self, pages=None, delay=0.0):
        self.pages = pages or {}
        self.delay = delay
        self.urls = []
        self.active = 0
        self.max_active = 0

    async def read(self, url, evidence_id):
        self.urls.append(url)
        self.active += 1
        self.max_active = max(self.max_active, self.active)
        await asyncio.sleep(self.delay)
        self.active -= 1
        page = self.pages.get(url, {})
        if page.get("fail"):
            return EvidenceDocument(evidence_id=evidence_id, url=url, fetched_at=NOW,
                                    fetch_status="unavailable", failure_reason=page["fail"])
        return EvidenceDocument(evidence_id=evidence_id, url=url, final_url=page.get("final_url", url),
                                fetched_at=NOW, fetch_status="ok", content_hash="h", text=page.get("text", url))


def collect(matches, reader, max_pages=12, concurrency=4):
    return asyncio.run(collect_catalog_evidence(matches, reader, max_pages=max_pages, concurrency=concurrency))


def test_each_match_reads_its_detail_and_price_pages():
    reader = FakeReader()
    result = collect([match("c1", "100")], reader)
    assert reader.urls == ["https://product.pconline.com.cn/notebook/demo/100.html",
                           "https://product.pconline.com.cn/notebook/demo/100_detail.html"]
    pages = result.pages["c1"]
    assert (pages.product_id, pages.detail_evidence_id, pages.price_evidence_id) == ("100", "e2", "e1")


def test_unmatched_candidates_are_not_read():
    reader = FakeReader()
    collect([match("c1", "100", status="unknown"), match("c2", "200")], reader)
    assert reader.urls
    assert all("/200" in u for u in reader.urls)


def test_redirect_off_the_product_page_is_skipped():
    detail = "https://product.pconline.com.cn/notebook/demo/100_detail.html"
    result = collect([match("c1", "100")], FakeReader({detail: {"final_url": "https://evil.example.com/"}}))
    assert [(s.url, s.reason) for s in result.skipped] == [(detail, "redirected_off_source")]
    assert "c1" not in result.pages


def test_redirect_to_another_product_is_skipped():
    detail = "https://product.pconline.com.cn/notebook/demo/100_detail.html"
    other = "https://product.pconline.com.cn/notebook/demo/999_detail.html"
    result = collect([match("c1", "100")], FakeReader({detail: {"final_url": other}}))
    assert result.skipped[0].reason == "redirected_off_source"


def test_failed_read_is_kept_as_unavailable():
    home = "https://product.pconline.com.cn/notebook/demo/100.html"
    result = collect([match("c1", "100")], FakeReader({home: {"fail": "timeout"}}))
    assert result.documents[result.pages["c1"].price_evidence_id].fetch_status == "unavailable"


def test_page_limit_counts_two_pages_per_match():
    reader = FakeReader()
    result = collect([match(f"c{i}", str(i)) for i in range(1, 5)], reader, max_pages=5)
    assert sorted(result.pages) == ["c1", "c2"]
    assert len(reader.urls) == 4


def test_concurrency_limit_is_respected():
    reader = FakeReader(delay=0.02)
    collect([match(f"c{i}", str(i)) for i in range(1, 4)], reader, concurrency=2)
    assert reader.max_active == 2


def test_two_requests_do_not_mix_evidence():
    async def both():
        a = collect_catalog_evidence([match("c1", "1")], FakeReader({"https://product.pconline.com.cn/notebook/demo/1.html": {"text": "A"}}),
                                     max_pages=4, concurrency=2)
        b = collect_catalog_evidence([match("c1", "2")], FakeReader({"https://product.pconline.com.cn/notebook/demo/2.html": {"text": "B"}}),
                                     max_pages=4, concurrency=2)
        return await asyncio.gather(a, b)

    first, second = asyncio.run(both())
    assert first.documents["e1"].text == "A"
    assert second.documents["e1"].text == "B"


def test_throttle_spaces_out_request_starts():
    now = [100.0]
    slept = []

    async def fake_sleep(seconds):
        slept.append(round(seconds, 3))
        now[0] += seconds

    throttle = Throttle(2.0, clock=lambda: now[0], sleep=fake_sleep)

    async def three():
        await throttle.wait()
        now[0] += 0.5
        await throttle.wait()
        await throttle.wait()

    asyncio.run(three())
    assert slept == [1.5, 2.0]


def test_cache_hits_skip_the_throttle():
    from datetime import timedelta

    from app.adapters.pages.cache import CachedPageReader

    waits = []

    class CountingThrottle(Throttle):
        async def wait(self):
            waits.append(1)

    url = "https://product.pconline.com.cn/notebook/demo/1_detail.html"
    reader = CachedPageReader(ThrottledReader(FakeReader(), CountingThrottle(2)), ttl=timedelta(hours=24))

    async def twice():
        await reader.read(url, "e1")
        await reader.read(url, "e2")

    asyncio.run(twice())
    assert len(waits) == 1

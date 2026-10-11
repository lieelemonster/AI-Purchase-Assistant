import asyncio
from datetime import datetime, timezone
from typing import Dict, List, Optional

from app.core.verification.evidence_set import collect_evidence
from app.core.verification.official_sources import check_channel
from app.core.verification.source_search import CandidateSources, SourceHit
from app.schemas.candidate import Candidate
from app.schemas.evidence import EvidenceDocument

NOW = datetime(2026, 10, 11, tzinfo=timezone.utc)


class FakeReader:
    def __init__(self, pages: Optional[Dict[str, dict]] = None, delay: float = 0):
        self.pages = pages or {}
        self.delay = delay
        self.active = 0
        self.max_active = 0
        self.read_urls: List[str] = []

    async def read(self, url, evidence_id):
        self.active += 1
        self.max_active = max(self.max_active, self.active)
        self.read_urls.append(url)
        await asyncio.sleep(self.delay)
        self.active -= 1
        page = self.pages.get(url, {})
        if page.get("fail"):
            return EvidenceDocument(evidence_id=evidence_id, url=url, fetched_at=NOW,
                                    fetch_status="unavailable", failure_reason=page["fail"])
        return EvidenceDocument(evidence_id=evidence_id, url=url, final_url=page.get("final_url", url),
                                fetched_at=NOW, fetch_status="ok", content_hash="h",
                                text=page.get("text", url), links=page.get("links", []))


def candidate(candidate_id, brand="华为"):
    return Candidate(candidate_id=candidate_id, brand_hint=brand, model_hint="型号", origin="model")


def sources(candidate_id, urls, brand="华为"):
    hits = [SourceHit(url=u, check=check_channel(u, brand)) for u in urls]
    return CandidateSources(candidate_id=candidate_id, status="found", hits=hits)


def vmall(n):
    return f"https://www.vmall.com/product/{n}.html"


def collect(cands, srcs, reader, max_pages=10, concurrency=4):
    return asyncio.run(collect_evidence(cands, srcs, reader, max_pages=max_pages, concurrency=concurrency))


def test_concurrent_reads_never_exceed_the_limit():
    reader = FakeReader(delay=0.02)
    result = collect([candidate("c1")], [sources("c1", [vmall(i) for i in range(5)])], reader, concurrency=2)
    assert reader.max_active == 2
    assert result.by_candidate["c1"] == ["e1", "e2", "e3", "e4", "e5"]


def test_two_requests_running_together_do_not_mix_evidence():
    async def both():
        a = collect_evidence([candidate("c1")], [sources("c1", [vmall("a")])], FakeReader({vmall("a"): {"text": "A"}}, 0.01),
                             max_pages=5, concurrency=2)
        b = collect_evidence([candidate("c1")], [sources("c1", [vmall("b")])], FakeReader({vmall("b"): {"text": "B"}}, 0.01),
                             max_pages=5, concurrency=2)
        return await asyncio.gather(a, b)

    first, second = asyncio.run(both())
    assert [d.text for d in first.documents.values()] == ["A"]
    assert [d.text for d in second.documents.values()] == ["B"]


def test_failed_read_is_kept_as_unavailable():
    result = collect([candidate("c1")], [sources("c1", [vmall(1)])], FakeReader({vmall(1): {"fail": "timeout"}}))
    doc = result.documents["e1"]
    assert (doc.fetch_status, doc.failure_reason) == ("unavailable", "timeout")
    assert result.by_candidate["c1"] == ["e1"]


def test_jd_item_page_is_kept_only_with_a_link_to_the_official_store():
    good, bad = "https://item.jd.com/1.html", "https://item.jd.com/2.html"
    reader = FakeReader({good: {"links": ["https://huawei.jd.com/"]}, bad: {"links": ["https://mall.jd.com/index-999.html"]}})
    result = collect([candidate("c1")], [sources("c1", [good, bad])], reader)
    assert [d.url for d in result.documents.values()] == [good]
    assert [(s.url, s.reason) for s in result.skipped] == [(bad, "not_official_store")]


def test_page_redirected_off_the_official_site_is_skipped():
    reader = FakeReader({vmall(1): {"final_url": "https://evil.example.com/"}})
    result = collect([candidate("c1")], [sources("c1", [vmall(1)])], reader)
    assert result.documents == {}
    assert result.skipped[0].reason == "redirected_off_official"


def test_page_limit_is_shared_fairly_between_candidates():
    srcs = [sources("c1", [vmall(f"a{i}") for i in range(3)]), sources("c2", [vmall(f"b{i}") for i in range(3)])]
    result = collect([candidate("c1"), candidate("c2")], srcs, FakeReader(), max_pages=4)
    assert {k: len(v) for k, v in result.by_candidate.items()} == {"c1": 2, "c2": 2}


def test_same_url_for_two_candidates_is_read_once():
    reader = FakeReader()
    result = collect([candidate("c1"), candidate("c2")], [sources("c1", [vmall(1)]), sources("c2", [vmall(1)])], reader)
    assert reader.read_urls == [vmall(1)]
    assert result.by_candidate == {"c1": ["e1"], "c2": ["e1"]}

import hashlib
from datetime import datetime, timezone
from typing import List, Optional, Tuple
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup

from app.adapters.pages.url_safety import Resolver, UnsafeUrlError, check_url, system_resolve
from app.schemas.evidence import EvidenceDocument

HTML_TYPES = {"text/html", "application/xhtml+xml"}
USER_AGENT = "AIBuyAssistant/0.1 (+official product page reader)"
MAX_LINKS = 500


class _FetchFailed(Exception):
    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


class PageReader:
    def __init__(
        self,
        *,
        max_page_bytes: int,
        timeout_s: float,
        max_redirects: int = 5,
        resolve: Resolver = system_resolve,
        transport: Optional[httpx.AsyncBaseTransport] = None,
    ):
        self._max_page_bytes = max_page_bytes
        self._timeout_s = timeout_s
        self._max_redirects = max_redirects
        self._resolve = resolve
        self._transport = transport

    async def read(self, url: str, evidence_id: str) -> EvidenceDocument:
        fetched_at = datetime.now(timezone.utc)
        try:
            final_url, body, charset = await self._fetch(url)
        except _FetchFailed as e:
            return EvidenceDocument(evidence_id=evidence_id, url=url, fetched_at=fetched_at,
                                    fetch_status="unavailable", failure_reason=e.reason)
        title, text, links = extract_page(body, charset, base_url=final_url)
        return EvidenceDocument(
            evidence_id=evidence_id,
            url=url,
            final_url=final_url,
            title=title,
            fetched_at=fetched_at,
            fetch_status="ok",
            content_hash=hashlib.sha256(body).hexdigest(),
            text=text,
            links=links,
        )

    async def _fetch(self, url: str) -> Tuple[str, bytes, Optional[str]]:
        current = url
        async with httpx.AsyncClient(
            transport=self._transport,
            timeout=self._timeout_s,
            follow_redirects=False,
            headers={"User-Agent": USER_AGENT},
        ) as client:
            for hop in range(self._max_redirects + 1):
                await self._check(current, is_redirect=hop > 0)
                try:
                    async with client.stream("GET", current) as resp:
                        if resp.is_redirect:
                            current = urljoin(current, resp.headers["location"])
                            continue
                        return current, await self._read_body(resp), resp.charset_encoding
                except httpx.TimeoutException as e:
                    raise _FetchFailed("timeout") from e
                except httpx.HTTPError as e:
                    raise _FetchFailed("network") from e
        raise _FetchFailed("too_many_redirects")

    async def _check(self, url: str, *, is_redirect: bool) -> None:
        try:
            await check_url(url, resolve=self._resolve)
        except UnsafeUrlError as e:
            if e.reason == "dns_failed":
                raise _FetchFailed("dns_failed") from e
            raise _FetchFailed("unsafe_redirect" if is_redirect else "unsafe_url") from e

    async def _read_body(self, resp: httpx.Response) -> bytes:
        if resp.status_code >= 400:
            raise _FetchFailed(f"http_{resp.status_code}")
        content_type = resp.headers.get("content-type", "").split(";")[0].strip().lower()
        if content_type not in HTML_TYPES:
            raise _FetchFailed("not_html")
        declared = resp.headers.get("content-length")
        if declared and declared.isdigit() and int(declared) > self._max_page_bytes:
            raise _FetchFailed("too_large")
        body = bytearray()
        async for chunk in resp.aiter_bytes():
            body.extend(chunk)
            if len(body) > self._max_page_bytes:
                raise _FetchFailed("too_large")
        return bytes(body)


def extract_page(body: bytes, charset: Optional[str] = None, base_url: str = "") -> Tuple[Optional[str], str, List[str]]:
    """返回标题、正文和页面中的链接（已转为绝对地址，去重，最多 MAX_LINKS 条）。"""
    soup = BeautifulSoup(body, "html.parser", from_encoding=charset)
    title = soup.title.get_text(strip=True) if soup.title else None
    hrefs = (a.get("href", "").strip() for a in soup.find_all("a"))
    links = list(dict.fromkeys(urljoin(base_url, h) for h in hrefs if h and not h.startswith(("#", "javascript:"))))
    for tag in soup(["script", "style", "noscript", "template"]):
        tag.decompose()
    for row in soup.find_all("tr"):
        cells = [cell.get_text(" ", strip=True) for cell in row.find_all(["th", "td"])]
        row.replace_with(soup.new_string(" | ".join(c for c in cells if c)))
    lines = (" ".join(line.split()) for line in soup.get_text("\n").splitlines())
    return title or None, "\n".join(line for line in lines if line), links[:MAX_LINKS]

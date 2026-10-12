import asyncio
import hashlib
import re
from datetime import datetime, timezone
from typing import List, NamedTuple, Optional, Tuple
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup

from app.adapters.pages.url_safety import Resolver, UnsafeUrlError, check_url, system_resolve
from app.core.usage import add_page_read
from app.schemas.evidence import EvidenceDocument

HTML_TYPES = {"text/html", "application/xhtml+xml"}
USER_AGENT = "AIBuyAssistant/0.1 (+official product page reader)"
MAX_LINKS = 500


class FetchError(Exception):
    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


class FetchedPage(NamedTuple):
    final_url: str
    body: bytes
    charset: Optional[str]


class PageReader:
    def __init__(
        self,
        *,
        max_page_bytes: int,
        timeout_s: float,
        max_redirects: int = 5,
        resolve: Resolver = system_resolve,
        transport: Optional[httpx.AsyncBaseTransport] = None,
        retry_wait_s: float = 8,
    ):
        self._max_page_bytes = max_page_bytes
        self._timeout_s = timeout_s
        self._max_redirects = max_redirects
        self._resolve = resolve
        self._transport = transport
        self._retry_wait_s = retry_wait_s

    async def read(self, url: str, evidence_id: str) -> EvidenceDocument:
        fetched_at = datetime.now(timezone.utc)
        try:
            final_url, body, charset = await self.fetch(url)
        except FetchError as e:
            return EvidenceDocument(evidence_id=evidence_id, url=url, fetched_at=fetched_at,
                                    fetch_status="unavailable", failure_reason=e.reason)
        add_page_read()
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

    async def fetch(self, url: str) -> FetchedPage:
        """经过安全检查和体积限制取回原始 HTML；失败时抛出 FetchError。"""
        current = url
        hops = 0
        server_busy = 0
        async with httpx.AsyncClient(
            transport=self._transport,
            timeout=self._timeout_s,
            follow_redirects=False,
            headers={"User-Agent": USER_AGENT},
        ) as client:
            while hops <= self._max_redirects:
                await self._check(current, is_redirect=hops > 0)
                try:
                    async with client.stream("GET", current) as resp:
                        location = resp.headers.get("location")
                        if resp.is_redirect and location:
                            current = urljoin(current, location)
                            hops += 1
                            continue
                        if resp.status_code == 503 and server_busy < 1:
                            server_busy += 1
                            await asyncio.sleep(self._retry_wait_s)
                            continue
                        # 产品首页有时用 302 返回完整 HTML，且不带 Location。
                        return FetchedPage(current, await self._read_body(resp), resp.charset_encoding)
                except httpx.TimeoutException as e:
                    raise FetchError("timeout") from e
                except httpx.HTTPError as e:
                    raise FetchError("network") from e
        raise FetchError("too_many_redirects")

    async def _check(self, url: str, *, is_redirect: bool) -> None:
        try:
            await check_url(url, resolve=self._resolve)
        except UnsafeUrlError as e:
            if e.reason == "dns_failed":
                raise FetchError("dns_failed") from e
            raise FetchError("unsafe_redirect" if is_redirect else "unsafe_url") from e

    async def _read_body(self, resp: httpx.Response) -> bytes:
        if resp.status_code >= 400:
            raise FetchError(f"http_{resp.status_code}")
        content_type = resp.headers.get("content-type", "").split(";")[0].strip().lower()
        if content_type not in HTML_TYPES:
            raise FetchError("not_html")
        declared = resp.headers.get("content-length")
        if declared and declared.isdigit() and int(declared) > self._max_page_bytes:
            raise FetchError("too_large")
        body = bytearray()
        async for chunk in resp.aiter_bytes():
            body.extend(chunk)
            if len(body) > self._max_page_bytes:
                raise FetchError("too_large")
        return bytes(body)


def _homepage_price(soup) -> Optional[str]:
    """产品首页上这一款自己的标价。旁边对比机型的价格用的是别的标记，不取。"""
    node = soup.select_one("span.product-meta__ecoPrice")
    if node is None:
        return None
    match = re.search(r"[￥¥]\s*([\d,]+(?:\.\d{1,2})?)", node.get_text(" ", strip=True))
    return match.group(1) if match else None


def extract_page(body: bytes, charset: Optional[str] = None, base_url: str = "") -> Tuple[Optional[str], str, List[str]]:
    """返回标题、正文和页面中的链接（已转为绝对地址，去重，最多 MAX_LINKS 条）。"""
    soup = BeautifulSoup(body, "html.parser", from_encoding=charset)
    home_price = _homepage_price(soup)
    title = soup.title.get_text(strip=True) if soup.title else None
    hrefs = (a.get("href", "").strip() for a in soup.find_all("a"))
    links = list(dict.fromkeys(urljoin(base_url, h) for h in hrefs if h and not h.startswith(("#", "javascript:"))))
    for tag in soup(["script", "style", "noscript", "template"]):
        tag.decompose()
    for row in soup.find_all("tr"):
        cells = [cell.get_text(" ", strip=True) for cell in row.find_all(["th", "td"])]
        row.replace_with(soup.new_string(" | ".join(c for c in cells if c)))
    lines = (" ".join(line.split()) for line in soup.get_text("\n").splitlines())
    text = "\n".join(line for line in lines if line)
    if home_price:
        text = f"首页价格：￥{home_price}\n{text}"
    return title or None, text, links[:MAX_LINKS]

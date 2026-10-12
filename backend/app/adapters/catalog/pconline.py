import re
from typing import List, Optional, Protocol
from urllib.parse import quote_plus, urljoin, urlsplit

from bs4 import BeautifulSoup
from pydantic import BaseModel

from app.adapters.pages.reader import FetchedPage, FetchError
from app.core.usage import add_search

SEARCH_URL = "https://ks.pconline.com.cn/product.shtml?q="
SEARCH_HOST = "ks.pconline.com.cn"
PRODUCT_HOST = "product.pconline.com.cn"
# 站内搜索按 GBK 解释中文关键词；UTF-8 编码的中文会搜出无关结果（2026-10-11 实测）。
KEYWORD_ENCODING = "gbk"
PRODUCT_PATH = re.compile(r"^/([a-z_]+)/([a-z0-9_]+)/(\d+)\.html$")
# 本产品品类 → 太平洋产品库的品类目录（2026-10-11 按五个品类的真实页面整理，任务 24 实测后可补充）。
CATEGORY_DIRS = {
    "laptop": ["notebook"],
    "phone": ["mobile"],
    "tablet": ["tabletpc"],
    "headphones": ["earphone"],
}


class CatalogSearchError(Exception):
    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


class CatalogHit(BaseModel):
    """站内搜索结果中的一个具体配置。参数摘要和列表价只用来定位，不能当作事实。"""

    product_id: str
    name: str
    url: str
    category_dir: str
    brand_dir: str
    discontinued: bool
    summary: str = ""

    @property
    def detail_url(self) -> str:
        return self.url[: -len(".html")] + "_detail.html"

    @property
    def price_url(self) -> str:
        return self.url[: -len(".html")] + "_price.html"


class HtmlFetcher(Protocol):
    async def fetch(self, url: str) -> FetchedPage: ...


def build_search_url(keyword: str, encoding: str = KEYWORD_ENCODING) -> str:
    return SEARCH_URL + quote_plus(keyword.strip(), encoding=encoding, errors="ignore")


def parse_product_url(href: str) -> Optional[CatalogHit]:
    """把结果中的链接规范成 https 配置页网址；不是配置页的返回 None。"""
    url = urljoin("https://" + PRODUCT_HOST + "/", href)
    parts = urlsplit(url)
    match = PRODUCT_PATH.match(parts.path)
    if parts.hostname != PRODUCT_HOST or match is None:
        return None
    category_dir, brand_dir, product_id = match.groups()
    return CatalogHit(product_id=product_id, name="", url=f"https://{PRODUCT_HOST}{parts.path}",
                      category_dir=category_dir, brand_dir=brand_dir, discontinued=False)


def parse_search_results(body: bytes, charset: Optional[str] = None) -> List[CatalogHit]:
    soup = BeautifulSoup(body, "html.parser", from_encoding=charset or KEYWORD_ENCODING)
    hits: List[CatalogHit] = []
    seen = set()
    for item in soup.select("#Jitems li.item"):
        link = item.select_one("a.item-name")
        if link is None:
            continue
        hit = parse_product_url(link.get("href", ""))
        if hit is None or hit.product_id in seen:
            continue
        seen.add(hit.product_id)
        price = item.select_one(".item-sales .price")
        discontinued = price is not None and (
            "price-off" in (price.get("class") or []) or "停产" in price.get_text()
        )
        summary = item.select_one(".item-des")
        hits.append(hit.model_copy(update={
            "name": (link.get("title") or link.get_text(" ", strip=True)).strip(),
            "discontinued": discontinued,
            "summary": " ".join(summary.get_text(" ", strip=True).split()) if summary else "",
        }))
    return hits


class PconlineCatalog:
    def __init__(self, fetcher: HtmlFetcher):
        self._fetcher = fetcher

    async def search(self, keyword: str) -> List[CatalogHit]:
        """失败时抛出 CatalogSearchError；搜索被跳转到站外时同样视为失败。"""
        try:
            page = await self._fetcher.fetch(build_search_url(keyword))
        except FetchError as e:
            raise CatalogSearchError(e.reason) from e
        if urlsplit(page.final_url).hostname != SEARCH_HOST:
            raise CatalogSearchError("redirected_off_site")
        add_search()
        return parse_search_results(page.body, page.charset)

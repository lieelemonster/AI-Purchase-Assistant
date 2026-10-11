import asyncio

import httpx
import pytest

from app.adapters.catalog.pconline import (
    CatalogSearchError,
    PconlineCatalog,
    build_search_url,
    parse_search_results,
)
from app.adapters.pages.reader import PageReader

# 仿照站内搜索结果页结构的虚构页面，型号均为虚构。
SEARCH_PAGE = """
<html><head><title>搜索：示例本—太平洋电脑网快搜</title></head><body>
<div class="crumb">找到“示例本”相关信息共3条</div>
<ul class="list-items list-type-tw" id="Jitems">
  <li class="item"><div class="item-wrap">
    <div class="item-pic"><a href="//product.pconline.com.cn/notebook/demo/1000001.html"><img/></a></div>
    <div class="item-detail"><div class="item-title">
      <a href="//product.pconline.com.cn/notebook/demo/1000001.html" class="item-name" title="示例品牌 示例本 14(16GB/512GB)"><em class="red">示例本</em> 14(16GB/512GB)</a>
      <span class="item-des">产品定位:轻薄本 | 内存容量:16GB |
        硬盘容量:512GB SSD</span>
    </div></div>
    <div class="item-sales"><div class="price price-now"><a href="//product.pconline.com.cn/notebook/demo/1000001_price.html">￥5999</a></div></div>
  </div></li>
  <li class="item"><div class="item-wrap">
    <div class="item-detail"><div class="item-title">
      <a href="//product.pconline.com.cn/notebook/demo/1000002.html" class="item-name" title="示例品牌 示例本 14(8GB/256GB)">示例本 14(8GB/256GB)</a>
      <span class="item-des">产品定位:轻薄本</span>
    </div></div>
    <div class="item-sales"><div class="price price-off price-num"><a title="已停产">停产</a></div></div>
  </div></li>
  <li class="item"><div class="item-wrap">
    <div class="item-detail"><div class="item-title">
      <a href="//dealer.pconline.com.cn/shop/1.html" class="item-name" title="某经销商">某经销商</a>
    </div></div>
  </div></li>
</ul>
<a href="//product.pconline.com.cn/mobile/demo/1000009.html">页面别处的推荐链接</a>
</body></html>
"""

EMPTY_PAGE = '<html><body><div class="crumb">没有找到相关信息</div><ul id="Jitems"></ul></body></html>'


def gbk_html(text):
    return httpx.Response(200, content=text.encode("gbk"), headers={"content-type": "text/html; charset=GBK"})


async def fake_resolve(host):
    return ["93.184.216.34"]


def catalog(handler):
    reader = PageReader(max_page_bytes=500_000, timeout_s=5, resolve=fake_resolve, transport=httpx.MockTransport(handler))
    return PconlineCatalog(reader)


def test_results_are_parsed_with_name_id_url_and_directories():
    hits = parse_search_results(SEARCH_PAGE.encode("gbk"), "GBK")
    assert [h.product_id for h in hits] == ["1000001", "1000002"]
    first = hits[0]
    assert first.name == "示例品牌 示例本 14(16GB/512GB)"
    assert first.url == "https://product.pconline.com.cn/notebook/demo/1000001.html"
    assert (first.category_dir, first.brand_dir) == ("notebook", "demo")
    assert first.summary == "产品定位:轻薄本 | 内存容量:16GB | 硬盘容量:512GB SSD"
    assert first.detail_url.endswith("/1000001_detail.html")
    assert first.price_url.endswith("/1000001_price.html")


def test_discontinued_result_is_flagged():
    hits = parse_search_results(SEARCH_PAGE.encode("gbk"), "GBK")
    assert [h.discontinued for h in hits] == [False, True]


def test_links_outside_the_result_list_or_not_product_pages_are_ignored():
    ids = [h.product_id for h in parse_search_results(SEARCH_PAGE.encode("gbk"), "GBK")]
    assert "1000009" not in ids
    assert len(ids) == 2


def test_empty_result_page_returns_no_hits():
    assert parse_search_results(EMPTY_PAGE.encode("gbk"), "GBK") == []


def test_chinese_keyword_is_gbk_encoded():
    assert build_search_url("苹果") == "https://ks.pconline.com.cn/product.shtml?q=%C6%BB%B9%FB"
    assert build_search_url("华为 MateBook 14") == "https://ks.pconline.com.cn/product.shtml?q=%BB%AA%CE%AA+MateBook+14"


def test_search_goes_through_the_page_reader():
    requested = []

    def handler(request):
        requested.append(str(request.url))
        return gbk_html(SEARCH_PAGE)

    hits = asyncio.run(catalog(handler).search("示例本"))
    assert len(hits) == 2
    assert requested[0].startswith("https://ks.pconline.com.cn/product.shtml?q=")


def test_fetch_failure_becomes_a_search_error():
    def handler(request):
        raise httpx.ReadTimeout("slow", request=request)

    with pytest.raises(CatalogSearchError) as e:
        asyncio.run(catalog(handler).search("示例本"))
    assert e.value.reason == "timeout"


def test_redirect_off_site_is_a_search_error():
    def handler(request):
        if request.url.host == "ks.pconline.com.cn":
            return httpx.Response(302, headers={"location": "https://evil.example.com/"})
        return gbk_html(SEARCH_PAGE)

    with pytest.raises(CatalogSearchError) as e:
        asyncio.run(catalog(handler).search("示例本"))
    assert e.value.reason == "redirected_off_site"

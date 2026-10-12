import asyncio

import httpx

from app.adapters.pages.reader import PageReader

PUBLIC_DNS = {"shop.example": ["93.184.216.34"], "cdn.example": ["93.184.216.35"]}

SPEC_PAGE = """
<html><head><title>轻薄本 A 技术规格</title><style>.x{color:red}</style></head>
<body>
  <script>var price = 1;</script>
  <h1>轻薄本 A</h1>
  <table>
    <tr><th>内存</th><td>16GB</td></tr>
    <tr><th>重量</th><td>约 1.2 kg</td></tr>
  </table>
</body></html>
""".encode("utf-8")


async def fake_resolve(host):
    if host not in PUBLIC_DNS:
        raise OSError("not found")
    return PUBLIC_DNS[host]


def read(handler, url="https://shop.example/a", max_page_bytes=100_000):
    reader = PageReader(max_page_bytes=max_page_bytes, timeout_s=5, resolve=fake_resolve,
                        transport=httpx.MockTransport(handler), retry_wait_s=0)
    return asyncio.run(reader.read(url, evidence_id="e1"))


def html(body, status=200):
    return httpx.Response(status, content=body, headers={"content-type": "text/html; charset=utf-8"})


def test_reads_title_text_hash_and_keeps_table_rows():
    doc = read(lambda request: html(SPEC_PAGE))
    assert doc.fetch_status == "ok"
    assert doc.final_url == "https://shop.example/a"
    assert doc.title == "轻薄本 A 技术规格"
    assert len(doc.content_hash) == 64
    assert "内存 | 16GB" in doc.text.splitlines()
    assert "重量 | 约 1.2 kg" in doc.text.splitlines()
    assert "var price" not in doc.text
    assert "color:red" not in doc.text


def test_links_are_absolute_and_deduplicated():
    page = b"""<html><body>
      <a href="//huawei.jd.com/">shop</a><a href="/item/2.html">rel</a><a href="/item/2.html">dup</a>
      <a href="#top">anchor</a><a href="javascript:void(0)">js</a>
    </body></html>"""
    doc = read(lambda request: html(page))
    assert doc.links == ["https://huawei.jd.com/", "https://shop.example/item/2.html"]


def test_follows_safe_redirect_and_records_final_url():
    def handler(request):
        if request.url.host == "shop.example":
            return httpx.Response(301, headers={"location": "https://cdn.example/a"})
        return html(SPEC_PAGE)

    doc = read(handler)
    assert doc.fetch_status == "ok"
    assert doc.url == "https://shop.example/a"
    assert doc.final_url == "https://cdn.example/a"


def test_redirect_to_localhost_is_rejected():
    doc = read(lambda request: httpx.Response(302, headers={"location": "http://127.0.0.1/admin"}))
    assert doc.fetch_status == "unavailable"
    assert doc.failure_reason == "unsafe_redirect"


def test_unsafe_start_url_is_rejected_without_request():
    def handler(request):
        raise AssertionError("不应发出请求")

    doc = read(handler, url="http://192.168.1.1/")
    assert doc.failure_reason == "unsafe_url"


def test_page_over_size_limit_is_rejected():
    doc = read(lambda request: html(b"<html>" + b"a" * 2000 + b"</html>"), max_page_bytes=1000)
    assert doc.fetch_status == "unavailable"
    assert doc.failure_reason == "too_large"


def test_timeout_is_reported_as_timeout():
    def handler(request):
        raise httpx.ReadTimeout("slow", request=request)

    assert read(handler).failure_reason == "timeout"


def test_non_html_content_is_rejected():
    doc = read(lambda request: httpx.Response(200, content=b"%PDF-1.7", headers={"content-type": "application/pdf"}))
    assert doc.failure_reason == "not_html"


def test_busy_page_is_retried_until_it_loads():
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        if calls["n"] < 2:
            return html(b"<html><title>503</title></html>", status=503)
        return html(b"<html><head><title>ok</title></head><body>hello</body></html>")

    doc = read(handler)
    assert doc.fetch_status == "ok"
    assert "hello" in doc.text
    assert calls["n"] == 2


def test_http_error_status_is_recorded():
    assert read(lambda request: html(b"not found", status=404)).failure_reason == "http_404"


def test_redirect_without_location_keeps_the_html_body():
    page = """<html><head><title>示例本报价</title></head><body>
      <span class="product-meta__ecoPrice">¥4699</span>
    </body></html>""".encode("utf-8")
    doc = read(lambda request: html(page, status=302))
    assert doc.fetch_status == "ok"
    assert doc.final_url == "https://shop.example/a"
    assert doc.text.startswith("首页价格：￥4699")


def test_redirect_loop_stops():
    doc = read(lambda request: httpx.Response(302, headers={"location": "https://shop.example/a"}))
    assert doc.failure_reason == "too_many_redirects"

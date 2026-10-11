from datetime import datetime, timezone

import pytest

from app.adapters.pages.reader import extract_page
from app.core.verification.price_parsing import parse_reference_price
from app.schemas.evidence import EvidenceDocument

NOW = datetime(2026, 10, 11, tzinfo=timezone.utc)
NAME = "示例品牌 示例本 14(16GB/512GB)"


def price_page(reference_block, extra=""):
    """仿照太平洋报价页结构的虚构页面。"""
    return f"""
<html><head><title>{NAME}价格_太平洋产品报价</title></head><body>
<h1>{NAME}报价</h1>
<dl class="price"><dt>参考价：</dt><dd>{reference_block}</dd></dl>
<ul class="dealers">
  <li>某经销商 示例本 14 <span>¥ 7469</span></li>
  <li>其他型号 示例本 16 参考价：<span>￥ 8999</span>（行货价格）</li>
</ul>
{extra}
</body></html>"""


def doc_from(html, status="ok"):
    if status != "ok":
        return EvidenceDocument(evidence_id="e2", url="https://product.pconline.com.cn/x_price.html", fetched_at=NOW,
                                fetch_status="unavailable", failure_reason="timeout")
    title, text, _ = extract_page(html.encode("utf-8"), "utf-8")
    return EvidenceDocument(evidence_id="e2", url="https://product.pconline.com.cn/x_price.html",
                            final_url="https://product.pconline.com.cn/x_price.html", title=title,
                            fetched_at=NOW, fetch_status="ok", content_hash="h", text=text)


def parse(html, multi_config=False, status="ok"):
    doc = doc_from(html, status)
    return doc, parse_reference_price(doc, "c1", NAME, multi_config)


def test_reference_price_is_parsed_into_minor_units():
    doc, price = parse(price_page("<em>￥</em> <strong>7399</strong> <span>（行货价格）</span>"))
    assert (price.status, price.amount_minor, price.minor_unit_digits, price.currency) == ("supported", 739900, 2, "CNY")
    assert price.price_basis == "pconline_reference"
    assert price.excerpt in doc.text
    assert price.variant_identity == NAME


def test_dealer_price_is_not_used():
    _, price = parse(price_page("<em>￥</em> 7399 （行货价格）"))
    assert price.amount_minor == 739900


@pytest.mark.parametrize("block", ["暂无报价", "停产", ""])
def test_missing_reference_price_is_unknown_not_zero(block):
    _, price = parse(price_page(block))
    assert (price.status, price.amount_minor, price.evidence_id) == ("unknown", None, None)


def test_other_models_reference_price_is_never_borrowed():
    _, price = parse(price_page("暂无报价"))
    assert price.amount_minor != 899900


def test_price_range_from_a_series_page_is_not_used():
    assert parse(price_page("￥ 6099 - ￥ 8499"))[1].status == "unknown"


def test_multi_config_page_price_is_marked_as_starting_price():
    _, price = parse(price_page("￥ 4199 （行货价格）"), multi_config=True)
    assert price.price_basis == "pconline_reference_starting"
    assert price.conditions


def test_thousands_separator_and_decimals_are_handled():
    _, price = parse(price_page("￥ 12,999.00 （行货价格）"))
    assert price.amount_minor == 1299900


def test_real_page_line_layout_is_parsed():
    text = "竞品对比\n参考价：\n￥\n4199\n（行货价格）\n版本选择：\n12GB+256GB"
    doc = EvidenceDocument(evidence_id="e2", url="u", final_url="u", fetched_at=NOW, fetch_status="ok",
                           content_hash="h", text=text)
    price = parse_reference_price(doc, "c1", NAME, multi_config=True)
    assert (price.amount_minor, price.price_basis) == (419900, "pconline_reference_starting")
    assert price.excerpt in text


def test_unreadable_page_gives_unknown_price():
    _, price = parse("", status="unavailable")
    assert (price.status, price.amount_minor) == ("unknown", None)


def test_own_reference_price_wins_over_other_models_listed_below():
    _, price = parse(price_page("￥ 5999 （行货价格）"))
    assert price.amount_minor == 599900

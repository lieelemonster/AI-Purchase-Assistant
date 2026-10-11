import itertools
from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from app.adapters.pages.reader import extract_page
from app.config.categories import category_ids
from app.config.field_tables import FieldTable, load_field_table
from app.core.verification.spec_parsing import parse_spec_page
from app.schemas.evidence import EvidenceDocument

NOW = datetime(2026, 10, 11, tzinfo=timezone.utc)

# 仿照太平洋参数页“详细参数”表格结构的虚构页面。
SPEC_PAGE = """
<html><head><title>示例本 14(16GB/512GB)参数</title></head><body>
<h1>示例本 14(16GB/512GB)参数</h1>
<h3>详细参数</h3>
<table>
  <tr><th>上市时间</th><td><a href="//product.pconline.com.cn/so/1/">2026年</a>,5月</td></tr>
  <tr><th>处理器</th><td>示例芯片 X1<a href="//diy.pconline.com.cn/">点击型号查看完整天梯图</a></td></tr>
  <tr><th>内存容量</th><td><i><a href="#">16GB</a>• <a href="#">内存容量是什么</a>• <a href="#">查看所有16GB示例</a></i></td></tr>
  <tr><th>硬盘容量</th><td>512GB SSD</td></tr>
  <tr><th>续航时间</th><td>具体时间视使用环境而定</td></tr>
  <tr><th>显卡芯片</th><td>暂无数据</td></tr>
</table>
<table>
  <tr><th>型号</th><td>参考价</td></tr>
  <tr><th>示例本 14(32GB/1TB)</th><td>￥7999</td></tr>
</table>
</body></html>
"""


def doc_from_html(html, evidence_id="e1"):
    title, text, links = extract_page(html.encode("utf-8"), "utf-8", base_url="https://product.pconline.com.cn/")
    return EvidenceDocument(evidence_id=evidence_id, url="https://product.pconline.com.cn/notebook/demo/1_detail.html",
                            final_url="https://product.pconline.com.cn/notebook/demo/1_detail.html", title=title,
                            fetched_at=NOW, fetch_status="ok", content_hash="h", text=text, links=links)


def parse(doc, category="laptop"):
    counter = itertools.count(1)
    return parse_spec_page(doc, load_field_table(category), "c1", lambda: f"f{next(counter)}")


def facts_by_field(result):
    return {f.field: f for f in result.facts}


def test_table_row_becomes_a_supported_fact_with_verbatim_excerpt():
    doc = doc_from_html(SPEC_PAGE)
    memory = facts_by_field(parse(doc))["memory"]
    assert (memory.value, memory.status, memory.evidence_id) == ("16GB", "supported", "e1")
    assert memory.excerpt in doc.text.splitlines()
    assert memory.excerpt.startswith("内存容量 | 16GB")


def test_site_help_text_after_the_value_is_removed():
    facts = facts_by_field(parse(doc_from_html(SPEC_PAGE)))
    assert facts["cpu"].value == "示例芯片 X1"
    assert facts["release_date"].value == "2026年 ,5月"


@pytest.mark.parametrize("field", ["battery_life", "gpu"])
def test_placeholder_values_are_unknown(field):
    fact = facts_by_field(parse(doc_from_html(SPEC_PAGE)))[field]
    assert fact.status == "unknown"
    assert fact.value is None


def test_fields_missing_from_the_page_are_unknown():
    fact = facts_by_field(parse(doc_from_html(SPEC_PAGE)))["weight"]
    assert (fact.status, fact.evidence_id, fact.excerpt) == ("unknown", None, None)


def test_every_field_in_the_table_gets_exactly_one_fact():
    result = parse(doc_from_html(SPEC_PAGE))
    assert [f.field for f in result.facts] == [f.id for f in load_field_table("laptop").fields]
    assert len({f.fact_id for f in result.facts}) == len(result.facts)


def test_rows_of_other_models_are_not_mistaken_for_fields():
    values = [f.value for f in parse(doc_from_html(SPEC_PAGE)).facts]
    assert "￥7999" not in values


def test_page_without_a_spec_table_fails_and_yields_no_supported_facts():
    result = parse(doc_from_html("<html><body><p>页面改版了</p><table><tr><td>内存容量</td><td>16GB</td></tr></table></body></html>"))
    assert (result.status, result.reason) == ("failed", "spec_table_not_found")
    assert result.facts == []


def test_unavailable_page_fails():
    doc = EvidenceDocument(evidence_id="e1", url="https://product.pconline.com.cn/x.html", fetched_at=NOW,
                           fetch_status="unavailable", failure_reason="timeout")
    assert (parse(doc).status, parse(doc).reason) == ("failed", "timeout")


@pytest.mark.parametrize("category_id", sorted(category_ids()))
def test_every_category_has_a_valid_field_table(category_id):
    assert load_field_table(category_id).category_id == category_id


def test_one_pconline_label_cannot_map_to_two_fields():
    with pytest.raises(ValidationError, match="多个字段"):
        FieldTable(category_id="laptop", version="v1", fields=[
            {"id": "a", "name": "A", "pconline_labels": ["重量"]},
            {"id": "b", "name": "B", "pconline_labels": ["重量"]},
        ])

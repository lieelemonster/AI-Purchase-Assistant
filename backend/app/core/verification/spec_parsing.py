from typing import Callable, Dict, List, Literal, Optional, Tuple

from pydantic import BaseModel

from app.config.field_tables import FieldTable
from app.schemas.evidence import EvidenceDocument, VerifiedFact

MIN_MATCHED_FIELDS = 3
CELL_SEPARATOR = " | "
# 太平洋参数表在值后面附带的站内说明和链接文字，从这里起截掉。
NOISE_MARKERS = (" • ", "点击型号查看完整天梯图")
UNKNOWN_VALUES = {"暂无数据", "暂无", "未知", "--", "-", "具体时间视使用环境而定"}


class SpecParseResult(BaseModel):
    status: Literal["ok", "failed"]
    reason: Optional[str] = None
    facts: List[VerifiedFact] = []


def _clean_value(raw: str) -> str:
    value = raw
    for marker in NOISE_MARKERS:
        index = value.find(marker)
        if index != -1:
            value = value[:index]
    return " ".join(value.split()).strip(" ,，")


def _table_rows(text: str) -> Dict[str, Tuple[str, str]]:
    """把正文中“字段名 | 值”的行整理成 {字段名: (原文整行, 值)}；同名字段只取第一次出现。"""
    rows: Dict[str, Tuple[str, str]] = {}
    for line in text.splitlines():
        if CELL_SEPARATOR not in line:
            continue
        label, raw = line.split(CELL_SEPARATOR, 1)
        label = label.strip()
        if label and label not in rows:
            rows[label] = (line, raw)
    return rows


def parse_spec_page(
    doc: EvidenceDocument,
    table: FieldTable,
    candidate_id: str,
    next_fact_id: Callable[[], str],
) -> SpecParseResult:
    """参数页是规整表格，由程序直接解析；原文片段为整行，保证能在页面正文中逐字找到。"""
    if doc.fetch_status != "ok":
        return SpecParseResult(status="failed", reason=doc.failure_reason or "unavailable")

    rows = _table_rows(doc.text)
    matched = {f.id: next((rows[label] for label in f.pconline_labels if label in rows), None) for f in table.fields}
    if sum(1 for row in matched.values() if row) < MIN_MATCHED_FIELDS:
        return SpecParseResult(status="failed", reason="spec_table_not_found")

    facts: List[VerifiedFact] = []
    for field in table.fields:
        row = matched[field.id]
        value = _clean_value(row[1]) if row else ""
        if not row or not value or value in UNKNOWN_VALUES:
            facts.append(VerifiedFact(fact_id=next_fact_id(), candidate_id=candidate_id, field=field.id,
                                      evidence_id=doc.evidence_id if row else None,
                                      excerpt=row[0] if row else None, status="unknown"))
            continue
        facts.append(VerifiedFact(fact_id=next_fact_id(), candidate_id=candidate_id, field=field.id,
                                  value=value, evidence_id=doc.evidence_id, excerpt=row[0], status="supported"))
    return SpecParseResult(status="ok", facts=facts)

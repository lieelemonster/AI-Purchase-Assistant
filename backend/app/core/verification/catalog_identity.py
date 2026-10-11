import re
from typing import Dict, List, Literal, Optional
from urllib.parse import urlsplit

from pydantic import BaseModel

from app.adapters.catalog.pconline import PRODUCT_PATH
from app.core.verification.catalog_evidence import CatalogPages
from app.core.verification.catalog_match import CatalogMatch
from app.schemas.evidence import EvidenceDocument, VerifiedFact

# D-10：这些字段出现多个值，说明一个页面涵盖多个配置。
CONFIG_FIELDS = ("memory", "storage")
VALUE_SPLIT = re.compile(r"\s*[,，、]\s*")
DISCONTINUED_LINE = re.compile(r"参考价\s*[:：]?\s*停产")


class IdentityCheck(BaseModel):
    candidate_id: str
    status: Literal["ok", "rejected"]
    reason: Optional[str] = None
    price_page_ok: bool = False
    multi_config: bool = False
    facts: List[VerifiedFact] = []


def _compact(text: str) -> str:
    return "".join(text.split()).lower()


def _product_id(doc: EvidenceDocument) -> Optional[str]:
    path = urlsplit(doc.final_url or doc.url).path
    match = PRODUCT_PATH.match(re.sub(r"_(detail|price)\.html$", ".html", path))
    return match.group(3) if match else None


def _title_matches(doc: EvidenceDocument, name: str) -> bool:
    return doc.fetch_status == "ok" and bool(doc.title) and _compact(name) in _compact(doc.title)


def _options(value: str) -> List[str]:
    parts = [p for p in VALUE_SPLIT.split(value) if p]
    return parts if len(parts) > 1 and all(re.search(r"\d", p) for p in parts) else []


def _downgrade(facts: List[VerifiedFact]) -> List[VerifiedFact]:
    return [f.model_copy(update={"status": "unknown", "value": None}) if f.status == "supported" else f for f in facts]


def verify_catalog_identity(
    match: CatalogMatch,
    pages: CatalogPages,
    documents: Dict[str, EvidenceDocument],
    facts: List[VerifiedFact],
) -> IdentityCheck:
    """模型在匹配步骤已选定配置；这里由程序核对读到的页面确实是那个配置、未停产，并识别多配置页面。"""
    detail, price = documents[pages.detail_evidence_id], documents[pages.price_evidence_id]
    result = IdentityCheck(candidate_id=match.candidate_id, status="rejected")

    ids = {_product_id(d) for d in (detail, price)}
    if ids != {match.hit.product_id}:
        result.reason, result.facts = "product_id_mismatch", _downgrade(facts)
        return result
    if match.hit.discontinued or any(DISCONTINUED_LINE.search(d.text) for d in (detail, price) if d.fetch_status == "ok"):
        result.reason, result.facts = "discontinued", _downgrade(facts)
        return result
    if not _title_matches(detail, match.hit.name):
        result.reason, result.facts = "detail_title_mismatch", _downgrade(facts)
        return result

    checked: List[VerifiedFact] = []
    for fact in facts:
        options = _options(fact.value) if fact.status == "supported" and fact.field in CONFIG_FIELDS and fact.value else []
        if options:
            result.multi_config = True
            fact = fact.model_copy(update={"value": " / ".join(options) + " 可选"})
        checked.append(fact)

    result.status, result.facts = "ok", checked
    result.price_page_ok = _title_matches(price, match.hit.name)
    return result

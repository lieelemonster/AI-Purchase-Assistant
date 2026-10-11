import re
from decimal import Decimal, InvalidOperation

from app.config.market import MARKET
from app.schemas.evidence import EvidenceDocument, PriceFact

# 报价页正文中参考价跨多行，例如“参考价：\n￥\n4199\n（行货价格）”。只认带“行货价格”标注的单个金额（D-09）。
REFERENCE_PRICE = re.compile(r"参考价\s*[:：]\s*[￥¥]\s*([\d,]+(?:\.\d{1,2})?)\s*（行货价格）")
MINOR_UNIT_DIGITS = 2


def _to_minor(amount_text: str):
    try:
        amount = Decimal(amount_text.replace(",", ""))
    except InvalidOperation:
        return None
    minor = amount * (10 ** MINOR_UNIT_DIGITS)
    return int(minor) if minor == minor.to_integral_value() and minor >= 0 else None


def parse_reference_price(doc: EvidenceDocument, candidate_id: str, variant_name: str, multi_config: bool) -> PriceFact:
    """从太平洋报价页解析“参考价（行货价格）”；经销商报价不用。查不到时价格为未知，金额为空，不用 0 代替。"""
    unknown = PriceFact(candidate_id=candidate_id, variant_identity=variant_name, status="unknown")
    if doc.fetch_status != "ok":
        return unknown
    # 只认页面上第一次出现的“参考价”：本机没有参考价时，不能取到下方其他型号的参考价。
    first = doc.text.find("参考价")
    match = REFERENCE_PRICE.match(doc.text, first) if first != -1 else None
    if match is None:
        return unknown
    amount_minor = _to_minor(match.group(1))
    if amount_minor is None or amount_minor == 0:
        return unknown
    return PriceFact(
        candidate_id=candidate_id,
        amount_minor=amount_minor,
        minor_unit_digits=MINOR_UNIT_DIGITS,
        currency=MARKET.currency,
        region=MARKET.region,
        variant_identity=variant_name,
        price_basis="pconline_reference_starting" if multi_config else "pconline_reference",
        conditions=["页面涵盖多个配置，参考价为起售价，具体以购买时为准"] if multi_config else [],
        evidence_id=doc.evidence_id,
        excerpt=match.group(0),
        status="supported",
    )

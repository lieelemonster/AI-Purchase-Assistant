import re
from typing import Dict, Iterable, List

from app.schemas.candidate import Candidate
from app.schemas.evidence import PriceFact, VerifiedFact
from app.schemas.result import Reason

PLACEHOLDER = re.compile(r"\{\{(name|fact|price):([A-Za-z0-9]+)\}\}")
BARE_NUMBER_OR_CURRENCY = re.compile(r"[0-9]|[¥￥$€]")
UNKNOWN_PRICE_TEXT = "官方价格未查到"


class ReasonFillError(Exception):
    """理由里有占位符以外的数字、货币符号或型号原文，不能展示。"""


def format_price(price: PriceFact) -> str:
    if price.status != "supported" or price.amount_minor is None:
        return UNKNOWN_PRICE_TEXT
    digits = price.minor_unit_digits if price.minor_unit_digits is not None else 2
    scale = 10 ** digits
    whole, frac = divmod(price.amount_minor, scale)
    body = f"{whole:,}"
    if frac:
        body = f"{body}.{frac:0{digits}d}".rstrip("0").rstrip(".")
    symbol = "¥" if price.currency == "CNY" else (price.currency or "")
    return f"{symbol}{body}" if symbol in ("¥", "") else f"{symbol} {body}"


def contains_unsupported_literal(text: str, names: Iterable[str]) -> bool:
    try:
        _guard(text, names)
    except ReasonFillError:
        return True
    return False


def _guard(text: str, names: Iterable[str]) -> None:
    visible = PLACEHOLDER.sub(" ", text)
    if BARE_NUMBER_OR_CURRENCY.search(visible):
        raise ReasonFillError(text)
    for name in names:
        if name and name in visible:
            raise ReasonFillError(text)


def fill_reason_text(
    text: str,
    *,
    candidate: Candidate,
    facts: Dict[str, VerifiedFact],
    prices: Dict[str, PriceFact],
    names: Iterable[str],
) -> str:
    _guard(text, names)

    def replace(match: re.Match) -> str:
        kind, ref = match.group(1), match.group(2)
        if kind == "name":
            if ref != candidate.candidate_id:
                raise ReasonFillError(text)
            return candidate.model_hint
        if kind == "fact":
            fact = facts.get(ref)
            if fact is None or fact.candidate_id != candidate.candidate_id or not fact.value:
                raise ReasonFillError(text)
            return fact.value
        price = prices.get(ref)
        if price is None:
            raise ReasonFillError(text)
        return format_price(price)

    return PLACEHOLDER.sub(replace, text)


def fill_reasons(
    reasons: List[Reason],
    *,
    candidate: Candidate,
    facts: List[VerifiedFact],
    prices: Dict[str, PriceFact],
    names: Iterable[str],
) -> List[Reason]:
    by_id = {fact.fact_id: fact for fact in facts}
    filled = []
    for reason in reasons:
        try:
            text = fill_reason_text(
                reason.text,
                candidate=candidate,
                facts=by_id,
                prices=prices,
                names=names,
            )
        except ReasonFillError:
            continue
        filled.append(reason.model_copy(update={"text": text}))
    return filled

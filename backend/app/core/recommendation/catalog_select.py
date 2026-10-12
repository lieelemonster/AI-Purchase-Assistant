"""模型只在程序筛出的候选里选 1 个主推和最多 2 个备选。选不合法时重试，仍不行就按参考价规则排序。"""

import re
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field

from app.adapters.model.base import ModelGateway, ModelGatewayError
from app.catalog.library import LibraryProduct

SELECT_TASK = (
    "你是购买顾问。程序已经按预算和品牌从产品库筛出候选。你只能使用这些候选的 product_id，"
    "按参数和用户需求的匹配度选出 1 个主推、最多 2 个备选。必须给出推荐，不要提问。\n"
    "规则：\n"
    "1. 不得新增、改名或改写任何产品、参数、价格、链接。理由里出现的数字必须能在该候选的参数或参考价里找到。\n"
    "2. 价格未确认的候选可以选，但理由里要说明参考价未确认。\n"
    "3. 候选不足 3 个时，有几个选几个，不要编造空位。\n"
    "4. 理由只写这款产品为什么符合需求，不要写排序过程。\n"
    "只返回："
    '{"primary":{"product_id":"...","reason":"..."},'
    '"alternatives":[{"product_id":"...","reason":"..."},{"product_id":"...","reason":"..."}],'
    '"notes":"..."}'
)


class _Pick(BaseModel):
    model_config = ConfigDict(extra="ignore")

    product_id: str = ""
    reason: str = ""


class _Selection(BaseModel):
    model_config = ConfigDict(extra="ignore")

    need_clarification: bool = False
    questions: List[str] = Field(default_factory=list)
    primary: Optional[_Pick] = None
    alternatives: List[_Pick] = Field(default_factory=list)
    notes: str = ""


class CatalogChoice(BaseModel):
    product_id: str
    reason: str


class CatalogSelection(BaseModel):
    primary: Optional[CatalogChoice] = None
    alternatives: List[CatalogChoice] = []
    notes: str = ""
    questions: List[str] = []


def _payload(need_summary: str, products: List[LibraryProduct]) -> dict:
    return {
        "need": need_summary,
        "candidates": [
            {
                "product_id": product.product_id,
                "brand": product.brand,
                "model": product.model,
                "reference_price": product.price_text or "未确认",
                "specs": product.specs,
            }
            for product in products
        ],
    }


def _allowed_numbers(product: LibraryProduct) -> set:
    allowed = set(re.findall(r"\d+", f"{product.brand} {product.model}"))
    if product.price_yuan is not None:
        allowed.add(str(product.price_yuan))
    for value in product.specs.values():
        allowed.update(re.findall(r"\d+", value))
    return allowed


def _reason_ok(reason: str, product: LibraryProduct) -> bool:
    if not reason.strip():
        return False
    return set(re.findall(r"\d+", reason)) <= _allowed_numbers(product)


def _validate(draft: _Selection, products: List[LibraryProduct]) -> tuple:
    by_id = {product.product_id: product for product in products}
    questions = [question.strip() for question in draft.questions if question.strip()][:3]
    if draft.need_clarification or questions:
        return None, ["不要提问，必须从候选里选出主推和备选"]
    if draft.primary is None or draft.primary.product_id not in by_id:
        return None, ["primary.product_id 不在候选中"]
    chosen = [draft.primary]
    seen = {draft.primary.product_id}
    for item in draft.alternatives:
        if item.product_id in seen or item.product_id not in by_id:
            return None, [f"备选 {item.product_id} 不在候选中或重复"]
        chosen.append(item)
        seen.add(item.product_id)
        if len(chosen) == 3:
            break
    expected_extra = min(2, max(0, len(products) - 1))
    if len(chosen) - 1 != expected_extra:
        return None, [f"备选应为 {expected_extra} 个"]
    picks = []
    for item in chosen:
        product = by_id[item.product_id]
        if not _reason_ok(item.reason, product):
            return None, [f"{item.product_id} 的理由含有候选数据里没有的数字"]
        picks.append(CatalogChoice(product_id=item.product_id, reason=item.reason.strip()))
    return CatalogSelection(primary=picks[0], alternatives=picks[1:], notes=draft.notes.strip()), []


def _release_key(product: Optional[LibraryProduct]) -> tuple:
    text = "" if product is None else product.specs.get("release_date", "")
    matched = re.match(r"(\d{4})-(\d{2})(?:-(\d{2}))?$", text.strip())
    if matched is None:
        return (0, 0, 0)
    year, month, day = matched.groups()
    return (int(year), int(month), int(day or 0))


def order_newest_first(choices: List[CatalogChoice], by_id: dict) -> List[CatalogChoice]:
    """三款已经选定后，发布日期最近的放在主推。日期不明的排在后面，相同日期保持原来的先后。"""
    return sorted(choices, key=lambda choice: _release_key(by_id.get(choice.product_id)), reverse=True)


def rule_select(products: List[LibraryProduct]) -> CatalogSelection:
    """模型选不出来时的规则排序：有参考价的从低到高，未确认的放最后。"""
    ranked = sorted(products, key=lambda product: (product.price_yuan is None, product.price_yuan or 0, product.row_id))
    shown = ranked[:3]

    def reason(product: LibraryProduct) -> str:
        if product.price_yuan is None:
            bits = ["参考价未确认"]
        else:
            bits = [f"参考价 {product.price_yuan} 元，在预算区间内"]
        released = product.specs.get("release_date", "")
        if re.match(r"\d{4}-\d{2}", released):
            bits.append(f"发布日期 {released}")
        return "，".join(bits) + "。"

    picks = [CatalogChoice(product_id=product.product_id, reason=reason(product)) for product in shown]
    return CatalogSelection(
        primary=picks[0] if picks else None,
        alternatives=picks[1:],
    )


async def select_from_catalog(
    need_summary: str,
    products: List[LibraryProduct],
    model: ModelGateway,
    *,
    max_attempts: int = 2,
) -> CatalogSelection:
    if not products:
        return CatalogSelection(questions=["预算以内没有可推荐的产品。要不要提高预算？"])
    feedback: List[str] = []
    payload = _payload(need_summary, products)
    for _ in range(max_attempts):
        try:
            draft = await model.generate_json(
                task=SELECT_TASK,
                payload={**payload, "previous_problems": feedback},
                output_schema=_Selection,
            )
        except ModelGatewayError as exc:
            if exc.kind != "invalid_output":
                raise
            feedback = [str(exc)]
            continue
        selection, problems = _validate(draft, products)
        if selection is not None:
            return selection
        feedback = problems
    return rule_select(products)

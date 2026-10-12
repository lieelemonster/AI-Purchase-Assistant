from typing import Dict, List, Literal, NamedTuple, Optional, Set, Tuple

from pydantic import BaseModel

from app.core.needs.normalize import BUDGET_TOPIC, _option_budget
from app.schemas.evidence import PriceFact
from app.schemas.need import NeedProfile

# 预算是硬性标准。上下限都可以再超出这一段，单位是元。
_BUDGET_SLACK_YUAN = {
    "laptop": 500,
    "phone": 500,
    "tablet": 500,
    "headphones": 150,
}


class ConstraintCheck(BaseModel):
    candidate_id: str
    status: Literal["pass", "excluded", "unverified"]
    notes: List[str] = []


class _Budget(NamedTuple):
    key: str
    low: Optional[int]
    high: Optional[int]


def _slack_minor(category_id: str) -> int:
    return _BUDGET_SLACK_YUAN[category_id] * 100


def _budgets(need: NeedProfile) -> List[_Budget]:
    """有具体金额的预算都按硬性处理。问卷里点选的区间即使没被模型标成 hard，也同样生效。"""
    found: List[_Budget] = []
    seen: Set[Tuple[Optional[int], Optional[int]]] = set()

    def add(key: str, low: Optional[int], high: Optional[int]) -> None:
        if low is None and high is None:
            return
        signature = (low, high)
        if signature in seen:
            return
        seen.add(signature)
        found.append(_Budget(key, low, high))

    for requirement in need.requirements:
        if requirement.topic == BUDGET_TOPIC:
            add(requirement.requirement_id, requirement.budget_min_minor, requirement.budget_max_minor)
    for answer in need.option_answers:
        if answer.question_id != BUDGET_TOPIC:
            continue
        for option_id in answer.option_ids:
            bounds = _option_budget(option_id)
            if bounds is None:
                continue
            low, high = bounds
            add(
                f"option:{option_id}",
                low * 100 if low is not None else None,
                high * 100 if high is not None else None,
            )
    return found


def check_hard_constraints(need: NeedProfile, prices: Dict[str, PriceFact]) -> Dict[str, ConstraintCheck]:
    """预算按硬性标准排除超范围的已知价格。

    笔记本、手机、平板的上下限各允许超出 500 元；耳机允许超出 150 元。
    价格未知时不排除也不算满足；起售价落在放宽后的范围内时，提醒具体配置可能更贵。
    """
    budgets = _budgets(need)
    slack = _slack_minor(need.category_id)
    results: Dict[str, ConstraintCheck] = {}
    for candidate_id, price in prices.items():
        check = ConstraintCheck(candidate_id=candidate_id, status="pass")
        for budget in budgets:
            if price.status != "supported" or price.amount_minor is None:
                check.status = "unverified" if check.status == "pass" else check.status
                check.notes.append(f"budget_unverified:{budget.key}")
                continue
            over = budget.high is not None and price.amount_minor > budget.high + slack
            under = budget.low is not None and price.amount_minor < budget.low - slack
            if over or under:
                check.status = "excluded"
                check.notes.append(f"{'over' if over else 'under'}_budget:{budget.key}")
            elif price.price_basis == "pconline_reference_starting":
                check.notes.append(f"starting_price_within_budget:{budget.key}")
        results[candidate_id] = check
    return results

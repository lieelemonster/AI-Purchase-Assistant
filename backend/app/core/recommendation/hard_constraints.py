from typing import Dict, List, Literal

from pydantic import BaseModel

from app.core.needs.normalize import BUDGET_TOPIC
from app.schemas.evidence import PriceFact
from app.schemas.need import NeedProfile


class ConstraintCheck(BaseModel):
    candidate_id: str
    status: Literal["pass", "excluded", "unverified"]
    notes: List[str] = []


def check_hard_constraints(need: NeedProfile, prices: Dict[str, PriceFact]) -> Dict[str, ConstraintCheck]:
    """只有用户明确为硬性、且有具体金额的预算才会排除候选；软硬不明的交给排序步骤说明取舍。

    价格未知时不排除也不算满足（D-02 保留并标注）；起售价在预算内时提醒具体配置可能超出（D-10）。
    """
    budgets = [
        r for r in need.requirements
        if r.topic == BUDGET_TOPIC and r.strictness == "hard"
        and (r.budget_min_minor is not None or r.budget_max_minor is not None)
    ]
    results: Dict[str, ConstraintCheck] = {}
    for candidate_id, price in prices.items():
        check = ConstraintCheck(candidate_id=candidate_id, status="pass")
        for budget in budgets:
            rid = budget.requirement_id
            if price.status != "supported" or price.amount_minor is None:
                check.status = "unverified" if check.status == "pass" else check.status
                check.notes.append(f"budget_unverified:{rid}")
                continue
            over = budget.budget_max_minor is not None and price.amount_minor > budget.budget_max_minor
            under = budget.budget_min_minor is not None and price.amount_minor < budget.budget_min_minor
            if over or under:
                check.status = "excluded"
                check.notes.append(f"{'over' if over else 'under'}_budget:{rid}")
            elif price.price_basis == "pconline_reference_starting":
                check.notes.append(f"starting_price_within_budget:{rid}")
        results[candidate_id] = check
    return results

from typing import Dict, List, Tuple

from app.schemas.evidence import VerifiedFact
from app.schemas.result import UnresolvedItem


def mark_field_conflicts(facts: List[VerifiedFact]) -> Tuple[List[VerifiedFact], List[UnresolvedItem]]:
    """同一候选、同一字段出现两个不同的已核实值时，两条都标为冲突，不合并、不只留一条。"""
    grouped: Dict[Tuple[str, str], List[int]] = {}
    for index, fact in enumerate(facts):
        if fact.status == "supported" and fact.value:
            grouped.setdefault((fact.candidate_id, fact.field), []).append(index)

    updated = list(facts)
    unresolved: List[UnresolvedItem] = []
    for (candidate_id, field), indexes in grouped.items():
        values = {updated[index].value for index in indexes}
        if len(values) < 2:
            continue
        for index in indexes:
            updated[index] = updated[index].model_copy(update={"status": "conflicting"})
        unresolved.append(UnresolvedItem(
            candidate_id=candidate_id,
            field=field,
            status="conflicting",
            description=f"{field} 有互相冲突的资料：{'、'.join(sorted(values))}",
        ))
    return updated, unresolved

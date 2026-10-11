import re
from typing import Dict, List, Literal, Set

from pydantic import BaseModel, ConfigDict, Field

from app.adapters.model.base import ModelGateway, ModelGatewayError
from app.config.field_tables import load_field_table
from app.schemas.candidate import Candidate
from app.schemas.evidence import PriceFact, VerifiedFact
from app.schemas.need import NeedProfile
from app.schemas.result import Reason

RESULT_SIZE = 3
PLACEHOLDER = re.compile(r"\{\{(name|fact|price):([a-z0-9]+)\}\}")

TASK = (
    "你是购买顾问。请根据用户需求和每个候选在太平洋电脑网读到的参数、参考价，选出最适合的几款并排序，"
    "然后为每款写推荐理由。规则：\n"
    "1. 只能使用给出的参数和价格，不要凭记忆补充任何参数或价格。\n"
    "2. 每条理由写明对应的需求（need_refs，填需求编号如 r1；针对未知信息的提醒填 unknown:话题，如 unknown:budget）"
    "和依据的参数（fact_refs，填参数编号如 f3，价格填 price:候选编号）。\n"
    "3. conclusion_type：直接陈述参数的写 fact；结合需求作出的适合性判断写 judgment。\n"
    "4. 理由文字中出现型号名称、任何数值或金额时，必须写成占位符：型号写 {{name:c1}}，参数写 {{fact:f3}}，价格写 {{price:c1}}；"
    "除占位符外不要出现阿拉伯数字。\n"
    "5. 有局限要写进 limitations，例如信息未知、价格为起售价、参数缺失。\n"
    "6. ranking 按推荐顺序列出候选编号，最多 3 个，第一个是首选。"
)


class RankingError(Exception):
    pass


class _DraftReason(BaseModel):
    model_config = ConfigDict(extra="ignore")

    need_refs: List[str] = []
    fact_refs: List[str] = []
    conclusion_type: Literal["fact", "judgment"]
    text: str = Field(min_length=1)
    limitations: List[str] = []


class _DraftRanking(BaseModel):
    model_config = ConfigDict(extra="ignore")

    ranking: List[str]
    reasons: Dict[str, List[_DraftReason]]


class RankingResult(BaseModel):
    order: List[str]
    reasons: Dict[str, List[Reason]]


def _payload(need: NeedProfile, candidates: List[Candidate], facts: Dict[str, List[VerifiedFact]],
             prices: Dict[str, PriceFact]) -> dict:
    names = {f.id: f.name for f in load_field_table(need.category_id).fields}
    return {
        "needs": [{"id": r.requirement_id, "topic": r.topic, "statement": r.statement, "strictness": r.strictness}
                  for r in need.requirements],
        "unknowns": need.unknowns,
        "conflicts": [c.description for c in need.conflicts],
        "candidates": [
            {
                "candidate_id": c.candidate_id,
                "name": c.model_hint,
                "origin": c.origin,
                "facts": [{"fact_id": f.fact_id, "field": names.get(f.field, f.field), "value": f.value}
                          for f in facts.get(c.candidate_id, []) if f.status == "supported"],
                "price": _price_view(prices.get(c.candidate_id)),
            }
            for c in candidates
        ],
    }


def _price_view(price) -> dict:
    if price is None or price.status != "supported":
        return {"ref": None, "status": "unknown"}
    return {"ref": f"price:{price.candidate_id}", "yuan": price.amount_minor / 100, "basis": price.price_basis}


def _problems(draft: _DraftRanking, need: NeedProfile, allowed: Set[str],
              facts: Dict[str, List[VerifiedFact]], prices: Dict[str, PriceFact]) -> List[str]:
    problems = []
    expected = min(RESULT_SIZE, len(allowed))
    if len(draft.ranking) != expected or len(set(draft.ranking)) != len(draft.ranking):
        problems.append(f"ranking 应为 {expected} 个不重复的候选")
    need_ids = {r.requirement_id for r in need.requirements} | {f"unknown:{t}" for t in need.unknowns}
    for cid in draft.ranking:
        if cid not in allowed:
            problems.append(f"{cid} 不在允许的候选中")
            continue
        fact_ids = {f.fact_id for f in facts.get(cid, []) if f.status == "supported"}
        price = prices.get(cid)
        if price is not None and price.status == "supported":
            fact_ids.add(f"price:{cid}")
        reasons = draft.reasons.get(cid, [])
        if not reasons:
            problems.append(f"{cid} 没有推荐理由")
        for reason in reasons:
            if not reason.need_refs or not set(reason.need_refs) <= need_ids:
                problems.append(f"{cid} 的理由引用了不存在的需求：{reason.need_refs}")
            if not set(reason.fact_refs) <= fact_ids:
                problems.append(f"{cid} 的理由引用了不属于它的参数：{reason.fact_refs}")
            if reason.conclusion_type == "fact" and not reason.fact_refs:
                problems.append(f"{cid} 的事实类理由没有引用参数")
            for kind, ref in PLACEHOLDER.findall(reason.text):
                target = ref if kind == "fact" else f"price:{ref}" if kind == "price" else None
                if kind == "name" and ref != cid or target is not None and target not in fact_ids:
                    problems.append(f"{cid} 的理由占位符引用不当：{kind}:{ref}")
    return problems


async def rank_and_explain(
    need: NeedProfile,
    candidates: List[Candidate],
    facts: Dict[str, List[VerifiedFact]],
    prices: Dict[str, PriceFact],
    model: ModelGateway,
    max_attempts: int = 2,
) -> RankingResult:
    """排序和理由交给模型；程序核对排名和所有引用。不合格时重试，仍不合格抛出 RankingError。"""
    allowed = {c.candidate_id for c in candidates}
    payload = _payload(need, candidates, facts, prices)
    feedback: List[str] = []
    for _ in range(max_attempts):
        try:
            draft = await model.generate_json(task=TASK, payload={**payload, "previous_problems": feedback},
                                              output_schema=_DraftRanking)
        except ModelGatewayError as e:
            if e.kind != "invalid_output":
                raise
            feedback = [str(e)]
            continue
        feedback = _problems(draft, need, allowed, facts, prices)
        if not feedback:
            return RankingResult(
                order=draft.ranking,
                reasons={cid: [Reason(**r.model_dump()) for r in draft.reasons[cid]] for cid in draft.ranking},
            )
    raise RankingError("；".join(feedback) or "模型输出不合格")

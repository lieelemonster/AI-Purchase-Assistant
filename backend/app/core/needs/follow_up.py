import json
from functools import lru_cache
from pathlib import Path
from typing import Dict, List, Optional

from pydantic import BaseModel, ConfigDict

from app.adapters.model.base import ModelGateway
from app.config.option_loader import load_options
from app.core.needs.normalize import stated_budget_cap_yuan
from app.schemas.follow_up import FollowUpQuestion, FollowUpRequest
from app.schemas.need import NeedProfile

REQUIRED_INFO_FILE = Path(__file__).resolve().parents[2] / "config" / "required_info.json"

TASK = (
    "用户的购买需求还缺少一些必要信息，或者存在互相矛盾的地方。"
    "请用亲切、简短的中文，为每个缺失项和每处矛盾各写一个追问，帮助用户补充或澄清。"
    "不要替用户回答，不要推荐产品。缺失项的追问填写对应的 question_id；矛盾的追问 question_id 留空。"
)


class RequiredInfo(BaseModel):
    model_config = ConfigDict(extra="forbid")

    max_follow_up_rounds: int
    uncertain_option_ids: List[str]
    required_questions: Dict[str, List[str]]


class _DraftQuestions(BaseModel):
    model_config = ConfigDict(extra="ignore")

    questions: List[FollowUpQuestion] = []


@lru_cache(maxsize=1)
def load_required_info() -> RequiredInfo:
    return RequiredInfo.model_validate(json.loads(REQUIRED_INFO_FILE.read_text(encoding="utf-8")))


def find_missing(profile: NeedProfile) -> List[str]:
    """返回该品类必要信息中仍然未知的问题 ID。选了“还不确定”也算未知。"""
    info = load_required_info()
    answered = {
        a.question_id
        for a in profile.option_answers
        if any(o not in info.uncertain_option_ids for o in a.option_ids)
    }
    from_text = {r.topic for r in profile.requirements}
    missing = []
    for question_id in info.required_questions[profile.category_id]:
        if question_id in answered:
            continue
        if question_id == "budget" and stated_budget_cap_yuan(profile.free_text) is not None:
            continue
        if question_id in from_text and question_id not in profile.unknowns:
            continue
        missing.append(question_id)
    return missing


async def plan_follow_up(profile: NeedProfile, follow_up_round: int, model: ModelGateway) -> Optional[FollowUpRequest]:
    """D-04：必要信息缺失或需求冲突时最多追问一轮；追问过后仍未知的按未知继续推荐。"""
    if follow_up_round >= load_required_info().max_follow_up_rounds:
        return None
    missing = find_missing(profile)
    if not missing and not profile.conflicts:
        return None

    labels = {q.id: q.label for q in load_options(profile.category_id).questions}
    draft = await model.generate_json(
        task=TASK,
        payload={
            "need": profile.model_dump(mode="json"),
            "missing": [{"question_id": q, "question": labels[q]} for q in missing],
            "conflicts": [c.model_dump() for c in profile.conflicts],
        },
        output_schema=_DraftQuestions,
    )

    questions = [q for q in draft.questions if q.question_id is None or q.question_id in missing]
    covered = {q.question_id for q in questions}
    questions += [FollowUpQuestion(text=labels[q], question_id=q) for q in missing if q not in covered]
    if profile.conflicts and not any(q.question_id is None for q in questions):
        questions += [FollowUpQuestion(text=f"请确认：{c.description}") for c in profile.conflicts]

    return FollowUpRequest(
        round=follow_up_round + 1,
        missing_question_ids=missing,
        conflicts=profile.conflicts,
        questions=questions,
    )

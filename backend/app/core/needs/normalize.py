import re
from typing import Annotated, List, Literal, Optional, Set, Tuple, Union

from pydantic import BaseModel, ConfigDict, Field

from app.adapters.model.base import ModelGateway
from app.config.categories import load_categories
from app.config.market import MARKET
from app.config.option_loader import load_options
from app.schemas.need import Conflict, FreeTextSource, NeedProfile, OptionAnswer, OptionSource, Requirement
from app.schemas.options import OptionConfig

TASK = (
    "你负责整理用户的购买需求。根据用户在问卷中选择的选项和自由补充的文字，提取需求、未知信息和互相冲突的需求。规则：\n"
    "1. 每条需求必须注明出处：来自选项的，source 写 kind=option 以及 question_id、option_id；"
    "来自用户原话的，source 写 kind=free_text，quote 必须逐字摘自用户原话。\n"
    "2. 不要补充用户没说的内容。没提到或说不确定的信息（如预算、用途、品牌偏好）放进 unknowns，不要猜测数值。\n"
    "3. topic 和 unknowns 优先使用问卷中的问题 ID（见 questions）；不属于任何问题的，用简短的英文小写词。\n"
    "4. strictness：用户明确表示必须满足或不能超过的写 hard，倾向性的写 soft，无法判断的写 unknown。\n"
    "5. 两条需求互相矛盾时，在 conflicts 中说明，并用 requirement_indexes 指出是 requirements 中的哪几条（从 0 开始）。\n"
    "6. 用户在原话里写了明确的预算金额时，topic 写 budget，并在 budget_min_yuan / budget_max_yuan 填写金额（单位：元）；"
    "没有明确金额就不要填。"
)
BUDGET_TOPIC = "budget"


class InvalidNeedInput(ValueError):
    pass


class _OptionRef(BaseModel):
    kind: Literal["option"]
    question_id: str
    option_id: str


class _TextRef(BaseModel):
    kind: Literal["free_text"]
    quote: str


class ExtractedRequirement(BaseModel):
    model_config = ConfigDict(extra="ignore")

    topic: str = Field(min_length=1)
    statement: str = Field(min_length=1)
    strictness: Literal["hard", "soft", "unknown"] = "unknown"
    source: Annotated[Union[_OptionRef, _TextRef], Field(discriminator="kind")]
    budget_min_yuan: Optional[int] = Field(default=None, ge=0)
    budget_max_yuan: Optional[int] = Field(default=None, ge=0)


class ExtractedConflict(BaseModel):
    model_config = ConfigDict(extra="ignore")

    description: str = Field(min_length=1)
    requirement_indexes: List[int]


class NeedExtraction(BaseModel):
    model_config = ConfigDict(extra="ignore")

    requirements: List[ExtractedRequirement] = []
    unknowns: List[str] = []
    conflicts: List[ExtractedConflict] = []


def validate_answers(config: OptionConfig, answers: List[OptionAnswer]) -> None:
    questions = {q.id: q for q in config.questions}
    seen: Set[str] = set()
    for answer in answers:
        question = questions.get(answer.question_id)
        if question is None:
            raise InvalidNeedInput(f"未知问题：{answer.question_id}")
        if answer.question_id in seen:
            raise InvalidNeedInput(f"问题重复作答：{answer.question_id}")
        seen.add(answer.question_id)
        option_ids = {o.id for o in question.options}
        for option_id in answer.option_ids:
            if option_id not in option_ids:
                raise InvalidNeedInput(f"问题 {answer.question_id} 没有选项 {option_id}")
        if not question.multiple and len(answer.option_ids) > 1:
            raise InvalidNeedInput(f"问题 {answer.question_id} 是单选题")


OPTION_BUDGET = re.compile(r"^(?:under_(\d+)|(\d+)_(\d+)|over_(\d+))$")


def _option_budget(option_id: str) -> Optional[Tuple[Optional[int], Optional[int]]]:
    """预算选项的稳定 ID 本身就写明了范围，如 under_5000、5000_8000、over_12000（单位：元）。"""
    match = OPTION_BUDGET.match(option_id)
    if match is None:
        return None
    under, low, high, over = match.groups()
    if under:
        return None, int(under)
    if over:
        return int(over), None
    return int(low), int(high)


def _amount_in_quote(amount: Optional[int], quote: str) -> Optional[int]:
    """模型给出的金额必须能在用户原话里找到（如“6000”或“1万”），否则不采用。"""
    if amount is None:
        return None
    digits = re.sub(r"(?<=\d)[,，](?=\d{3})", "", quote)
    if re.search(rf"(?<!\d){amount}(?!\d)", digits):
        return amount
    if amount % 10000 == 0 and re.search(rf"(?<!\d){amount // 10000}万", digits):
        return amount
    return None


def _budget_bounds(item: "ExtractedRequirement") -> Tuple[Optional[int], Optional[int]]:
    if item.topic != BUDGET_TOPIC:
        return None, None
    if isinstance(item.source, _OptionRef):
        bounds = _option_budget(item.source.option_id) if item.source.question_id == BUDGET_TOPIC else None
        low, high = bounds or (None, None)
    else:
        low = _amount_in_quote(item.budget_min_yuan, item.source.quote)
        high = _amount_in_quote(item.budget_max_yuan, item.source.quote)
    return (low * 100 if low is not None else None), (high * 100 if high is not None else None)


def _source_is_real(source: Union[_OptionRef, _TextRef], selected: Set[Tuple[str, str]], free_text: str) -> bool:
    if isinstance(source, _OptionRef):
        return (source.question_id, source.option_id) in selected
    quote = source.quote.strip()
    return bool(quote) and quote in free_text


async def normalize_needs(
    category_id: str,
    option_answers: List[OptionAnswer],
    free_text: str,
    model: ModelGateway,
) -> NeedProfile:
    config = load_options(category_id)
    validate_answers(config, option_answers)
    category_name = next(c.name for c in load_categories().categories if c.id == category_id)

    extraction = await model.generate_json(
        task=TASK,
        payload={
            "category": {"id": category_id, "name": category_name},
            "questions": [q.model_dump() for q in config.questions],
            "option_answers": [a.model_dump() for a in option_answers],
            "free_text": free_text,
        },
        output_schema=NeedExtraction,
    )

    selected = {(a.question_id, o) for a in option_answers for o in a.option_ids}
    requirements: List[Requirement] = []
    id_by_index = {}
    for index, item in enumerate(extraction.requirements):
        if not _source_is_real(item.source, selected, free_text):
            continue
        requirement_id = f"r{len(requirements) + 1}"
        id_by_index[index] = requirement_id
        source: Union[OptionSource, FreeTextSource]
        if isinstance(item.source, _OptionRef):
            source = OptionSource(kind="option", question_id=item.source.question_id, option_id=item.source.option_id)
        else:
            source = FreeTextSource(kind="free_text", quote=item.source.quote.strip())
        budget_min, budget_max = _budget_bounds(item)
        requirements.append(Requirement(
            requirement_id=requirement_id,
            topic=item.topic,
            statement=item.statement,
            strictness=item.strictness,
            source=source,
            budget_min_minor=budget_min,
            budget_max_minor=budget_max,
        ))

    conflicts: List[Conflict] = []
    for conflict in extraction.conflicts:
        ids: List[Optional[str]] = [id_by_index.get(i) for i in conflict.requirement_indexes]
        if len(ids) >= 2 and all(ids):
            conflicts.append(Conflict(description=conflict.description, requirement_ids=ids))

    return NeedProfile(
        category_id=category_id,
        option_answers=option_answers,
        free_text=free_text,
        requirements=requirements,
        unknowns=sorted({u.strip() for u in extraction.unknowns if u.strip()}),
        conflicts=conflicts,
        market_context=MARKET,
    )

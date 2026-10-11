from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field

from app.adapters.model.base import ModelGateway
from app.schemas.candidate import Candidate
from app.schemas.need import NeedProfile

TASK = (
    "你是熟悉消费电子产品的购买顾问。根据用户需求和你已有的产品知识，"
    "提出最多 {max_candidates} 个可能适合的具体型号，供后续到厂商官网核实。"
    "每个候选只给品牌、型号、代际和需要核实的配置线索。"
    "不要给出价格，不要声称任何信息已经核实；"
    "需求中标为未知的信息保持未知，不要替用户假设预算、用途或品牌偏好。"
)


class ProposedCandidate(BaseModel):
    model_config = ConfigDict(extra="ignore")

    brand_hint: str = Field(min_length=1)
    model_hint: str = Field(min_length=1)
    generation_hint: Optional[str] = None
    variant_hint: Optional[str] = None


class CandidateProposal(BaseModel):
    model_config = ConfigDict(extra="ignore")

    candidates: List[ProposedCandidate]


async def propose_candidates(need: NeedProfile, model: ModelGateway, max_candidates: int) -> List[Candidate]:
    proposal = await model.generate_json(
        task=TASK.format(max_candidates=max_candidates),
        payload={"need": need.model_dump(mode="json"), "max_candidates": max_candidates},
        output_schema=CandidateProposal,
    )
    return [
        Candidate(candidate_id=f"c{i}", origin="model", **proposed.model_dump())
        for i, proposed in enumerate(proposal.candidates[:max_candidates], start=1)
    ]

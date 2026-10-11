from datetime import datetime
from typing import Annotated, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.schemas.evidence import FactStatus, PriceFact, VerifiedFact

FactRef = Annotated[str, Field(pattern=r"^(f\d+|price:c\d+)$")]

ResultStatus = Literal[
    "success",
    "insufficient_candidates",
    "timeout",
    "service_unavailable",
    "failed",
]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Reason(StrictModel):
    need_refs: List[str] = Field(min_length=1)
    fact_refs: List[FactRef] = []
    conclusion_type: Literal["fact", "judgment"]
    text: str = Field(min_length=1)
    limitations: List[str] = []

    @model_validator(mode="after")
    def fact_reason_needs_fact_refs(self):
        if self.conclusion_type == "fact" and not self.fact_refs:
            raise ValueError("事实类理由必须引用至少一条事实")
        return self


class RecommendationItem(StrictModel):
    candidate_id: str = Field(pattern=r"^c\d+$")
    name: str = Field(min_length=1)
    facts: List[VerifiedFact] = []
    price: PriceFact
    reasons: List[Reason] = []


class ComparisonEntry(StrictModel):
    candidate_id: str = Field(pattern=r"^c\d+$")
    comparable: bool
    difference_minor_vs_primary: Optional[int] = None
    not_comparable_reason: Optional[str] = None


class EvidenceSource(StrictModel):
    evidence_id: str = Field(pattern=r"^e\d+$")
    url: str
    title: Optional[str] = None
    fetched_at: datetime


class UnresolvedItem(StrictModel):
    candidate_id: Optional[str] = None
    field: Optional[str] = None
    status: FactStatus
    description: str


class RecommendationResult(StrictModel):
    request_id: str = Field(min_length=1)
    status: ResultStatus
    primary: Optional[RecommendationItem] = None
    alternatives: List[RecommendationItem] = []
    comparison: List[ComparisonEntry] = []
    evidence_sources: List[EvidenceSource] = []
    unresolved_items: List[UnresolvedItem] = []
    checked_at: datetime

    @model_validator(mode="after")
    def success_has_one_primary_and_two_alternatives(self):
        if self.status == "success" and (self.primary is None or len(self.alternatives) != 2):
            raise ValueError("正常成功的结果必须是首选 1 款＋备选 2 款")
        return self

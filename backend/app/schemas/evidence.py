from datetime import date, datetime
from typing import List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, StrictInt, model_validator

FactStatus = Literal["supported", "unknown", "conflicting", "unavailable"]

PriceBasis = Literal[
    "list_price",
    "starting_price",
    "installment",
    "trade_in",
    "education",
    "promotion",
    "unknown",
]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class EvidenceDocument(StrictModel):
    """本次请求中实际读取过的一个页面。"""

    evidence_id: str = Field(pattern=r"^e\d+$")
    url: str = Field(min_length=1)
    final_url: Optional[str] = None
    title: Optional[str] = None
    fetched_at: datetime
    page_date: Optional[date] = None
    fetch_status: Literal["ok", "unavailable"]
    failure_reason: Optional[str] = None
    content_hash: Optional[str] = None
    text: str = ""
    links: List[str] = []

    @model_validator(mode="after")
    def check_fetch_result(self):
        if self.fetch_status == "ok" and not (self.final_url and self.content_hash):
            raise ValueError("读取成功的页面必须有 final_url 和 content_hash")
        if self.fetch_status == "unavailable" and not self.failure_reason:
            raise ValueError("读取失败的页面必须有 failure_reason")
        return self


class VerifiedFact(StrictModel):
    """候选的单个规格字段及其依据。"""

    fact_id: str = Field(pattern=r"^f\d+$")
    candidate_id: str = Field(pattern=r"^c\d+$")
    field: str = Field(min_length=1)
    value: Optional[str] = None
    unit: Optional[str] = None
    evidence_id: Optional[str] = Field(default=None, pattern=r"^e\d+$")
    excerpt: Optional[str] = None
    status: FactStatus

    @model_validator(mode="after")
    def supported_needs_evidence(self):
        if self.status == "supported" and not (self.value and self.evidence_id and self.excerpt):
            raise ValueError("supported 字段必须有 value、evidence_id 和 excerpt")
        return self


class PriceFact(StrictModel):
    """某个具体配置在某地区、某价格口径下的价格。金额以最小货币单位的整数保存。"""

    candidate_id: str = Field(pattern=r"^c\d+$")
    amount_minor: Optional[StrictInt] = Field(default=None, ge=0)
    minor_unit_digits: Optional[StrictInt] = Field(default=None, ge=0, le=4)
    currency: Optional[str] = Field(default=None, pattern=r"^[A-Z]{3}$")
    region: Optional[str] = None
    variant_identity: Optional[str] = None
    price_basis: PriceBasis = "unknown"
    conditions: List[str] = []
    evidence_id: Optional[str] = Field(default=None, pattern=r"^e\d+$")
    excerpt: Optional[str] = None
    status: FactStatus

    @model_validator(mode="after")
    def check_amount_and_evidence(self):
        if self.amount_minor is not None and (self.minor_unit_digits is None or self.currency is None):
            raise ValueError("有金额时必须同时给出 minor_unit_digits 和 currency")
        if self.status == "supported" and not (
            self.amount_minor is not None and self.evidence_id and self.excerpt
        ):
            raise ValueError("supported 价格必须有 amount_minor、evidence_id 和 excerpt")
        return self

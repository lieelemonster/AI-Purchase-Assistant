from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


class Candidate(BaseModel):
    """AI 提出、尚未核实的候选；不携带价格或核实状态。"""

    model_config = ConfigDict(extra="forbid")

    candidate_id: str = Field(pattern=r"^c\d+$")
    brand_hint: str = Field(min_length=1)
    model_hint: str = Field(min_length=1)
    generation_hint: Optional[str] = None
    variant_hint: Optional[str] = None
    origin: Literal["model"]

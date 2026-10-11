from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.need import Conflict


class FollowUpQuestion(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str = Field(min_length=1)
    question_id: Optional[str] = None


class FollowUpRequest(BaseModel):
    """必要信息缺失或需求冲突时，返回给用户的追问。"""

    model_config = ConfigDict(extra="forbid")

    round: int = Field(ge=1)
    missing_question_ids: List[str] = []
    conflicts: List[Conflict] = []
    questions: List[FollowUpQuestion] = Field(min_length=1)

from typing import List

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict

from app.adapters.model.base import ModelGateway
from app.api.recommendations import get_model
from app.core.needs.normalize import normalize_needs
from app.schemas.need import NeedProfile, OptionAnswer

router = APIRouter(prefix="/v1")


class NormalizeIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    category_id: str
    option_answers: List[OptionAnswer] = []
    free_text: str = ""


@router.post("/needs/normalize", response_model=NeedProfile)
async def normalize(body: NormalizeIn, model: ModelGateway = Depends(get_model)) -> NeedProfile:
    return await normalize_needs(body.category_id, body.option_answers, body.free_text, model)

from fastapi import APIRouter, Depends

from app.adapters.model.base import ModelGateway
from app.config.settings import RuntimeConfig, load_runtime_config
from app.core.recommendation.recommend import RecommendRequest, recommend
from app.core.verification.catalog_match import CatalogLike
from app.core.verification.evidence_set import PageReaderLike
from app.schemas.need import OptionAnswer
from app.schemas.result import RecommendationResult
from pydantic import BaseModel, ConfigDict, Field


class RecommendationIn(BaseModel):
    """客户端只能提交自己的需求和请求标识，不能提交价格或“已核实”。"""

    model_config = ConfigDict(extra="forbid")

    request_id: str = Field(min_length=1)
    input_version: str = Field(min_length=1)
    category_id: str
    option_answers: list[OptionAnswer] = []
    free_text: str = ""
    follow_up_round: int = 0


class RecommendationOut(RecommendationResult):
    input_version: str


router = APIRouter(prefix="/v1")


def get_model() -> ModelGateway:
    raise RuntimeError("尚未接入模型服务")


def get_catalog() -> CatalogLike:
    raise RuntimeError("尚未接入产品库")


def get_reader() -> PageReaderLike:
    raise RuntimeError("尚未接入网页读取")


def get_config() -> RuntimeConfig:
    return load_runtime_config()


@router.post("/recommendations", response_model=RecommendationOut)
async def create_recommendation(
    body: RecommendationIn,
    model: ModelGateway = Depends(get_model),
    catalog: CatalogLike = Depends(get_catalog),
    reader: PageReaderLike = Depends(get_reader),
    config: RuntimeConfig = Depends(get_config),
) -> RecommendationOut:
    result = await recommend(
        RecommendRequest(
            request_id=body.request_id,
            category_id=body.category_id,
            option_answers=body.option_answers,
            free_text=body.free_text,
            follow_up_round=body.follow_up_round,
        ),
        model=model,
        catalog=catalog,
        reader=reader,
        config=config,
    )
    return RecommendationOut(input_version=body.input_version, **result.model_dump())

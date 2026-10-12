from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse

from app.adapters.model.base import ModelGateway
from app.adapters.model.deepseek import DeepSeekGateway
from app.adapters.catalog.pconline import PconlineCatalog
from app.adapters.pages.cache import CachedPageReader
from app.adapters.pages.reader import PageReader
from app.api.limiter import RequestLimiter
from app.config.settings import RuntimeConfig, load_project_env, load_runtime_config, load_secrets
from app.core.recommendation.recommend import RecommendRequest, recommend
from app.core.verification.catalog_evidence import Throttle, ThrottledReader
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
    load_project_env()
    secrets = load_secrets()
    if secrets.model_api_key is None:
        raise RuntimeError("缺少 MODEL_API_KEY")
    config = load_runtime_config()
    return DeepSeekGateway(secrets.model_api_key.get_secret_value(), timeout_s=config.call_timeout_s)


def _source_throttle(request: Request) -> Throttle:
    """搜索和读页面共用一把锁，避免两路请求同时打到太平洋电脑网。"""
    throttle = getattr(request.app.state, "source_throttle", None)
    if throttle is None:
        throttle = Throttle(load_runtime_config().source_min_interval_s)
        request.app.state.source_throttle = throttle
    return throttle


def get_reader(request: Request) -> PageReaderLike:
    config = load_runtime_config()
    raw = PageReader(max_page_bytes=config.max_page_bytes, timeout_s=config.call_timeout_s, retry_wait_s=8)
    return CachedPageReader(ThrottledReader(raw, _source_throttle(request)))


def get_catalog(request: Request) -> CatalogLike:
    config = load_runtime_config()
    raw = PageReader(max_page_bytes=config.max_page_bytes, timeout_s=config.call_timeout_s, retry_wait_s=8)
    return PconlineCatalog(ThrottledReader(raw, _source_throttle(request)))


def get_config() -> RuntimeConfig:
    return load_runtime_config()


def get_limiter(request: Request) -> RequestLimiter:
    limiter = getattr(request.app.state, "limiter", None)
    if limiter is None:
        config = load_runtime_config()
        limiter = RequestLimiter(config.rate_limit_per_minute, config.max_concurrent_requests)
        request.app.state.limiter = limiter
    return limiter


@router.post("/recommendations", response_model=RecommendationOut)
async def create_recommendation(
    body: RecommendationIn,
    request: Request,
    model: ModelGateway = Depends(get_model),
    catalog: CatalogLike = Depends(get_catalog),
    reader: PageReaderLike = Depends(get_reader),
    config: RuntimeConfig = Depends(get_config),
    limiter: RequestLimiter = Depends(get_limiter),
) -> RecommendationOut:
    decision = limiter.enter()
    if decision == "rate_limited":
        return JSONResponse(status_code=429, content={"error": "rate_limited", "message": "请求过于频繁，请一分钟后再试"})
    if decision == "busy":
        return JSONResponse(status_code=503, content={"error": "busy", "message": "服务繁忙，请稍后再试"})
    try:
        override = getattr(request.app.state, "recommend_override", None)
        if override is not None:
            result = await override()
        else:
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
    finally:
        limiter.leave()

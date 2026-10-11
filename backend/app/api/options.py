from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse

from app.config.option_loader import UnknownCategoryError, load_options
from app.schemas.options import OptionConfig

router = APIRouter(prefix="/v1")


@router.get(
    "/options",
    response_model=OptionConfig,
    responses={404: {"description": "未知品类", "content": {"application/json": {"example": {"error": "unknown_category", "message": "未知品类：car"}}}}},
)
def get_options(category_id: str = Query(..., description="品类 ID，例如 laptop")):
    try:
        return load_options(category_id)
    except UnknownCategoryError:
        return JSONResponse(status_code=404, content={"error": "unknown_category", "message": f"未知品类：{category_id}"})

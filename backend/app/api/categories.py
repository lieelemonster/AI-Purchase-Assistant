from fastapi import APIRouter

from app.config.categories import load_categories
from app.schemas.category import CategoryList

router = APIRouter(prefix="/v1")


@router.get("/categories", response_model=CategoryList)
def list_categories() -> CategoryList:
    return load_categories()

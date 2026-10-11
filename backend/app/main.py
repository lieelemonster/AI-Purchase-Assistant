from fastapi import FastAPI

from app.api.categories import router as categories_router
from app.api.health import router as health_router
from app.api.options import router as options_router

app = FastAPI(title="AI 购买助手", version="0.1.0")
app.include_router(health_router)
app.include_router(categories_router)
app.include_router(options_router)

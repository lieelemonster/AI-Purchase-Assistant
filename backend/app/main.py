import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.categories import router as categories_router
from app.api.health import router as health_router
from app.api.needs import router as needs_router
from app.api.options import router as options_router
from app.api.recommendations import router as recommendations_router

app = FastAPI(title="AI 购买助手", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=os.getenv(
        "CORS_ORIGIN_REGEX",
        r"https?://(localhost|127\.0\.0\.1)(:\d+)?|https://patrick-starai\.com",
    ),
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)
app.include_router(health_router)
app.include_router(categories_router)
app.include_router(options_router)
app.include_router(needs_router)
app.include_router(recommendations_router)

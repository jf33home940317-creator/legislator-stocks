from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.errors import register_error_handlers
from app.api.routes import meta, politicians, stocks
from app.config import settings

app = FastAPI(title="立委持股查詢 API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_origin_regex=r"http://(localhost|127\.0\.0\.1)(:\d+)?",  # 開發時任何 localhost port
    allow_methods=["GET", "PATCH"],
    allow_headers=["*"],
)
register_error_handlers(app)

for router in (meta.router, politicians.router, stocks.router):
    app.include_router(router, prefix="/api/v1")

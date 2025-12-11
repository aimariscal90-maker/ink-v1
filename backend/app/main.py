from fastapi import FastAPI

from app.core.config import get_settings
from app.api.v1.jobs import router as jobs_router

settings = get_settings()

app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    description="Ink API - Comic translation backend.",
)

app.include_router(jobs_router, prefix="/api/v1")

@app.get("/", tags=["root"])
def read_root() -> dict:
    return {"message": f"Welcome to {settings.app_name}!"}


@app.get("/health", tags=["health"])
def health_check() -> dict:
    return {"status": "ok", "environment": settings.environment}


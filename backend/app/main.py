from fastapi import FastAPI

from app.core.config import get_settings

settings = get_settings()

app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    description="Ink API - Comic translation backend.",
)

@app.get("/")
def read_root() -> dict:
    return {"message": "Welcome to the Ink API!"}

@app.get("/health", tags=["health"])
def health_check() -> dict:
    return {"status": "ok", "environment": settings.environment}

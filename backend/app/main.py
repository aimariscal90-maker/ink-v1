from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi import Request

from app.api.v1.jobs import router as jobs_router
from app.core.config import get_settings

settings = get_settings()

app = FastAPI(
    title="Ink v1 API",
    version="0.1.0",
)

# CORS configurable via `settings.allowed_origins` (definido en .env)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[str(o) for o in settings.allowed_origins],
    allow_credentials=settings.allow_credentials,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def ensure_cors_header(request: Request, call_next):
    response = await call_next(request)
    # Fallback: si por alguna razón el proxy/reversebackend remueve headers CORS,
    # asegúrate de establecerlos en la respuesta final.
    if "Access-Control-Allow-Origin" not in response.headers:
        origins = ",".join(settings.allowed_origins) if settings.allowed_origins != ["*"] else "*"
        response.headers["Access-Control-Allow-Origin"] = origins
        if settings.allow_credentials:
            response.headers["Access-Control-Allow-Credentials"] = "true"
    return response


@app.get("/health")
async def health():
    return {"status": "ok"}


app.include_router(jobs_router, prefix="/api/v1")

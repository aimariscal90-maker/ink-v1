"""Punto de entrada de la API usando FastAPI.

Este módulo crea la aplicación, configura CORS y registra los routers.
Los comentarios intentan explicar cada paso de forma que alguien sin
experiencia en backend pueda seguir el flujo con facilidad.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi import Request

from app.api.v1.jobs import router as jobs_router
from app.core.config import get_settings

settings = get_settings()

# Instancia principal de FastAPI; aquí es donde se montan rutas y middleware.
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
    """Fallback middleware that sets the CORS headers dynamically.

    - If `ALLOWED_ORIGINS` contains `*`, respond `Access-Control-Allow-Origin: *`.
    - Otherwise, if Origin is present and in the whitelist, echo it back.
    - Optionally set `Access-Control-Allow-Credentials`.
    """
    # `call_next` ejecuta la siguiente capa (rutas incluidas) y devuelve la respuesta.
    origin = request.headers.get("origin")
    response = await call_next(request)

    # If there's no Origin header, nothing to do.
    if not origin:
        return response

    allowed = settings.allowed_origins
    # Fast path: wildcard
    if allowed == ["*"]:
        response.headers["Access-Control-Allow-Origin"] = "*"
        if settings.allow_credentials:
            response.headers["Access-Control-Allow-Credentials"] = "true"
        return response

    # If a list of origins is specified, echo the origin if allowed
    try:
        origins_list = [str(o) for o in allowed]
    except Exception:
        origins_list = [str(allowed)]

    if origin in origins_list:
        response.headers["Access-Control-Allow-Origin"] = origin
        if settings.allow_credentials:
            response.headers["Access-Control-Allow-Credentials"] = "true"

    return response


@app.get("/health")
async def health():
    return {"status": "ok"}


app.include_router(jobs_router, prefix="/api/v1")

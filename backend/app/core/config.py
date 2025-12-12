from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Ink API"
    environment: str = "development"

    # Directorio base para almacenar jobs (input/output)
    data_dir: Path = Path("data/jobs")

    # Claves externas (se rellenarán vía .env en su momento)
    openai_api_key: str | None = None
    google_project_id: str | None = None
    google_credentials_file: str | None = None
    # CORS
    allowed_origins: list[str] = ["*"]
    allow_credentials: bool = False

    model_config = SettingsConfigDict(env_file=".env", case_sensitive=False)






@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    # Accept comma separated `ALLOWED_ORIGINS` env value as a string
    ao = settings.allowed_origins
    if isinstance(ao, str):
        settings.allowed_origins = [s.strip() for s in ao.split(",") if s.strip()]
    return settings

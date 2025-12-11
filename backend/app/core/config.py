from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    app_name: str = "Ink API"
    environment: str = "development"

    # Directorio base para almacenar jobs (input/output)
    data_dir: Path = Path("data/jobs")

    # Claves externas (se rellenarán vía .env en su momento)
    openai_api_key: str | None = None
    google_project_id: str | None = None
    google_credentials_file: str | None = None

    class Config:
        env_file = ".env"
        case_sensitive = False


@lru_cache
def get_settings() -> Settings:
    return Settings()

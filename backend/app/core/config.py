"""Carga de configuración de la aplicación.

Usa `pydantic-settings` para leer valores desde `.env` o variables de
entorno. Las constantes y comentarios aclaran para qué sirve cada campo
de forma que resulte legible para personas sin contexto previo.
"""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Contenedor tipado para todas las opciones configurables."""

    app_name: str = "Ink API"
    environment: str = "development"

    # Directorio base para almacenar archivos de entrada y resultados por job
    data_dir: Path = Path("data/jobs")

    # Claves externas (se rellenarán vía .env en su momento)
    openai_api_key: str | None = None
    google_project_id: str | None = None
    google_credentials_file: str | None = None
    # CORS
    allowed_origins: list[str] = ["*"]
    allow_credentials: bool = False

    # Parámetros para afinado del OCR y sus filtros
    ocr_min_confidence: float = 0.55
    ocr_classifier_min_confidence: float = 0.4
    ocr_min_area_ratio: float = 0.0004
    ocr_max_area_ratio: float = 0.25
    ocr_min_width_px: int = 8
    ocr_min_height_px: int = 8
    ocr_merge_gap_px: int = 16
    ocr_line_tolerance_px: int = 10
    ocr_block_gap_px: int = 18
    ocr_min_x_overlap_ratio: float = 0.15
    ocr_merge_max_area_growth_ratio: float = 1.6
    ocr_merge_min_height_ratio: float = 0.55
    ocr_merge_max_center_distance_ratio: float = 0.45
    ocr_merge_min_alignment_overlap: float = 0.12
    ocr_merge_max_characters: int = 320
    ocr_merge_gutter_gap_px: int = 48
    ocr_enable_fallback: bool = True
    ocr_filter_non_dialogue: bool = True

    # Le indicamos a Pydantic que lea automáticamente las variables de entorno
    model_config = SettingsConfigDict(env_file=".env", case_sensitive=False)






@lru_cache
def get_settings() -> Settings:
    """Crea (y memoriza) la configuración de forma perezosa.

    Usamos `lru_cache` para que sólo se construya una instancia por proceso,
    evitando relecturas repetidas de `.env`. También normalizamos la lista de
    orígenes permitidos para CORS cuando llega como cadena separada por comas.
    """

    settings = Settings()
    # Accept comma separated `ALLOWED_ORIGINS` env value as a string
    ao = settings.allowed_origins
    if isinstance(ao, str):
        settings.allowed_origins = [s.strip() for s in ao.split(",") if s.strip()]
    return settings

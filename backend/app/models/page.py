from __future__ import annotations

"""Modelos relacionados con páginas individuales rasterizadas."""

from pathlib import Path
from pydantic import BaseModel, ConfigDict


class PageImage(BaseModel):
    """
    Representa una página del cómic ya rasterizada a imagen.
    """

    index: int  # 0-based
    image_path: Path  # Ruta en disco de la imagen de la página
    width: int | None = None  # Se rellena al importar
    height: int | None = None

    model_config = ConfigDict(arbitrary_types_allowed=True)

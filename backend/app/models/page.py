from __future__ import annotations

from pathlib import Path
from pydantic import BaseModel, ConfigDict


class PageImage(BaseModel):
    """
    Representa una página del cómic ya rasterizada a imagen.
    """

    index: int  # 0-based
    image_path: Path
    width: int | None = None
    height: int | None = None

    model_config = ConfigDict(arbitrary_types_allowed=True)

from __future__ import annotations

from pathlib import Path
from typing import List

from app.models.text import TranslatedRegion


class RenderService:
    """
    Se encarga de pintar el texto traducido sobre la imagen original.
    """

    def render_page(
        self,
        input_image: Path,
        regions: List[TranslatedRegion],
        output_image: Path | None = None,
    ) -> Path:
        """
        Devuelve la ruta a la imagen traducida.
        """
        raise NotImplementedError("Render service not implemented yet")

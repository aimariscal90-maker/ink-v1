from __future__ import annotations

from pathlib import Path
from typing import List

from app.models.text import TextRegion


class OcrService:
    """
    Encapsula llamadas al OCR (Google Vision, etc.).
    """

    def extract_text_regions(self, image_path: Path) -> List[TextRegion]:
        """
        Dada una imagen de página, devuelve regiones de texto detectadas.
        """
        raise NotImplementedError("OCR service not implemented yet")

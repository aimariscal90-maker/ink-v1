from __future__ import annotations

from pathlib import Path
from typing import List

from app.models.page import PageImage


class ExportService:
    """
    Exporta la lista de imágenes traducidas a un archivo final (PDF o CBZ).
    """

    def export_pdf(self, pages: List[PageImage], output_path: Path) -> Path:
        """
        Crea un PDF a partir de las imágenes en orden.
        """
        raise NotImplementedError("PDF export not implemented yet")

    def export_cbz(self, pages: List[PageImage], output_path: Path) -> Path:
        """
        Crea un CBZ (ZIP de imágenes) a partir de las imágenes en orden.
        """
        raise NotImplementedError("CBZ export not implemented yet")

from __future__ import annotations

from pathlib import Path
from typing import List

from PIL import Image

from app.models.page import PageImage


class ExportService:
    """
    Exporta la lista de imágenes traducidas a un archivo final (PDF o CBZ).
    """

    def export_pdf(self, pages: List[PageImage], output_path: Path) -> Path:
        """
        Crea un PDF a partir de las imágenes de las páginas, en orden.
        """
        if not pages:
            raise ValueError("No pages to export to PDF")

        # Nos aseguramos de que el directorio existe
        output_path.parent.mkdir(parents=True, exist_ok=True)

        # Ordenamos por índice por si acaso
        pages_sorted = sorted(pages, key=lambda p: p.index)

        images: list[Image.Image] = []
        try:
            for page in pages_sorted:
                img = Image.open(page.image_path)
                if img.mode != "RGB":
                    img = img.convert("RGB")
                images.append(img)

            first, *rest = images
            # Guardar el PDF
            first.save(output_path, save_all=True, append_images=rest)
        finally:
            # Cerrar siempre las imágenes
            for img in images:
                try:
                    img.close()
                except Exception:
                    pass

        return output_path

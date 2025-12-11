from __future__ import annotations

from pathlib import Path
from typing import List

from PIL import Image
import zipfile

from app.models.page import PageImage


class ExportService:
    """
    Exporta la lista de imágenes traducidas a un archivo final (PDF o CBZ).
    """

    def export_pdf(self, pages: List[PageImage], output_path: Path) -> Path:
        """
        Crea un PDF a partir de las imágenes en orden.
        """
        if not pages:
            raise ValueError("No pages to export to PDF")

        output_path.parent.mkdir(parents=True, exist_ok=True)

        # Aseguramos orden por índice
        pages_sorted = sorted(pages, key=lambda p: p.index)

        images: list[Image.Image] = []
        try:
            for page in pages_sorted:
                img = Image.open(page.image_path)
                if img.mode != "RGB":
                    img = img.convert("RGB")
                images.append(img)

            first, *rest = images
            first.save(output_path, save_all=True, append_images=rest)
        finally:
            for img in images:
                try:
                    img.close()
                except Exception:
                    pass

        return output_path

    def export_cbz(self, pages: List[PageImage], output_path: Path) -> Path:
        """
        Crea un CBZ (ZIP de imágenes) a partir de las imágenes en orden.
        """
        if not pages:
            raise ValueError("No pages to export to CBZ")

        output_path.parent.mkdir(parents=True, exist_ok=True)
        pages_sorted = sorted(pages, key=lambda p: p.index)

        with zipfile.ZipFile(output_path, "w") as zf:
            for page in pages_sorted:
                ext = page.image_path.suffix or ".png"
                arcname = f"page_{page.index:04d}{ext}"
                zf.write(page.image_path, arcname=arcname)

        return output_path

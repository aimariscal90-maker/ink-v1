from __future__ import annotations

from pathlib import Path
from typing import List

import fitz  # PyMuPDF
from PIL import Image
import rarfile
import zipfile

from app.core.enums import JobType
from app.models.page import PageImage


# Extensiones de imagen que aceptaremos en cómics
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}


class ImportService:
    """
    Convierte el archivo de entrada (PDF, CBR, CBZ)
    en una lista ordenada de PageImage, guardando
    las imágenes en work_dir / "pages".
    """

    def __init__(self, work_dir: Path) -> None:
        self.work_dir = work_dir
        self.pages_dir = self.work_dir / "pages"
        self.pages_dir.mkdir(parents=True, exist_ok=True)

    def import_file(self, input_path: Path, job_type: JobType) -> List[PageImage]:
        """
        Punto de entrada principal. En función del tipo de job,
        delega en PDF o cómic.
        """
        if job_type == JobType.PDF:
            return self._import_pdf(input_path)
        elif job_type == JobType.COMIC:
            return self._import_comic(input_path)
        else:
            raise ValueError(f"Unsupported JobType: {job_type}")

    # ---------- PDF ----------

    def _import_pdf(self, input_path: Path) -> List[PageImage]:
        """
        Importa un PDF: rasteriza cada página a una imagen PNG.
        """
        if not input_path.exists():
            raise FileNotFoundError(f"PDF not found: {input_path}")

        doc = fitz.open(input_path)
        pages: List[PageImage] = []

        # DPI razonable para cómic (no reventar memoria pero que se vea bien)
        dpi = 200

        for page_index in range(len(doc)):
            page = doc.load_page(page_index)
            pix = page.get_pixmap(dpi=dpi)

            output_path = self.pages_dir / f"page_{page_index:04d}.png"
            pix.save(output_path)

            # Obtener dimensiones reales
            width, height = pix.width, pix.height

            pages.append(
                PageImage(
                    index=page_index,
                    image_path=output_path,
                    width=width,
                    height=height,
                )
            )

        doc.close()
        return pages

    # ---------- CÓMIC (CBR/CBZ) ----------

    def _import_comic(self, input_path: Path) -> List[PageImage]:
        """
        Importa un archivo de cómic (CBR/CBZ): extrae imágenes y las
        devuelve ordenadas como PageImage.
        """
        if not input_path.exists():
            raise FileNotFoundError(f"Comic file not found: {input_path}")

        ext = input_path.suffix.lower()

        if ext == ".cbz":
            return self._import_cbz(input_path)
        elif ext == ".cbr":
            return self._import_cbr(input_path)
        else:
            raise ValueError(f"Unsupported comic extension: {ext}")

    def _import_cbz(self, input_path: Path) -> List[PageImage]:
        pages: List[PageImage] = []

        with zipfile.ZipFile(input_path, "r") as zf:
            # Filtrar solo entradas que parecen imágenes
            image_names = [
                name
                for name in zf.namelist()
                if Path(name).suffix.lower() in IMAGE_EXTENSIONS
            ]
            # Orden por nombre para mantener el orden de páginas
            image_names.sort()

            for idx, name in enumerate(image_names):
                # Extraer a memoria y guardar como archivo normal
                output_path = self.pages_dir / f"page_{idx:04d}{Path(name).suffix.lower()}"
                with zf.open(name) as src, open(output_path, "wb") as dst:
                    dst.write(src.read())

                width, height = self._get_image_size(output_path)

                pages.append(
                    PageImage(
                        index=idx,
                        image_path=output_path,
                        width=width,
                        height=height,
                    )
                )

        return pages

    def _import_cbr(self, input_path: Path) -> List[PageImage]:
        pages: List[PageImage] = []

        # rarfile necesita 'unrar' o 'bsdtar' instalado en el sistema;
        # en Codespaces suele estar, si no, se puede cambiar por otra cosa.
        with rarfile.RarFile(input_path) as rf:
            image_names = [
                info.filename
                for info in rf.infolist()
                if Path(info.filename).suffix.lower() in IMAGE_EXTENSIONS
            ]
            image_names.sort()

            for idx, name in enumerate(image_names):
                output_path = self.pages_dir / f"page_{idx:04d}{Path(name).suffix.lower()}"
                with rf.open(name) as src, open(output_path, "wb") as dst:
                    dst.write(src.read())

                width, height = self._get_image_size(output_path)

                pages.append(
                    PageImage(
                        index=idx,
                        image_path=output_path,
                        width=width,
                        height=height,
                    )
                )

        return pages

    # ---------- Helpers ----------

    def _get_image_size(self, path: Path) -> tuple[int, int]:
        """
        Devuelve (width, height) de una imagen usando Pillow.
        """
        with Image.open(path) as img:
            return img.width, img.height

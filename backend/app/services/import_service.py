from __future__ import annotations

from pathlib import Path
from typing import List

from app.core.enums import JobType
from app.models.page import PageImage


class ImportService:
    """
    Se encarga de convertir el archivo de entrada (PDF, CBR, CBZ)
    en una lista ordenada de PageImage.
    """

    def __init__(self, work_dir: Path) -> None:
        self.work_dir = work_dir

    def import_file(self, input_path: Path, job_type: JobType) -> List[PageImage]:
        """
        Punto de entrada principal. En función del tipo de job,
        delega en PDF o comic.
        """
        if job_type == JobType.PDF:
            return self._import_pdf(input_path)
        elif job_type == JobType.COMIC:
            return self._import_comic(input_path)
        else:
            raise ValueError(f"Unsupported JobType: {job_type}")

    def _import_pdf(self, input_path: Path) -> List[PageImage]:
        """
        Importa un PDF: rasteriza cada página a una imagen.
        """
        raise NotImplementedError("PDF import not implemented yet")

    def _import_comic(self, input_path: Path) -> List[PageImage]:
        """
        Importa un archivo de cómic (CBR/CBZ): extrae las imágenes.
        """
        raise NotImplementedError("Comic import not implemented yet")

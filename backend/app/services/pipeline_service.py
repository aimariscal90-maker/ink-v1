from __future__ import annotations

from pathlib import Path
from typing import List

from app.core.config import get_settings
from app.core.enums import JobType
from app.models.job import Job
from app.models.page import PageImage
from app.services.job_service import JobService
from app.services.import_service import ImportService
from app.services.ocr_service import OcrService
from app.services.translation_service import TranslationService
from app.services.render_service import RenderService
from app.services.export_service import ExportService


class PipelineService:
    """
    Orquesta el pipeline de procesamiento de un Job:
    import -> ocr -> traducción -> render -> export.
    """

    def __init__(self, job_service: JobService) -> None:
        settings = get_settings()
        self.data_dir: Path = settings.data_dir
        self.job_service = job_service

        self.ocr_service = OcrService()
        self.translation_service = TranslationService()
        self.render_service = RenderService()
        self.export_service = ExportService()

    def process_job(self, job_id: str) -> Job:
        """
        Procesa un job de forma síncrona. De momento solo soporta PDF.
        """

        job = self.job_service.get_job(job_id)
        if not job:
            raise ValueError(f"Job not found: {job_id}")

        if job.type != JobType.PDF:
            # Mañana (día 9) añadimos soporte para cómics
            raise NotImplementedError("Only PDF jobs are supported at the moment")

        job_dir = self.data_dir / job.id
        job_dir.mkdir(parents=True, exist_ok=True)

        importer = ImportService(work_dir=job_dir)

        # Marcamos como en procesamiento
        job.mark_processing()
        self.job_service.update_job(job)

        try:
            # 1) Importar PDF -> imágenes
            pages = importer.import_file(job.input_path, job.type)

            # 2) Para cada página: OCR -> Traducción -> Render
            translated_pages: List[PageImage] = []

            for page in pages:
                regions = self.ocr_service.extract_text_regions(page.image_path)

                translated_regions = self.translation_service.translate_regions(
                    regions=regions,
                    source_lang="en",
                    target_lang="es",
                )

                output_img_path = page.image_path.with_name(
                    page.image_path.stem + "_translated.png"
                )

                self.render_service.render_page(
                    input_image=page.image_path,
                    regions=translated_regions,
                    output_image=output_img_path,
                )

                translated_pages.append(
                    PageImage(
                        index=page.index,
                        image_path=output_img_path,
                        width=page.width,
                        height=page.height,
                    )
                )

            # 3) Exportar a PDF
            output_path = job_dir / "output.pdf"
            self.export_service.export_pdf(translated_pages, output_path)

            # 4) Marcar como completado
            job.mark_completed(output_path=output_path, num_pages=len(translated_pages))
            self.job_service.update_job(job)

            return job

        except Exception as e:
            # Marcamos el job como fallido y re-lanzamos
            job.mark_failed(str(e))
            self.job_service.update_job(job)
            raise

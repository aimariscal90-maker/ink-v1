from __future__ import annotations

import logging
from pathlib import Path
from time import perf_counter
from typing import List

from app.core.config import get_settings
from app.core.enums import JobType
from app.models.job import Job
from app.models.page import PageImage
from app.models.text import TextRegion, TranslatedRegion
from app.services.job_service import JobService
from app.services.import_service import ImportService
from app.services.ocr_service import OcrService
from app.services.translation_service import TranslationService
from app.services.render_service import RenderResult, RenderService
from app.services.export_service import ExportService


class PipelineService:
    """
    Orquesta el pipeline de procesamiento de un Job:
    import -> ocr -> traducción -> render -> export.
    De momento solo soporta PDF.
    """

    def __init__(self, job_service: JobService) -> None:
        settings = get_settings()
        # directorio raíz donde se guardan los jobs, p.ej: data/jobs
        self.data_dir: Path = settings.data_dir
        self.job_service = job_service

        self.ocr_service = OcrService()
        self.translation_service = TranslationService()
        self.render_service = RenderService()
        self.export_service = ExportService()

    # ---------- NÚCLEO DEL PIPELINE (trabaja con un Job ya cargado) ----------

    def run_pipeline(self, job: Job) -> Job:
        """
        Pipeline completo:
        1) Importar páginas
        2) OCR
        3) Traducir
        4) Renderizar
        5) Exportar PDF final
        """

        if job.type != JobType.PDF:
            # Más adelante añadiremos soporte CBR/CBZ
            raise NotImplementedError("Only PDF jobs are supported at the moment")

        # Carpeta de trabajo concreta del job
        job_dir = self.data_dir / job.id
        job_dir.mkdir(parents=True, exist_ok=True)

        importer = ImportService(work_dir=job_dir)

        # Marcar como en proceso
        job.mark_processing()
        job.progress_stage = "import"
        job.progress_current = 0
        job.progress_total = None
        self.job_service.update_job(job)

        try:
            # 1) Importar PDF -> imágenes
            import_start = perf_counter()
            pages: List[PageImage] = importer.import_file(job.input_path, job.type)
            job.timing_import_ms = int((perf_counter() - import_start) * 1000)
            job.progress_total = len(pages)
            job.pages_total = len(pages)
            job.progress_stage = "import"
            job.progress_current = 0
            self.job_service.update_job(job)

            translated_pages: List[PageImage] = []
            job.regions_total = 0
            ocr_time = 0.0
            translate_time = 0.0
            render_time = 0.0
            qa_overflow_total = 0
            qa_retry_total = 0
            invalid_bbox_total = 0
            discarded_region_total = 0
            merged_region_total = 0
            regions_detected_raw_total = 0
            regions_after_grouping_total = 0
            regions_after_filter_total = 0
            regions_after_merge_total = 0

            for page in pages:
                page_number = page.index + 1

                # 2) OCR
                job.progress_current = page_number
                job.progress_stage = "ocr"
                self.job_service.update_job(job)
                ocr_started_at = perf_counter()
                regions: List[TextRegion] = self.ocr_service.extract_text_regions(
                    page.image_path
                )
                ocr_time += perf_counter() - ocr_started_at
                job.regions_total += len(regions)
                invalid_bbox_total += self.ocr_service.last_invalid_bbox_count
                discarded_region_total += self.ocr_service.last_discarded_region_count
                merged_region_total += self.ocr_service.last_merged_region_count
                regions_detected_raw_total += self.ocr_service.regions_detected_raw
                regions_after_grouping_total += (
                    self.ocr_service.regions_after_paragraph_grouping
                )
                regions_after_filter_total += self.ocr_service.regions_after_filter
                regions_after_merge_total += self.ocr_service.regions_after_merge

                # 3) Traducción (batch por página)
                job.progress_stage = "translate"
                self.job_service.update_job(job)
                translate_started_at = perf_counter()
                translated_regions: List[TranslatedRegion] = (
                    self.translation_service.translate_regions_batch(
                        regions=regions,
                        source_lang="en",
                        target_lang="es",
                    )
                )
                translate_time += perf_counter() - translate_started_at

                # 4) Renderizar imagen traducida
                job.progress_stage = "render"
                self.job_service.update_job(job)
                output_img_path = page.image_path.with_name(
                    page.image_path.stem + "_translated.png"
                )

                render_started_at = perf_counter()
                render_result: RenderResult = self.render_service.render_page(
                    input_image=page.image_path,
                    regions=translated_regions,
                    output_image=output_img_path,
                )
                render_time += perf_counter() - render_started_at
                qa_overflow_total += render_result.qa_overflow_count
                qa_retry_total += render_result.qa_retry_count
                invalid_bbox_total += render_result.invalid_bbox_count
                discarded_region_total += render_result.discarded_region_count

                translated_pages.append(
                    PageImage(
                        index=page.index,
                        image_path=render_result.output_image,
                        width=page.width,
                        height=page.height,
                    )
                )

            # 5) Exportar PDF final
            job.progress_stage = "export"
            job.progress_current = job.progress_total or job.progress_current
            self.job_service.update_job(job)
            export_started_at = perf_counter()
            output_path = job_dir / "output.pdf"
            self.export_service.export_pdf(translated_pages, output_path)
            job.timing_ocr_ms = int(ocr_time * 1000)
            job.timing_translate_ms = int(translate_time * 1000)
            job.timing_render_ms = int(render_time * 1000)
            job.timing_export_ms = int((perf_counter() - export_started_at) * 1000)
            job.qa_overflow_count = qa_overflow_total
            job.qa_retry_count = qa_retry_total
            job.invalid_bbox_count = invalid_bbox_total
            job.discarded_region_count = discarded_region_total
            job.merged_region_count = merged_region_total
            job.regions_detected_raw = regions_detected_raw_total
            job.regions_after_paragraph_grouping = regions_after_grouping_total
            job.regions_after_filter = regions_after_filter_total
            job.regions_after_merge = regions_after_merge_total

            # Marcar como completado
            job.mark_completed(output_path=output_path, num_pages=len(translated_pages))
            self.job_service.update_job(job)

            return job

        except Exception as e:
            # Marcamos el job como fallido y relanzamos
            job.mark_failed(str(e))
            self.job_service.update_job(job)
            raise

    # ---------- API USADA POR EL ENDPOINT (/jobs/{job_id}/process) ----------

    def process_job(self, job_id: str) -> Job:
        """
        Busca el job por id y ejecuta el pipeline completo.
        """

        job = self.job_service.get_job(job_id)
        if not job:
            raise ValueError(f"Job not found: {job_id}")

        return self.run_pipeline(job)

    def process_job_background(self, job_id: str) -> None:
        """Run the pipeline in a background task, logging failures safely."""

        try:
            self.process_job(job_id)
        except Exception:
            logging.exception("Background job %s failed", job_id)

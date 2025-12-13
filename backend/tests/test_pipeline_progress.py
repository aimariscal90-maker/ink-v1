from pathlib import Path

import app.services.pipeline_service as pipeline_service
from app.core.enums import JobType, OutputFormat
from app.models.page import PageImage
from app.models.text import BBox, TextRegion, TranslatedRegion
from app.services.job_service import JobService


class TrackingJobService(JobService):
    def __init__(self) -> None:
        super().__init__()
        self.saved_progress = []

    def update_job(self, job):  # type: ignore[override]
        super().update_job(job)
        self.saved_progress.append((job.progress_stage, job.progress_current))


class StubImportService:
    def __init__(self, work_dir: Path) -> None:
        self.work_dir = work_dir

    def import_file(self, input_path: Path, job_type: JobType):  # type: ignore[override]
        return [
            PageImage(index=0, image_path=self.work_dir / "page0.png"),
            PageImage(index=1, image_path=self.work_dir / "page1.png"),
        ]


class StubOcrService:
    def extract_text_regions(self, image_path: Path):  # type: ignore[override]
        return [
            TextRegion(
                id="1",
                text="hello",
                bbox=BBox(x_min=0.0, y_min=0.0, x_max=1.0, y_max=1.0),
                confidence=1.0,
            )
        ]


class StubTranslationService:
    def translate_regions(self, regions, source_lang: str, target_lang: str):  # type: ignore[override]
        return [
            TranslatedRegion(
                id=r.id,
                original_text=r.text,
                translated_text=f"{r.text}-es",
                bbox=r.bbox,
                confidence=r.confidence,
            )
            for r in regions
        ]

    def translate_regions_batch(self, regions, source_lang: str, target_lang: str):  # type: ignore[override]
        return self.translate_regions(regions, source_lang, target_lang)


class StubRenderService:
    def render_page(self, input_image: Path, regions, output_image: Path):  # type: ignore[override]
        output_image.touch()


class StubExportService:
    def export_pdf(self, pages, output_path: Path):  # type: ignore[override]
        output_path.touch()


def test_pipeline_tracks_progress(monkeypatch, tmp_path):
    class DummySettings:
        data_dir = tmp_path

    monkeypatch.setattr(pipeline_service, "get_settings", lambda: DummySettings())
    monkeypatch.setattr(pipeline_service, "ImportService", StubImportService)
    monkeypatch.setattr(pipeline_service, "OcrService", lambda: StubOcrService())
    monkeypatch.setattr(pipeline_service, "TranslationService", lambda: StubTranslationService())
    monkeypatch.setattr(pipeline_service, "RenderService", lambda: StubRenderService())
    monkeypatch.setattr(pipeline_service, "ExportService", lambda: StubExportService())

    job_service = TrackingJobService()
    pipeline = pipeline_service.PipelineService(job_service)

    job = job_service.create_job(
        job_type=JobType.PDF,
        output_format=OutputFormat.PDF,
        input_path=tmp_path / "input.pdf",
    )

    result = pipeline.run_pipeline(job)

    assert result.progress_total == 2
    assert result.progress_current == 2
    assert result.progress_stage == "completed"

    stages = [stage for stage, _ in job_service.saved_progress]
    assert "ocr" in stages
    assert "translate" in stages
    assert "render" in stages
    assert "export" in stages
    assert "completed" in stages

    progress_values = [value for _, value in job_service.saved_progress]
    assert 1 in progress_values
    assert progress_values[-1] == 2

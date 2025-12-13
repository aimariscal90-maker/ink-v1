from __future__ import annotations

from pathlib import Path
from typing import Optional

from fastapi import APIRouter, UploadFile, File, HTTPException, status, BackgroundTasks

from app.core.enums import JobType, OutputFormat

from fastapi.responses import FileResponse

from app.services.job_store import job_service
from app.services.pipeline_service import PipelineService
from app.models.job import Job
from app.core.config import get_settings

router = APIRouter(prefix="/jobs", tags=["jobs"])

settings = get_settings()
pipeline_service = PipelineService(job_service=job_service)

def detect_job_type(filename: str) -> JobType:
    """
    Determina si el archivo es PDF o cómic (CBR/CBZ).
    """
    ext = filename.lower().split(".")[-1]
    if ext == "pdf":
        return JobType.PDF
    if ext in ("cbr", "cbz"):
        return JobType.COMIC
    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail=f"Unsupported file type: {ext}",
    )


def detect_output_format(job_type: JobType) -> OutputFormat:
    """
    PDF → exportamos PDF
    CBR/CBZ → exportamos CBZ
    """
    if job_type == JobType.PDF:
        return OutputFormat.PDF
    return OutputFormat.CBZ


@router.post("", summary="Upload a comic and create a processing job")
async def create_job(file: UploadFile = File(...)) -> dict:
    job_type = detect_job_type(file.filename)
    output_format = detect_output_format(job_type)

    # Crear directorio para el job
    data_dir = settings.data_dir
    data_dir.mkdir(parents=True, exist_ok=True)

    # Crear Job vacío
    job: Job = job_service.create_job(
        job_type=job_type,
        output_format=output_format,
        input_path=Path(""),
    )

    # Carpeta del job
    job_dir = data_dir / job.id
    job_dir.mkdir(parents=True, exist_ok=True)

    # Guardar archivo subido
    input_ext = file.filename.split(".")[-1].lower()
    input_path = job_dir / f"input.{input_ext}"

    file_bytes = await file.read()
    if not file_bytes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded file is empty.",
        )

    with open(input_path, "wb") as f:
        f.write(file_bytes)

    # Actualizar job con ruta del archivo
    job.input_path = input_path
    job_service.update_job(job)

    return {
        "job_id": job.id,
        "status": job.status,
        "type": job.type,
        "output_format": job.output_format,
        "progress_current": job.progress_current,
        "progress_total": job.progress_total,
        "progress_stage": job.progress_stage,
        "timing_import_ms": job.timing_import_ms,
        "timing_ocr_ms": job.timing_ocr_ms,
        "timing_translate_ms": job.timing_translate_ms,
        "timing_render_ms": job.timing_render_ms,
        "timing_export_ms": job.timing_export_ms,
        "pages_total": job.pages_total,
        "regions_total": job.regions_total,
    }


@router.get("/{job_id}", summary="Get job status")
async def get_job_status(job_id: str) -> dict:
    job = job_service.get_job(job_id)
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Job not found.",
        )

    return {
        "job_id": job.id,
        "status": job.status,
        "type": job.type,
        "output_format": job.output_format,
        "num_pages": job.num_pages,
        "error_message": job.error_message,
        "output_path": str(job.output_path) if job.output_path else None,
        "progress_current": job.progress_current,
        "progress_total": job.progress_total,
        "progress_stage": job.progress_stage,
        "timing_import_ms": job.timing_import_ms,
        "timing_ocr_ms": job.timing_ocr_ms,
        "timing_translate_ms": job.timing_translate_ms,
        "timing_render_ms": job.timing_render_ms,
        "timing_export_ms": job.timing_export_ms,
        "pages_total": job.pages_total,
        "regions_total": job.regions_total,
    }


@router.post(
    "/{job_id}/process",
    summary="Process a job asynchronously (PDF only for now)",
    status_code=status.HTTP_202_ACCEPTED,
)
async def process_job(job_id: str, background_tasks: BackgroundTasks) -> dict:
    job = job_service.get_job(job_id)
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Job not found.",
        )

    try:
        job.mark_processing()
        job.progress_stage = "import"
        job.progress_current = 0
        job.progress_total = None
        job_service.update_job(job)

        background_tasks.add_task(pipeline_service.process_job_background, job_id)
    except NotImplementedError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Job processing failed: {e}",
        )

    return {
        "job_id": job.id,
        "status": job.status,
        "type": job.type,
        "output_format": job.output_format,
        "num_pages": job.num_pages,
        "error_message": job.error_message,
        "output_path": str(job.output_path) if job.output_path else None,
        "progress_current": job.progress_current,
        "progress_total": job.progress_total,
        "progress_stage": job.progress_stage,
        "timing_import_ms": job.timing_import_ms,
        "timing_ocr_ms": job.timing_ocr_ms,
        "timing_translate_ms": job.timing_translate_ms,
        "timing_render_ms": job.timing_render_ms,
        "timing_export_ms": job.timing_export_ms,
        "pages_total": job.pages_total,
        "regions_total": job.regions_total,
    }

@router.get("/{job_id}/download", summary="Download processed file")
async def download_job_output(job_id: str):
    job = job_service.get_job(job_id)
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Job not found.",
        )

    if not job.output_path:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Job has no output yet.",
        )

    output_path = Path(job.output_path)
    if not output_path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Output file not found on disk.",
        )

    if job.output_format == OutputFormat.PDF:
        media_type = "application/pdf"
        filename = f"{job.id}.pdf"
    elif job.output_format == OutputFormat.CBZ:
        media_type = "application/zip"
        filename = f"{job.id}.cbz"
    else:
        media_type = "application/octet-stream"
        filename = output_path.name

    return FileResponse(
        path=output_path,
        media_type=media_type,
        filename=filename,
    )



# NOTE: process_job already defined above with the correct route.

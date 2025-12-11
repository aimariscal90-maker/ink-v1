from __future__ import annotations

from pathlib import Path
from typing import Optional

from fastapi import APIRouter, UploadFile, File, HTTPException, status

from app.core.enums import JobType, OutputFormat
from app.services.job_service import JobService
from app.models.job import Job
from app.core.config import get_settings

router = APIRouter()
settings = get_settings()

# TEMP: JobService global para MVP (más adelante se inyecta)
job_service = JobService()


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


@router.post("/jobs", summary="Upload a comic and create a processing job")
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
    }


@router.get("/jobs/{job_id}", summary="Get job status")
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
    }

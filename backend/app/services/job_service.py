from __future__ import annotations

from typing import Dict, List, Optional
from pathlib import Path
from uuid import uuid4

from app.core.enums import JobStatus, JobType, OutputFormat
from app.models.job import Job


class JobService:
    """
    Gestión de jobs. MVP: almacenamiento en memoria.
    Más adelante se puede sustituir por BD persistente.
    """

    def __init__(self) -> None:
        self._jobs: Dict[str, Job] = {}

    def create_job(
        self,
        job_type: JobType,
        output_format: OutputFormat,
        input_path: Path,
    ) -> Job:
        job_id = str(uuid4())
        job = Job(
            id=job_id,
            type=job_type,
            output_format=output_format,
            input_path=input_path,
            status=JobStatus.UPLOADED,
        )
        self._jobs[job_id] = job
        return job

    def get_job(self, job_id: str) -> Optional[Job]:
        return self._jobs.get(job_id)

    def update_job(self, job: Job) -> None:
        # En un futuro, aquí iría la persistencia real (DB).
        self._jobs[job.id] = job

    def list_jobs(self) -> List[Job]:
        return list(self._jobs.values())

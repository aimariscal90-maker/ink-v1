from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field

from app.core.enums import JobStatus, JobType, OutputFormat


class Job(BaseModel):
    id: str
    status: JobStatus = JobStatus.UPLOADED
    type: JobType
    output_format: OutputFormat

    input_path: Path
    output_path: Optional[Path] = None

    num_pages: Optional[int] = None
    error_message: Optional[str] = None

    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        arbitrary_types_allowed = True

    def mark_processing(self) -> None:
        self.status = JobStatus.PROCESSING
        self.updated_at = datetime.utcnow()

    def mark_completed(self, output_path: Path, num_pages: int) -> None:
        self.status = JobStatus.COMPLETED
        self.output_path = output_path
        self.num_pages = num_pages
        self.updated_at = datetime.utcnow()

    def mark_failed(self, error_message: str) -> None:
        self.status = JobStatus.FAILED
        self.error_message = error_message
        self.updated_at = datetime.utcnow()

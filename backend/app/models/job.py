from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

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

    progress_current: int = 0
    progress_total: Optional[int] = None
    progress_stage: Optional[str] = None

    # Métricas
    timing_import_ms: Optional[int] = None
    timing_ocr_ms: Optional[int] = None
    timing_translate_ms: Optional[int] = None
    timing_render_ms: Optional[int] = None
    timing_export_ms: Optional[int] = None

    pages_total: int = 0
    regions_total: int = 0
    regions_detected_raw: int = 0
    regions_after_paragraph_grouping: int = 0
    regions_after_filter: int = 0
    regions_after_merge: int = 0
    qa_overflow_count: int = 0
    qa_retry_count: int = 0
    invalid_bbox_count: int = 0
    discarded_region_count: int = 0
    merged_region_count: int = 0
    qa_overflow_count: int = 0
    qa_retry_count: int = 0

    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    model_config = ConfigDict(arbitrary_types_allowed=True)

    def mark_processing(self) -> None:
        self.status = JobStatus.PROCESSING
        self.updated_at = datetime.now(timezone.utc)

    def mark_completed(self, output_path: Path, num_pages: int) -> None:
        self.status = JobStatus.COMPLETED
        self.output_path = output_path
        self.num_pages = num_pages
        self.progress_stage = "completed"
        if self.progress_total is not None:
            self.progress_current = self.progress_total
        self.updated_at = datetime.now(timezone.utc)

    def mark_failed(self, error_message: str) -> None:
        self.status = JobStatus.FAILED
        self.error_message = error_message
        self.progress_stage = "failed"
        self.updated_at = datetime.now(timezone.utc)

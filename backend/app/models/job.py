"""Definición del modelo de datos de un Job.

Un job representa una ejecución completa del pipeline (importar, OCR,
traducir, renderizar, exportar). Se almacena en memoria, por lo que
mantener los campos documentados ayuda a entender qué se persiste y por
qué cambia cada atributo durante el procesamiento.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from app.core.enums import JobStatus, JobType, OutputFormat


class Job(BaseModel):
    """Modelo principal que describe el estado de un trabajo."""

    id: str
    status: JobStatus = JobStatus.UPLOADED  # Estado actual en el ciclo de vida
    type: JobType  # Tipo de archivo de entrada
    output_format: OutputFormat  # Formato final a exportar

    input_path: Path  # Ruta al archivo original subido
    output_path: Optional[Path] = None  # Se rellena al terminar el pipeline

    num_pages: Optional[int] = None  # Número de páginas del documento
    error_message: Optional[str] = None  # Texto explicando por qué falló

    progress_current: int = 0  # Progreso actual (páginas procesadas)
    progress_total: Optional[int] = None  # Total esperado de páginas
    progress_stage: Optional[str] = None  # Paso del pipeline en curso

    # Métricas de tiempo por etapa (milisegundos)
    timing_import_ms: Optional[int] = None
    timing_ocr_ms: Optional[int] = None
    timing_translate_ms: Optional[int] = None
    timing_render_ms: Optional[int] = None
    timing_export_ms: Optional[int] = None

    # Estadísticas para facilitar debug y QA
    pages_total: int = 0
    regions_total: int = 0
    regions_detected_raw: int = 0
    regions_after_paragraph_grouping: int = 0
    regions_after_filter: int = 0
    regions_after_merge: int = 0
    invalid_bbox_count: int = 0
    discarded_region_count: int = 0
    merged_region_count: int = 0
    ocr_fallback_used_count: int = 0
    qa_overflow_count: int = 0
    qa_retry_count: int = 0

    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    model_config = ConfigDict(arbitrary_types_allowed=True)

    def mark_processing(self) -> None:
        """Marca el job como en proceso y refresca la marca temporal."""
        self.status = JobStatus.PROCESSING
        self.updated_at = datetime.now(timezone.utc)

    def mark_completed(self, output_path: Path, num_pages: int) -> None:
        """Marca el job como completado y guarda datos clave de salida."""
        self.status = JobStatus.COMPLETED
        self.output_path = output_path
        self.num_pages = num_pages
        self.progress_stage = "completed"
        if self.progress_total is not None:
            self.progress_current = self.progress_total
        self.updated_at = datetime.now(timezone.utc)

    def mark_failed(self, error_message: str) -> None:
        """Registra un fallo y almacena el mensaje de error mostrado al cliente."""
        self.status = JobStatus.FAILED
        self.error_message = error_message
        self.progress_stage = "failed"
        self.updated_at = datetime.now(timezone.utc)

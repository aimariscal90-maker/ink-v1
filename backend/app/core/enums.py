"""Enumeraciones compartidas que describen estados y tipos de trabajo."""

from enum import Enum


class JobStatus(str, Enum):
    """Estados posibles de un trabajo de procesamiento."""

    UPLOADED = "uploaded"
    QUEUED = "queued"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class JobType(str, Enum):
    """Formato de archivo de entrada que recibimos."""

    PDF = "pdf"
    COMIC = "comic"  # CBR/CBZ


class OutputFormat(str, Enum):
    """Formato en el que devolvemos el resultado procesado."""

    PDF = "pdf"
    CBZ = "cbz"

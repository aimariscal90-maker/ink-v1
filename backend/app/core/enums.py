from enum import Enum


class JobStatus(str, Enum):
    UPLOADED = "uploaded"
    QUEUED = "queued"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class JobType(str, Enum):
    PDF = "pdf"
    COMIC = "comic"  # CBR/CBZ


class OutputFormat(str, Enum):
    PDF = "pdf"
    CBZ = "cbz"

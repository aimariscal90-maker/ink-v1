import sys
from pathlib import Path

from PIL import Image

# Añadir backend/ al PYTHONPATH
sys.path.append(str(Path(__file__).resolve().parents[2]))

from app.core.enums import JobType
from app.services.import_service import ImportService


def _build_dummy_pdf(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    img = Image.new("RGB", (200, 280), color=(240, 240, 240))
    img.save(path, format="PDF")
    return path


def main() -> None:
    work_dir = Path("data/jobs/test-import-pdf")
    work_dir.mkdir(parents=True, exist_ok=True)

    input_path = work_dir / "sample.pdf"
    if not input_path.exists():
        _build_dummy_pdf(input_path)

    service = ImportService(work_dir=work_dir)
    pages = service.import_file(input_path=input_path, job_type=JobType.PDF)

    print(f"Total páginas: {len(pages)}")
    for p in pages:
        print(p.index, p.image_path, p.width, p.height)


if __name__ == "__main__":
    main()

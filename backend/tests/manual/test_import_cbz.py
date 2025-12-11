import sys
from pathlib import Path

# Añadir backend/ al PYTHONPATH
sys.path.append(str(Path(__file__).resolve().parents[2]))

from app.core.enums import JobType
from app.services.import_service import ImportService


def main() -> None:
    work_dir = Path("data/jobs/test-import-cbz")
    work_dir.mkdir(parents=True, exist_ok=True)

    input_path = Path("tests/files/sample.cbz")

    if not input_path.exists():
        raise SystemExit(f"Input CBZ not found: {input_path}")

    service = ImportService(work_dir=work_dir)
    pages = service.import_file(input_path=input_path, job_type=JobType.COMIC)

    print(f"Total páginas: {len(pages)}")
    for p in pages:
        print(p.index, p.image_path, p.width, p.height)


if __name__ == "__main__":
    main()

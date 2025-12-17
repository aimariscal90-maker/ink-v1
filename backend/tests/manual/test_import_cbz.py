import sys
import zipfile
from pathlib import Path

from PIL import Image

# Añadir backend/ al PYTHONPATH
sys.path.append(str(Path(__file__).resolve().parents[2]))

from app.core.enums import JobType
from app.services.import_service import ImportService


def _build_dummy_cbz(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    page_dir = path.parent / "pages"
    page_dir.mkdir(exist_ok=True)

    images = []
    for idx, shade in enumerate((180, 200)):
        img_path = page_dir / f"page_{idx}.png"
        Image.new("RGB", (120, 160), color=(shade, shade, shade)).save(img_path)
        images.append(img_path)

    with zipfile.ZipFile(path, "w") as archive:
        for img in images:
            archive.write(img, img.name)
    return path


def main() -> None:
    work_dir = Path("data/jobs/test-import-cbz")
    work_dir.mkdir(parents=True, exist_ok=True)

    input_path = work_dir / "sample.cbz"
    if not input_path.exists():
        _build_dummy_cbz(input_path)

    service = ImportService(work_dir=work_dir)
    pages = service.import_file(input_path=input_path, job_type=JobType.COMIC)

    print(f"Total páginas: {len(pages)}")
    for p in pages:
        print(p.index, p.image_path, p.width, p.height)


if __name__ == "__main__":
    main()

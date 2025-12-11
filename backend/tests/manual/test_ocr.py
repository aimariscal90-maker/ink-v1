import sys
from pathlib import Path

# Añadir backend/ al PYTHONPATH
sys.path.append(str(Path(__file__).resolve().parents[2]))

from app.services.ocr_service import OcrService


def main():
    image_path = Path("data/jobs/test-import-pdf/pages/test_batman1.png")

    if not image_path.exists():
        raise SystemExit(f"Image not found: {image_path}")

    print("Probando OCR sobre:", image_path)

    ocr = OcrService()
    regions = ocr.extract_text_regions(image_path)

    print(f"Regiones detectadas: {len(regions)}")
    for r in regions[:10]:  # Mostrar solo 10
        print(r.id, r.text, r.bbox)


if __name__ == "__main__":
    main()

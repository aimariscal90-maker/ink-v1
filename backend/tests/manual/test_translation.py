import sys
from pathlib import Path

# Añadir backend/ al PYTHONPATH
sys.path.append(str(Path(__file__).resolve().parents[2]))

from app.models.text import BBox, TextRegion
from app.services.translation_service import TranslationService


def main() -> None:
    # Creamos unas regiones falsas (simulando diálogos de cómic)
    regions = [
        TextRegion(
            id="1",
            text="Hey, how are you?",
            bbox=BBox(x_min=0.1, y_min=0.1, x_max=0.3, y_max=0.2),
        ),
        TextRegion(
            id="2",
            text="We need to leave now!",
            bbox=BBox(x_min=0.2, y_min=0.3, x_max=0.5, y_max=0.4),
        ),
        TextRegion(
            id="3",
            text="What the hell is going on?!",
            bbox=BBox(x_min=0.4, y_min=0.5, x_max=0.8, y_max=0.6),
        ),
    ]

    service = TranslationService()
    translated = service.translate_regions(
        regions=regions,
        source_lang="en",
        target_lang="es",
    )

    print(f"Total regiones traducidas: {len(translated)}")
    for t in translated:
        print(f"ID={t.id}")
        print(f"  ORIGINAL:   {t.original_text!r}")
        print(f"  TRADUCIDO:  {t.translated_text!r}")
        print("---")


if __name__ == "__main__":
    main()

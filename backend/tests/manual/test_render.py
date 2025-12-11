import sys
from pathlib import Path

# Añadir backend/ al PYTHONPATH
sys.path.append(str(Path(__file__).resolve().parents[2]))

from app.models.text import BBox, TranslatedRegion
from app.services.render_service import RenderService


def main() -> None:
    # Usamos la imagen de test del día 4
    input_image = Path("data/jobs/test-import-pdf/pages/page_0000.png")
    if not input_image.exists():
        raise SystemExit(f"Input image not found: {input_image}")

    # Creamos una región falsa en el centro de la imagen
    bbox = BBox(
        x_min=0.2,
        y_min=0.2,
        x_max=0.8,
        y_max=0.4,
    )

    region = TranslatedRegion(
        id="1",
        original_text="This is a fake balloon",
        translated_text="Este es un globo de prueba con un texto bastante largo para comprobar el ajuste.",
        bbox=bbox,
        confidence=None,
    )

    render_service = RenderService()
    output_image = input_image.with_name(input_image.stem + "_translated.png")

    result_path = render_service.render_page(
        input_image=input_image,
        regions=[region],
        output_image=output_image,
    )

    print("Imagen traducida generada en:", result_path)


if __name__ == "__main__":
    main()

from pathlib import Path

from PIL import Image

from app.models.text import BBox, TranslatedRegion
from app.services.render_service import RenderService


def test_render_handles_overflow_and_retries(tmp_path):
    input_path = tmp_path / "page.png"
    Image.new("RGB", (200, 200), color="white").save(input_path)

    region = TranslatedRegion(
        id="1",
        original_text="",
        translated_text=(
            "Este es un cuadro con un texto muy largo que debería requerir saltos de línea y"
            " ajustes de tamaño para caber dentro del globo de diálogo sin desbordar."
        ),
        bbox=BBox(x_min=0.1, y_min=0.1, x_max=0.4, y_max=0.25),
    )

    service = RenderService(max_font_size=26, min_font_size=10, padding_px=6)
    result = service.render_page(input_path, [region], tmp_path / "out.png")

    assert result.output_image.exists()
    assert all(layout.font_size <= service.max_font_size for layout in result.layouts or [])
    assert result.qa_overflow_count >= 1
    assert result.qa_retry_count >= 1

from pathlib import Path

from PIL import Image, ImageDraw

from app.models.text import BBox, TextRegion, TranslatedRegion
from app.services.ocr_service import OcrService
from app.services.render_service import RenderService


class SummaryStub:
    def __init__(self) -> None:
        self.calls = 0

    def summarize_to_length(self, original: str, translated: str, max_chars: int) -> str:
        self.calls += 1
        return (translated[: max_chars // 2] + "…") if len(translated) > max_chars else translated


def _build_barrier_fixture(path: Path) -> Path:
    """Create a simple grayscale image with a bright vertical barrier between two bubbles."""
    img = Image.new("L", (240, 140), color=180)
    draw = ImageDraw.Draw(img)
    draw.rectangle((10, 10, 110, 130), fill=140)
    draw.rectangle((130, 10, 230, 130), fill=140)
    draw.rectangle((110, 0, 130, 140), fill=255)  # White separator
    img.save(path)
    return path


def _build_ellipse_fixture(path: Path) -> Path:
    """Create an image with an oval balloon on a darker background."""
    img = Image.new("RGB", (220, 160), color=(140, 140, 140))
    draw = ImageDraw.Draw(img)
    draw.ellipse((30, 20, 190, 150), fill=(245, 245, 245))
    img.save(path)
    return path


def test_white_barrier_blocks_merge(tmp_path: Path):
    image_path = _build_barrier_fixture(tmp_path / "barrier_bubbles.png")
    gray = Image.open(image_path).convert("L")

    ocr = OcrService()
    regions = [
        TextRegion(
            id="a",
            text="Hi",
            bbox=BBox(x_min=0.08, y_min=0.25, x_max=0.48, y_max=0.7),
            confidence=0.9,
        ),
        TextRegion(
            id="b",
            text="There",
            bbox=BBox(x_min=0.52, y_min=0.15, x_max=0.9, y_max=0.6),
            confidence=0.9,
        ),
    ]

    merged = ocr._merge_nearby_regions(regions, gray.width, gray.height, gray)

    assert len(merged) == 2, "Burbujas separadas no deben mergearse"
    assert ocr.merge_rejected_barrier >= 1


def test_masked_render_keeps_paint_inside(tmp_path: Path):
    image_path = _build_ellipse_fixture(tmp_path / "ellipse_balloon.png")
    region = TranslatedRegion(
        id="r1",
        original_text="Original",
        translated_text="Esta es una frase muy larga que necesita resumirse para caber en un globo pequeño",
        bbox=BBox(x_min=40 / 220, y_min=40 / 160, x_max=180 / 220, y_max=150 / 160),
        confidence=0.9,
        region_kind="dialogue",
    )

    summarizer = SummaryStub()
    renderer = RenderService(
        max_font_size=28,
        min_font_size=10,
        min_readable_font=18,
        translation_service=summarizer,
    )
    output_path = tmp_path / "render.png"
    result = renderer.render_page(image_path, [region], output_image=output_path)

    out_img = Image.open(result.output_image).convert("RGBA")
    corner_px = out_img.getpixel((45, 45))
    center_px = out_img.getpixel((110, 80))

    assert corner_px[0] < 200, "El relleno no debe cubrir esquinas fuera del óvalo"
    assert center_px[0] > corner_px[0], "El interior del globo debe quedar limpio para el texto"
    assert result.summarize_triggered_count >= 1
    assert summarizer.calls >= 1
    assert result.min_font_hit_count >= 1

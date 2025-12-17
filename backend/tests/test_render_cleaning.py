from pathlib import Path

import pytest
from PIL import Image, ImageDraw

from app.models.text import BBox, TranslatedRegion
from app.services.render_service import RenderService


class TranslatorStub:
    def __init__(self, translated: str = "hola mundo") -> None:
        self.calls = 0
        self.translated = translated

    def translate_text_cached(self, text: str, target_lang: str = "es") -> str:  # noqa: ARG002
        self.calls += 1
        return self.translated


def _draw_original_text(path: Path, text: str) -> None:
    img = Image.new("RGB", (240, 180), color="white")
    draw = ImageDraw.Draw(img)
    draw.text((60, 70), text, fill=(0, 0, 0))
    img.save(path)


def test_residual_cleanup_retries(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    input_path = tmp_path / "page.png"
    _draw_original_text(input_path, "HELLO THERE")

    region = TranslatedRegion(
        id="r1",
        original_text="Hello there",
        translated_text="",
        bbox=BBox(x_min=0.1, y_min=0.2, x_max=0.9, y_max=0.8),
    )

    renderer = RenderService(max_font_size=18, min_font_size=12)

    def tiny_mask(image, area, fill):  # noqa: ANN001
        x1, y1, x2, y2 = area
        mask = Image.new("L", (max(1, x2 - x1), max(1, y2 - y1)), 0)
        mask_draw = ImageDraw.Draw(mask)
        mask_draw.rectangle((0, 0, max(1, (x2 - x1) // 4), max(1, (y2 - y1) // 4)), fill=255)
        return mask, fill

    monkeypatch.setattr(renderer, "_build_balloon_mask", tiny_mask)

    result = renderer.render_page(input_path, [region], tmp_path / "out.png")
    out_img = Image.open(result.output_image).convert("L")
    crop = out_img.crop(renderer._bbox_to_pixels(region.bbox, out_img.width, out_img.height))

    assert renderer._dark_ratio(crop) < 0.05, "El texto residual debe limpiarse por completo"
    assert result.cleanup_retry_count >= 1


def test_overflow_skip_prevents_overlap(tmp_path: Path):
    input_path = tmp_path / "page.png"
    _draw_original_text(input_path, "ORIGINAL TEXT")

    region = TranslatedRegion(
        id="r1",
        original_text="Original text",
        translated_text=(
            "Este texto es intencionadamente largo y no debería renderizarse si no cabe en la "
            "caja porque causaría superposiciones claras."
        ),
        bbox=BBox(x_min=0.1, y_min=0.1, x_max=0.4, y_max=0.2),
    )

    renderer = RenderService(max_font_size=30, min_font_size=16, min_readable_font=18)
    result = renderer.render_page(input_path, [region], tmp_path / "out_overflow.png")

    out_img = Image.open(result.output_image).convert("L")
    crop = out_img.crop(renderer._bbox_to_pixels(region.bbox, out_img.width, out_img.height))

    assert result.overflow_skip_count >= 1, "Las cajas que siguen desbordadas no deben dibujarse"
    assert renderer._dark_ratio(crop) < 0.1, "No debe haber letras superpuestas en la caja"


def test_untranslated_region_gets_retried(tmp_path: Path):
    input_path = tmp_path / "page.png"
    _draw_original_text(input_path, "HELLO WORLD")

    region = TranslatedRegion(
        id="r1",
        original_text="Hello world",
        translated_text="HELLO WORLD",
        bbox=BBox(x_min=0.1, y_min=0.1, x_max=0.9, y_max=0.3),
    )

    translator = TranslatorStub("hola mundo")
    renderer = RenderService(max_font_size=22, min_font_size=12, translation_service=translator)

    result = renderer.render_page(input_path, [region], tmp_path / "out_retry.png")

    assert translator.calls == 1
    assert result.untranslated_skip_count == 0
    assert any("hola" in line for line in (result.layouts or [])[0].lines)

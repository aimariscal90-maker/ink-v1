from pathlib import Path

from app.services.layout_service import LayoutService


def test_short_text_prefers_max_font():
    service = LayoutService()
    result = service.fit_text_to_box(
        text="Hola",
        box_w=200,
        box_h=100,
        font_path=Path("DejaVuSans.ttf"),
        max_font=40,
        min_font=10,
    )

    assert result.fits is True
    assert result.font_size == 40
    assert len(result.lines) == 1


def test_long_text_wraps_and_shrinks_font():
    service = LayoutService()
    text = "Este es un texto bastante largo que debería forzar saltos de línea y reducir la fuente"
    result = service.fit_text_to_box(
        text=text,
        box_w=80,
        box_h=140,
        font_path=Path("DejaVuSans.ttf"),
        max_font=30,
        min_font=12,
    )

    assert result.fits is True
    assert result.font_size < 30
    assert len(result.lines) > 1


def test_huge_text_reports_overflow():
    service = LayoutService()
    text = "Muy " * 200
    result = service.fit_text_to_box(
        text=text,
        box_w=40,
        box_h=30,
        font_path=Path("DejaVuSans.ttf"),
        max_font=18,
        min_font=8,
    )

    assert result.font_size == 8
    assert result.fits is False

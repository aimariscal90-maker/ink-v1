from app.models.text import BBox, TextRegion
from app.services.cache_service import CacheService
from app.services.ocr_service import OcrService


def test_post_process_reduces_word_explosion(tmp_path):
    service = OcrService(cache_service=CacheService(base_dir=tmp_path / "cache"))

    raw_regions = []
    idx = 0
    # Simula muchas palabras sueltas en varias líneas/párrafos
    for paragraph in range(3):
        base_y = 20 + paragraph * 140
        for line in range(3):
            y = base_y + line * 18
            for word in range(20):
                x = 20 + word * 28
                raw_regions.append(
                    TextRegion(
                        id=str(idx),
                        text=f"w{paragraph}-{line}-{word}",
                        bbox=BBox(
                            x_min=x / 1000,
                            y_min=y / 1000,
                            x_max=(x + 26) / 1000,
                            y_max=(y + 22) / 1000,
                        ),
                        confidence=0.9,
                    )
                )
                idx += 1

    processed = service._post_process_regions(
        raw_regions,
        image_width=1000,
        image_height=1000,
        fallback=False,
    )

    assert service.regions_detected_raw == len(raw_regions)
    assert len(processed) < 30  # De >180 palabras a unos pocos bloques
    assert service.regions_after_paragraph_grouping <= len(raw_regions)
    assert service.regions_after_merge == len(processed)


def test_merge_respects_panel_gutters_and_bubbles(tmp_path):
    """Regression inspired by Thor 005 (2026) – pages 19–23: no cross-panel merges."""

    service = OcrService(cache_service=CacheService(base_dir=tmp_path / "cache"))

    left_panel = TextRegion(
        id="p1",
        text="Left bubble",
        bbox=BBox(x_min=0.05, y_min=0.1, x_max=0.25, y_max=0.18),
        confidence=0.9,
    )
    right_panel = TextRegion(
        id="p2",
        text="Right bubble",
        bbox=BBox(x_min=0.65, y_min=0.12, x_max=0.85, y_max=0.2),
        confidence=0.9,
    )

    merged = service._merge_nearby_regions([left_panel, right_panel], 1000, 1000)

    assert len(merged) == 2


def test_merge_rejects_misaligned_bubbles(tmp_path):
    service = OcrService(cache_service=CacheService(base_dir=tmp_path / "cache"))

    tall_bubble = TextRegion(
        id="t1",
        text="Tall bubble text",
        bbox=BBox(x_min=0.3, y_min=0.3, x_max=0.42, y_max=0.5),
        confidence=0.95,
    )
    short_bubble = TextRegion(
        id="s1",
        text="short",
        bbox=BBox(x_min=0.33, y_min=0.52, x_max=0.4, y_max=0.55),
        confidence=0.95,
    )

    merged = service._merge_nearby_regions([tall_bubble, short_bubble], 1000, 1000)

    assert len(merged) == 2


def test_merge_respects_character_cap(tmp_path):
    service = OcrService(cache_service=CacheService(base_dir=tmp_path / "cache"))
    service.settings.ocr_merge_max_characters = 20

    bubble_a = TextRegion(
        id="a",
        text="1234567890",
        bbox=BBox(x_min=0.1, y_min=0.6, x_max=0.3, y_max=0.66),
        confidence=0.9,
    )
    bubble_b = TextRegion(
        id="b",
        text="abcdefghij",
        bbox=BBox(x_min=0.32, y_min=0.6, x_max=0.5, y_max=0.66),
        confidence=0.9,
    )

    merged = service._merge_nearby_regions([bubble_a, bubble_b], 1000, 1000)

    assert len(merged) == 2

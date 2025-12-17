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
        raw_regions, image_width=1000, image_height=1000
    )

    assert service.regions_detected_raw == len(raw_regions)
    assert len(processed) < 30  # De >180 palabras a unos pocos bloques
    assert service.regions_after_paragraph_grouping <= len(raw_regions)
    assert service.regions_after_merge == len(processed)

from app.models.text import BBox, TextRegion
from app.services.cache_service import CacheService
from app.services.ocr_service import OcrService


def test_fallback_and_filtering(tmp_path):
    service = OcrService(cache_service=CacheService(base_dir=tmp_path / "cache"))

    raw_regions = [
        TextRegion(
            id="0",
            text="HELLO?",
            bbox=BBox(x_min=0.1, y_min=0.1, x_max=0.18, y_max=0.15),
            confidence=0.42,
        ),
        TextRegion(
            id="1",
            text="",
            bbox=BBox(x_min=0.2, y_min=0.2, x_max=0.21, y_max=0.21),
            confidence=0.9,
        ),
    ]

    primary = service._post_process_regions(
        raw_regions, image_width=1000, image_height=1000, fallback=False
    )
    assert service._should_retry_ocr(raw_regions, primary, 1000, 1000)

    fallback = service._post_process_regions(
        raw_regions, image_width=1000, image_height=1000, fallback=True
    )
    assert len(fallback) >= len(primary)


def test_filters_drop_non_dialogue_noise(tmp_path):
    service = OcrService(cache_service=CacheService(base_dir=tmp_path / "cache"))

    raw_regions = []
    idx = 0
    for line in range(4):
        y = 0.05 + 0.07 * line
        for word in range(15):
            x = 0.05 + 0.05 * word
            raw_regions.append(
                TextRegion(
                    id=str(idx),
                    text=f"{idx}" if idx % 3 == 0 else f"word-{idx}",
                    bbox=BBox(x_min=x, y_min=y, x_max=x + 0.04, y_max=y + 0.03),
                    confidence=0.8,
                )
            )
            idx += 1

    processed = service._post_process_regions(
        raw_regions, image_width=1000, image_height=1000, fallback=False
    )

    assert len(processed) < len(raw_regions) // 3
    assert service.regions_after_merge == len(processed)

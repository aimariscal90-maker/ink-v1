from pathlib import Path

from app.models.text import BBox, TextRegion
from app.services.cache_service import CacheService
from app.services.ocr_service import OcrService
from app.services.translation_service import TranslationService


def test_ocr_uses_cache_when_available(monkeypatch, tmp_path):
    cache = CacheService(base_dir=tmp_path / "cache")
    image_path = tmp_path / "page.png"
    image_bytes = b"dummy-image"
    image_path.write_bytes(image_bytes)

    cached_region = TextRegion(
        id="1",
        text="cached",
        bbox=BBox(x_min=0.0, y_min=0.0, x_max=1.0, y_max=1.0),
        confidence=None,
    )
    cache.set_json(
        f"ocr:{CacheService.key_hash(image_bytes)}",
        {"regions": [cached_region.model_dump()]},
    )

    service = OcrService(cache_service=cache)
    monkeypatch.setattr(service, "_get_client", lambda: (_ for _ in ()).throw(AssertionError("Vision client should not be called")))

    regions = service.extract_text_regions(image_path)

    assert len(regions) == 1
    assert regions[0].text == "cached"


def test_translation_cache_skips_model(monkeypatch, tmp_path):
    cache = CacheService(base_dir=tmp_path / "cache")
    service = TranslationService(cache_service=cache)

    text = "hello"
    target_lang = "es"
    cache.set_text(
        f"tr:{target_lang}:{CacheService.key_hash(text)}",
        "hola",
    )

    monkeypatch.setattr(service, "_get_client", lambda: (_ for _ in ()).throw(AssertionError("Model should not be called")))

    result = service.translate_text_cached(text, target_lang)

    assert result == "hola"


def test_translate_regions_batch_preserves_order(monkeypatch, tmp_path):
    cache = CacheService(base_dir=tmp_path / "cache")
    service = TranslationService(cache_service=cache)

    regions = [
        TextRegion(
            id="a",
            text="first",
            bbox=BBox(x_min=0, y_min=0, x_max=1, y_max=1),
        ),
        TextRegion(
            id="b",
            text="second",
            bbox=BBox(x_min=0, y_min=0, x_max=1, y_max=1),
        ),
    ]

    def fake_batch(texts, source_lang, target_lang):  # type: ignore[unused-argument]
        return [text.upper() for text in texts]

    monkeypatch.setattr(service, "_translate_texts_batch", fake_batch)

    translated = service.translate_regions_batch(
        regions=regions, source_lang="en", target_lang="es"
    )

    assert [r.translated_text for r in translated] == ["FIRST", "SECOND"]
    assert [r.id for r in translated] == ["a", "b"]

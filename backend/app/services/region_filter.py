from __future__ import annotations

"""Heurísticas para decidir si una caja de texto parece diálogo o ruido."""

import re
from enum import Enum

from app.core.config import get_settings
from app.models.text import BBox


class RegionKind(str, Enum):
    DIALOGUE = "dialogue"
    NON_DIALOGUE = "non_dialogue"
    UNKNOWN = "unknown"


def _ratio(predicate, text: str) -> float:
    """Calcula el porcentaje de caracteres que cumplen un predicado."""
    if not text:
        return 0.0
    count = sum(1 for c in text if predicate(c))
    return count / len(text)


def classify_region(
    text: str, bbox: BBox, confidence: float | None, page_w: int, page_h: int
) -> RegionKind:
    """Clasifica un fragmento de texto usando reglas sencillas.

    La idea es filtrar numeraciones, onomatopeyas aisladas o ruido que el OCR
    captura pero que no queremos traducir/pintar. Se comentan los checks para
    que sea fácil ajustar los umbrales.
    """
    settings = get_settings()
    cleaned = text.strip()

    if not cleaned:
        return RegionKind.NON_DIALOGUE

    min_conf = settings.ocr_classifier_min_confidence
    if confidence is not None and confidence < min_conf:
        return RegionKind.NON_DIALOGUE

    area_ratio = (bbox.x_max - bbox.x_min) * (bbox.y_max - bbox.y_min)
    if area_ratio <= 0:
        return RegionKind.NON_DIALOGUE
    if area_ratio < settings.ocr_min_area_ratio * 0.5:
        return RegionKind.NON_DIALOGUE
    if area_ratio > settings.ocr_max_area_ratio:
        return RegionKind.NON_DIALOGUE

    width_px = (bbox.x_max - bbox.x_min) * page_w
    height_px = (bbox.y_max - bbox.y_min) * page_h
    if width_px < settings.ocr_min_width_px or height_px < settings.ocr_min_height_px:
        return RegionKind.NON_DIALOGUE

    digits_ratio = _ratio(str.isdigit, cleaned)
    non_alnum_ratio = _ratio(lambda c: not c.isalnum(), cleaned)
    ascii_letter_ratio = _ratio(lambda c: c.isascii() and c.isalpha(), cleaned)

    noise_regex = re.compile(r"^[^A-Za-z0-9ÁÉÍÓÚÜÑáéíóúüñ]+$")
    repeated_regex = re.compile(r"^(.)\1{3,}$")

    if noise_regex.match(cleaned) or repeated_regex.match(cleaned):
        return RegionKind.NON_DIALOGUE
    if digits_ratio > 0.6 or non_alnum_ratio > 0.6:
        return RegionKind.NON_DIALOGUE
    if len(cleaned) <= 2 and non_alnum_ratio > 0:
        return RegionKind.NON_DIALOGUE

    word_count = len(cleaned.split())
    has_dialogue_punct = any(ch in cleaned for ch in ["?", "!", "…", "—"])
    has_lower = any(c.islower() for c in cleaned)

    if cleaned.isupper() and len(cleaned) <= 4:
        return RegionKind.NON_DIALOGUE

    if word_count >= 4 and has_lower:
        return RegionKind.DIALOGUE
    if has_dialogue_punct and has_lower:
        return RegionKind.DIALOGUE
    if ascii_letter_ratio > 0.4 and has_lower and word_count >= 2:
        return RegionKind.DIALOGUE

    return RegionKind.UNKNOWN

from __future__ import annotations

from pathlib import Path
from typing import List

from google.cloud import vision

from app.models.text import BBox, TextRegion
from app.services.cache_service import CacheService


class OcrService:
    """
    Extrae regiones de texto desde una imagen usando Google Cloud Vision OCR.
    """

    def __init__(self, cache_service: CacheService | None = None) -> None:
        self.client = None
        self.cache = cache_service or CacheService()
        self.last_invalid_bbox_count = 0
        self.last_discarded_region_count = 0
        self.last_merged_region_count = 0

    def _get_client(self):
        if self.client is None:
            self.client = vision.ImageAnnotatorClient()
        return self.client

    def extract_text_regions(self, image_path: Path) -> List[TextRegion]:
        """
        Devuelve todas las regiones de texto detectadas con bounding boxes normalizados.
        """

        # Reset métricas por llamada
        self.last_invalid_bbox_count = 0
        self.last_discarded_region_count = 0
        self.last_merged_region_count = 0

        with open(image_path, "rb") as f:
            content = f.read()

        image_hash = CacheService.key_hash(content)
        cache_key = f"ocr:{image_hash}"

        cached = self.cache.get_json(cache_key)
        if cached and isinstance(cached.get("regions"), list):
            return [TextRegion.model_validate(region) for region in cached["regions"]]

        image = vision.Image(content=content)
        client = self._get_client()
        response = client.text_detection(image=image)

        if response.error.message:
            raise RuntimeError(f"Google Vision OCR error: {response.error.message}")

        annotations = response.text_annotations
        full_text = getattr(response, "full_text_annotation", None)

        # Dimensiones reales de la imagen
        import PIL.Image

        with PIL.Image.open(image_path) as img:
            width, height = img.width, img.height

        regions: List[TextRegion] = []

        if getattr(full_text, "pages", None):
            regions = self._extract_from_full_text(full_text, width, height)
        elif annotations:
            regions = self._extract_from_annotations(annotations[1:], width, height)

        merged = self._merge_nearby_regions(regions)

        self.cache.set_json(cache_key, {"regions": [r.model_dump() for r in merged]})

        return merged

    # ---------- Helpers internos ----------

    def _sanitize_bbox(self, vertices, width: int, height: int) -> BBox | None:
        """Normaliza y valida un bounding box. Devuelve None si es inválido o demasiado pequeño."""

        xs = [v.x or 0 for v in vertices]
        ys = [v.y or 0 for v in vertices]

        x_min = min(xs)
        y_min = min(ys)
        x_max = max(xs)
        y_max = max(ys)

        # Clamp a la imagen y normalizar
        x_min = max(0.0, min(x_min, width))
        y_min = max(0.0, min(y_min, height))
        x_max = max(0.0, min(x_max, width))
        y_max = max(0.0, min(y_max, height))

        if x_min == x_max or y_min == y_max:
            self.last_invalid_bbox_count += 1
            return None

        if x_min > x_max:
            x_min, x_max = x_max, x_min
        if y_min > y_max:
            y_min, y_max = y_max, y_min

        pixel_w = x_max - x_min
        pixel_h = y_max - y_min
        if pixel_w < 2 or pixel_h < 2 or pixel_w * pixel_h < 16:
            self.last_discarded_region_count += 1
            return None

        return BBox(
            x_min=x_min / width,
            y_min=y_min / height,
            x_max=x_max / width,
            y_max=y_max / height,
        ).clamp()

    def _extract_from_full_text(self, full_text, width: int, height: int) -> List[TextRegion]:
        regions: List[TextRegion] = []
        idx = 1

        for page in getattr(full_text, "pages", []) or []:
            for block in getattr(page, "blocks", []) or []:
                for paragraph in getattr(block, "paragraphs", []) or []:
                    text_parts: List[str] = []
                    for word in getattr(paragraph, "words", []) or []:
                        symbols = getattr(word, "symbols", []) or []
                        word_text = "".join(getattr(sym, "text", "") for sym in symbols)
                        if word_text:
                            text_parts.append(word_text)

                    combined_text = " ".join(text_parts).strip()
                    bbox = None
                    if getattr(paragraph, "bounding_box", None):
                        bbox = self._sanitize_bbox(
                            paragraph.bounding_box.vertices, width, height
                        )

                    if combined_text and bbox:
                        regions.append(
                            TextRegion(
                                id=str(idx),
                                text=combined_text,
                                bbox=bbox,
                                confidence=None,
                            )
                        )
                        idx += 1

        return regions

    def _extract_from_annotations(self, annotations, width: int, height: int) -> List[TextRegion]:
        regions: List[TextRegion] = []
        for idx, ann in enumerate(annotations, start=1):
            bbox = self._sanitize_bbox(ann.bounding_poly.vertices, width, height)
            if not bbox:
                continue

            regions.append(
                TextRegion(
                    id=str(idx),
                    text=ann.description,
                    bbox=bbox,
                    confidence=None,
                )
            )
        return regions

    def _merge_nearby_regions(self, regions: List[TextRegion]) -> List[TextRegion]:
        if not regions:
            return []

        # Orden determinista top-to-bottom, left-to-right
        sorted_regions = sorted(regions, key=lambda r: (r.bbox.y_min, r.bbox.x_min))
        merged: List[TextRegion] = []

        def iou(a: BBox, b: BBox) -> float:
            x_left = max(a.x_min, b.x_min)
            y_top = max(a.y_min, b.y_min)
            x_right = min(a.x_max, b.x_max)
            y_bottom = min(a.y_max, b.y_max)
            inter_w = max(0.0, x_right - x_left)
            inter_h = max(0.0, y_bottom - y_top)
            inter = inter_w * inter_h
            if inter == 0:
                return 0.0
            area_a = (a.x_max - a.x_min) * (a.y_max - a.y_min)
            area_b = (b.x_max - b.x_min) * (b.y_max - b.y_min)
            return inter / (area_a + area_b - inter)

        def close_on_y(a: BBox, b: BBox) -> bool:
            y_overlap = min(a.y_max, b.y_max) - max(a.y_min, b.y_min)
            total_h = max(a.y_max, b.y_max) - min(a.y_min, b.y_min)
            return y_overlap / total_h >= 0.5 if total_h else False

        def horizontal_gap(a: BBox, b: BBox) -> float:
            if a.x_max < b.x_min:
                return b.x_min - a.x_max
            if b.x_max < a.x_min:
                return a.x_min - b.x_max
            return 0.0

        for region in sorted_regions:
            if not merged:
                merged.append(region)
                continue

            last = merged[-1]
            overlap = iou(last.bbox, region.bbox)
            gap = horizontal_gap(last.bbox, region.bbox)
            if overlap >= 0.2 or (close_on_y(last.bbox, region.bbox) and gap <= 0.02):
                union_bbox = BBox(
                    x_min=min(last.bbox.x_min, region.bbox.x_min),
                    y_min=min(last.bbox.y_min, region.bbox.y_min),
                    x_max=max(last.bbox.x_max, region.bbox.x_max),
                    y_max=max(last.bbox.y_max, region.bbox.y_max),
                ).clamp()
                merged[-1] = TextRegion(
                    id=last.id,
                    text=f"{last.text} {region.text}".strip(),
                    bbox=union_bbox,
                    confidence=last.confidence,
                )
                self.last_merged_region_count += 1
            else:
                merged.append(region)

        # Reasignar ids secuenciales para mantener orden
        for idx, region in enumerate(merged, start=1):
            region.id = str(idx)

        return merged

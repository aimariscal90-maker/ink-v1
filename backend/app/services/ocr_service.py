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

    MIN_AREA_RATIO = 0.0005
    MIN_TEXT_LEN = 3
    MIN_CONFIDENCE = 0.5
    MERGE_GAP_PX = 20
    MERGE_IOU_THRESHOLD = 0.2

    def __init__(self, cache_service: CacheService | None = None) -> None:
        self.client = None
        self.cache = cache_service or CacheService()
        self.last_invalid_bbox_count = 0
        self.last_discarded_region_count = 0
        self.last_merged_region_count = 0
        self.regions_detected_raw = 0
        self.regions_after_paragraph_grouping = 0
        self.regions_after_filter = 0
        self.regions_after_merge = 0

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
        self.regions_detected_raw = 0
        self.regions_after_paragraph_grouping = 0
        self.regions_after_filter = 0
        self.regions_after_merge = 0

        with open(image_path, "rb") as f:
            content = f.read()

        image_hash = CacheService.key_hash(content)
        cache_key = f"ocr:{image_hash}"

        cached = self.cache.get_json(cache_key)
        if cached and isinstance(cached.get("regions"), list):
            metrics = cached.get("metrics") or {}
            self.regions_detected_raw = metrics.get("regions_detected_raw", 0)
            self.regions_after_paragraph_grouping = metrics.get(
                "regions_after_paragraph_grouping", 0
            )
            self.regions_after_filter = metrics.get("regions_after_filter", 0)
            self.regions_after_merge = metrics.get("regions_after_merge", 0)
            self.last_invalid_bbox_count = metrics.get("last_invalid_bbox_count", 0)
            self.last_discarded_region_count = metrics.get("last_discarded_region_count", 0)
            self.last_merged_region_count = metrics.get("last_merged_region_count", 0)
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
        raw_candidates = 0
        grouped = 0

        if getattr(full_text, "pages", None):
            regions, raw_candidates, grouped = self._extract_from_full_text(
                full_text, width, height
            )
        elif annotations:
            regions, raw_candidates, grouped = self._extract_from_annotations(
                annotations[1:], width, height
            )

        self.regions_detected_raw = raw_candidates
        self.regions_after_paragraph_grouping = grouped

        filtered = self._filter_regions(regions, width, height)
        self.regions_after_filter = len(filtered)

        merged = self._merge_nearby_regions(filtered, width, height)
        self.regions_after_merge = len(merged)

        self.cache.set_json(
            cache_key,
            {
                "regions": [r.model_dump() for r in merged],
                "metrics": {
                    "regions_detected_raw": self.regions_detected_raw,
                    "regions_after_paragraph_grouping": self.regions_after_paragraph_grouping,
                    "regions_after_filter": self.regions_after_filter,
                    "regions_after_merge": self.regions_after_merge,
                    "last_invalid_bbox_count": self.last_invalid_bbox_count,
                    "last_discarded_region_count": self.last_discarded_region_count,
                    "last_merged_region_count": self.last_merged_region_count,
                },
            },
        )

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

        if x_min >= x_max or y_min >= y_max:
            self.last_invalid_bbox_count += 1
            return None

        if x_min > x_max:
            x_min, x_max = x_max, x_min
        if y_min > y_max:
            y_min, y_max = y_max, y_min

        pixel_w = x_max - x_min
        pixel_h = y_max - y_min
        area_ratio = (pixel_w * pixel_h) / float(width * height)
        if (
            pixel_w < 2
            or pixel_h < 2
            or pixel_w * pixel_h < 16
            or area_ratio < self.MIN_AREA_RATIO
        ):
            self.last_discarded_region_count += 1
            return None

        return BBox(
            x_min=x_min / width,
            y_min=y_min / height,
            x_max=x_max / width,
            y_max=y_max / height,
        ).clamp()

    def _extract_from_full_text(self, full_text, width: int, height: int) -> tuple[List[TextRegion], int, int]:
        regions: List[TextRegion] = []
        idx = 1
        raw_candidates = 0

        for page in getattr(full_text, "pages", []) or []:
            for block in getattr(page, "blocks", []) or []:
                for paragraph in getattr(block, "paragraphs", []) or []:
                    bbox = None
                    if getattr(paragraph, "bounding_box", None):
                        bbox = self._sanitize_bbox(
                            paragraph.bounding_box.vertices, width, height
                        )
                    words = getattr(paragraph, "words", []) or []
                    if words:
                        raw_candidates += 1
                    text_parts: List[str] = []
                    confidences: List[float] = []
                    for word in words:
                        symbols = getattr(word, "symbols", []) or []
                        word_text = "".join(getattr(sym, "text", "") for sym in symbols)
                        if word_text:
                            text_parts.append(word_text)
                        word_conf = getattr(word, "confidence", None)
                        if isinstance(word_conf, (int, float)):
                            confidences.append(float(word_conf))

                    combined_text = " ".join(text_parts).strip()
                    conf_val = sum(confidences) / len(confidences) if confidences else None

                    if combined_text and bbox:
                        regions.append(
                            TextRegion(
                                id=str(idx),
                                text=combined_text,
                                bbox=bbox,
                                confidence=conf_val,
                            )
                        )
                        idx += 1

        return regions, raw_candidates, len(regions)

    def _extract_from_annotations(
        self, annotations, width: int, height: int
    ) -> tuple[List[TextRegion], int, int]:
        sanitized: List[tuple[str, BBox]] = []
        for ann in annotations:
            bbox = self._sanitize_bbox(ann.bounding_poly.vertices, width, height)
            if not bbox:
                continue
            sanitized.append((ann.description, bbox))

        sanitized.sort(key=lambda item: (item[1].y_min, item[1].x_min))
        grouped: List[List[tuple[str, BBox]]] = []

        def same_line(box_a: BBox, box_b: BBox) -> bool:
            overlap_y = min(box_a.y_max, box_b.y_max) - max(box_a.y_min, box_b.y_min)
            height_span = max(box_a.y_max, box_b.y_max) - min(box_a.y_min, box_b.y_min)
            return (overlap_y / height_span) >= 0.5 if height_span else False

        for text, bbox in sanitized:
            if not grouped:
                grouped.append([(text, bbox)])
                continue

            last_line = grouped[-1]
            last_bbox = last_line[-1][1]
            gap_px = 0.0
            if bbox.x_min > last_bbox.x_max:
                gap_px = (bbox.x_min - last_bbox.x_max) * width
            elif bbox.x_max < last_bbox.x_min:
                gap_px = (last_bbox.x_min - bbox.x_max) * width
            if same_line(last_bbox, bbox) and gap_px <= self.MERGE_GAP_PX:
                last_line.append((text, bbox))
            else:
                grouped.append([(text, bbox)])

        regions: List[TextRegion] = []
        idx = 1
        for group in grouped:
            texts = [t for t, _ in group]
            bbox_union = BBox(
                x_min=min(b.x_min for _, b in group),
                y_min=min(b.y_min for _, b in group),
                x_max=max(b.x_max for _, b in group),
                y_max=max(b.y_max for _, b in group),
            ).clamp()
            regions.append(
                TextRegion(
                    id=str(idx),
                    text=" ".join(texts).strip(),
                    bbox=bbox_union,
                    confidence=None,
                )
            )
            idx += 1

        return regions, len(sanitized), len(regions)

    def _is_noise_text(self, text: str) -> bool:
        stripped = text.strip()
        if len(stripped) < self.MIN_TEXT_LEN:
            return True
        # Solo puntuación o símbolos
        import re

        return re.fullmatch(r"[\W_]+", stripped) is not None

    def _filter_regions(
        self, regions: List[TextRegion], width: int, height: int
    ) -> List[TextRegion]:
        filtered: List[TextRegion] = []
        for region in regions:
            if not region.bbox:
                continue
            area_ratio = (region.bbox.x_max - region.bbox.x_min) * (
                region.bbox.y_max - region.bbox.y_min
            )
            if area_ratio < self.MIN_AREA_RATIO:
                self.last_discarded_region_count += 1
                continue
            conf = region.confidence if region.confidence is not None else 1.0
            if conf < self.MIN_CONFIDENCE:
                self.last_discarded_region_count += 1
                continue
            if self._is_noise_text(region.text):
                self.last_discarded_region_count += 1
                continue
            filtered.append(region)

        return filtered

    def _merge_nearby_regions(
        self, regions: List[TextRegion], width: int, height: int
    ) -> List[TextRegion]:
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

        def horizontal_gap_px(a: BBox, b: BBox) -> float:
            if a.x_max < b.x_min:
                return (b.x_min - a.x_max) * width
            if b.x_max < a.x_min:
                return (a.x_min - b.x_max) * width
            return 0.0

        for region in sorted_regions:
            if not merged:
                merged.append(region)
                continue

            last = merged[-1]
            overlap = iou(last.bbox, region.bbox)
            gap = horizontal_gap_px(last.bbox, region.bbox)
            if overlap >= self.MERGE_IOU_THRESHOLD or (
                close_on_y(last.bbox, region.bbox) and gap <= self.MERGE_GAP_PX
            ):
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

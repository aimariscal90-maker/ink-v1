from __future__ import annotations

import logging
from pathlib import Path
from typing import List, Sequence

from google.cloud import vision

from app.models.text import BBox, TextRegion
from app.services.cache_service import CacheService


logger = logging.getLogger(__name__)


class OcrService:
    """
    Extrae regiones de texto desde una imagen usando Google Cloud Vision OCR.
    """

    MIN_AREA_RATIO = 0.0005
    MIN_AREA_PX = 120
    MIN_TEXT_LEN = 3
    MIN_CONFIDENCE = 0.5
    MERGE_GAP_PX = 24
    MERGE_IOU_THRESHOLD = 0.2
    MERGE_DISTANCE_PX = 32
    HARD_CAP_PER_PAGE = 200

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

        if getattr(full_text, "pages", None):
            regions, raw_candidates, _ = self._extract_from_full_text(
                full_text, width, height
            )
        elif annotations:
            regions, raw_candidates, _ = self._extract_from_annotations(
                annotations[1:], width, height
            )

        self.regions_detected_raw = raw_candidates

        grouped_regions = self._group_into_paragraphs(regions, width, height)
        self.regions_after_paragraph_grouping = len(grouped_regions)

        filtered = self._filter_regions(grouped_regions, width, height)
        self.regions_after_filter = len(filtered)

        merged = self._merge_nearby_regions(filtered, width, height)
        self.regions_after_merge = len(merged)

        logger.debug(
            "OCR metrics raw=%d grouped=%d filtered=%d merged=%d invalid=%d discarded=%d merged_ops=%d",
            self.regions_detected_raw,
            self.regions_after_paragraph_grouping,
            self.regions_after_filter,
            self.regions_after_merge,
            self.last_invalid_bbox_count,
            self.last_discarded_region_count,
            self.last_merged_region_count,
        )

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

        x_min = max(0.0, min(min(xs), width))
        y_min = max(0.0, min(min(ys), height))
        x_max = max(0.0, min(max(xs), width))
        y_max = max(0.0, min(max(ys), height))

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
        min_area_px = max(self.MIN_AREA_PX, int(width * height * self.MIN_AREA_RATIO))
        if (
            pixel_w < 2
            or pixel_h < 2
            or pixel_w * pixel_h < min_area_px
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

    def _extract_from_full_text(
        self, full_text, width: int, height: int
    ) -> tuple[List[TextRegion], int, int]:
        """Extrae bloques de texto a nivel de párrafo.

        Procesar a nivel de palabra genera cientos de regiones pequeñas. Aquí
        consolidamos cada párrafo en una sola región desde el OCR de Google,
        usando el bbox del párrafo (o la unión de las palabras) y promediando
        la confianza.
        """

        regions: List[TextRegion] = []
        idx = 1
        raw_candidates = 0

        for page in getattr(full_text, "pages", []) or []:
            for block in getattr(page, "blocks", []) or []:
                for paragraph in getattr(block, "paragraphs", []) or []:
                    paragraph_bbox = None
                    if getattr(paragraph, "bounding_box", None):
                        paragraph_bbox = self._sanitize_bbox(
                            paragraph.bounding_box.vertices, width, height
                        )

                    word_texts: List[str] = []
                    word_bboxes: List[BBox] = []
                    word_confidences: List[float] = []

                    for word in getattr(paragraph, "words", []) or []:
                        bbox = None
                        if getattr(word, "bounding_box", None):
                            bbox = self._sanitize_bbox(
                                word.bounding_box.vertices, width, height
                            )
                        if not bbox and paragraph_bbox:
                            bbox = paragraph_bbox
                        if not bbox:
                            continue

                        symbols = getattr(word, "symbols", []) or []
                        word_text = "".join(getattr(sym, "text", "") for sym in symbols).strip()
                        if not word_text:
                            continue

                        word_texts.append(word_text)
                        word_bboxes.append(bbox)
                        word_conf = getattr(word, "confidence", None)
                        if isinstance(word_conf, (int, float)):
                            word_confidences.append(float(word_conf))

                    if not word_texts:
                        continue

                    raw_candidates += 1

                    bbox = paragraph_bbox
                    if not bbox and word_bboxes:
                        bbox = self._union_bboxes(word_bboxes)
                    if not bbox:
                        continue

                    confidence = (
                        sum(word_confidences) / len(word_confidences)
                        if word_confidences
                        else None
                    )

                    regions.append(
                        TextRegion(
                            id=str(idx),
                            text=" ".join(word_texts).strip(),
                            bbox=bbox,
                            confidence=confidence,
                        )
                    )
                    idx += 1

        return regions, raw_candidates, len(regions)

    def _extract_from_annotations(
        self, annotations, width: int, height: int
    ) -> tuple[List[TextRegion], int, int]:
        regions: List[TextRegion] = []
        idx = 1
        raw_candidates = 0
        for ann in annotations:
            text = getattr(ann, "description", "").strip()
            if not text:
                continue
            raw_candidates += 1

            bbox = self._sanitize_bbox(ann.bounding_poly.vertices, width, height)
            if not bbox:
                continue

            regions.append(
                TextRegion(
                    id=str(idx),
                    text=text,
                    bbox=bbox,
                    confidence=None,
                )
            )
            idx += 1

        return regions, raw_candidates, len(regions)

    def _horizontal_gap_px(self, a: BBox, b: BBox, width: int) -> float:
        if a.x_max < b.x_min:
            return (b.x_min - a.x_max) * width
        if b.x_max < a.x_min:
            return (a.x_min - b.x_max) * width
        return 0.0

    def _vertical_gap_px(self, a: BBox, b: BBox, height: int) -> float:
        if a.y_max < b.y_min:
            return (b.y_min - a.y_max) * height
        if b.y_max < a.y_min:
            return (a.y_min - b.y_max) * height
        return 0.0

    def _iou(self, a: BBox, b: BBox) -> float:
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

    def _group_into_paragraphs(
        self, word_regions: Sequence[TextRegion], width: int, height: int
    ) -> List[TextRegion]:
        if not word_regions:
            return []

        sorted_words = sorted(word_regions, key=lambda r: (r.bbox.y_min, r.bbox.x_min))

        lines: List[List[TextRegion]] = []
        for word in sorted_words:
            if not lines:
                lines.append([word])
                continue

            last_line = lines[-1]
            last_bbox = self._union_bbox(last_line)
            if self._is_same_line(last_bbox, word.bbox, width, height):
                lines[-1].append(word)
            else:
                lines.append([word])

        line_regions = [self._merge_group_to_region(group) for group in lines]

        if not line_regions:
            return []

        paragraphs: List[List[TextRegion]] = []
        for line in line_regions:
            if not paragraphs:
                paragraphs.append([line])
                continue

            last_paragraph = paragraphs[-1]
            last_line_region = last_paragraph[-1]
            if self._line_belongs_to_paragraph(last_line_region, line, width, height):
                last_paragraph.append(line)
            else:
                paragraphs.append([line])

        return [self._merge_lines_to_paragraph(group) for group in paragraphs]

    def _is_same_line(self, a: BBox, b: BBox, width: int, height: int) -> bool:
        overlap_y = min(a.y_max, b.y_max) - max(a.y_min, b.y_min)
        height_span = max(a.y_max, b.y_max) - min(a.y_min, b.y_min)
        overlap_ratio = (overlap_y / height_span) if height_span else 0.0
        gap_y = self._vertical_gap_px(a, b, height)
        gap_x = self._horizontal_gap_px(a, b, width)
        avg_height_px = ((a.y_max - a.y_min) + (b.y_max - b.y_min)) / 2 * height
        similar_height = min(a.y_max - a.y_min, b.y_max - b.y_min) / max(
            a.y_max - a.y_min, b.y_max - b.y_min
        )

        return (
            overlap_ratio >= 0.35
            or (gap_y <= max(6.0, avg_height_px * 0.25) and similar_height >= 0.5)
        ) and gap_x <= self.MERGE_GAP_PX * 1.5

    def _line_belongs_to_paragraph(
        self, previous: TextRegion, current: TextRegion, width: int, height: int
    ) -> bool:
        prev_box = previous.bbox
        curr_box = current.bbox
        vertical_gap = self._vertical_gap_px(prev_box, curr_box, height)
        avg_height_px = ((prev_box.y_max - prev_box.y_min) + (curr_box.y_max - curr_box.y_min)) / 2 * height
        horizontal_overlap = min(prev_box.x_max, curr_box.x_max) - max(
            prev_box.x_min, curr_box.x_min
        )
        width_span = max(prev_box.x_max, curr_box.x_max) - min(prev_box.x_min, curr_box.x_min)
        overlap_ratio = (horizontal_overlap / width_span) if width_span else 0.0
        height_ratio = min(
            prev_box.y_max - prev_box.y_min, curr_box.y_max - curr_box.y_min
        ) / max(prev_box.y_max - prev_box.y_min, curr_box.y_max - curr_box.y_min)

        return (
            vertical_gap <= max(avg_height_px * 0.9, 12)
            and overlap_ratio >= 0.2
            and height_ratio >= 0.55
        )

    def _vertical_overlap_ratio(self, a: BBox, b: BBox) -> float:
        overlap_y = min(a.y_max, b.y_max) - max(a.y_min, b.y_min)
        height_span = max(a.y_max, b.y_max) - min(a.y_min, b.y_min)
        return (overlap_y / height_span) if height_span else 0.0

    def _horizontal_overlap_ratio(self, a: BBox, b: BBox) -> float:
        overlap_x = min(a.x_max, b.x_max) - max(a.x_min, b.x_min)
        width_span = max(a.x_max, b.x_max) - min(a.x_min, b.x_min)
        return (overlap_x / width_span) if width_span else 0.0

    def _union_bbox(self, regions: Sequence[TextRegion]) -> BBox:
        return BBox(
            x_min=min(r.bbox.x_min for r in regions),
            y_min=min(r.bbox.y_min for r in regions),
            x_max=max(r.bbox.x_max for r in regions),
            y_max=max(r.bbox.y_max for r in regions),
        ).clamp()

    def _union_bboxes(self, bboxes: Sequence[BBox]) -> BBox:
        return BBox(
            x_min=min(b.x_min for b in bboxes),
            y_min=min(b.y_min for b in bboxes),
            x_max=max(b.x_max for b in bboxes),
            y_max=max(b.y_max for b in bboxes),
        ).clamp()

    def _merge_group_to_region(self, group: Sequence[TextRegion]) -> TextRegion:
        bbox_union = self._union_bbox(group)
        texts = [r.text for r in group if r.text]
        confs = [r.confidence for r in group if r.confidence is not None]
        confidence = sum(confs) / len(confs) if confs else None
        return TextRegion(
            id=group[0].id,
            text=" ".join(texts).strip(),
            bbox=bbox_union,
            confidence=confidence,
        )

    def _merge_lines_to_paragraph(self, lines: Sequence[TextRegion]) -> TextRegion:
        bbox_union = self._union_bbox(lines)
        texts = [line.text for line in lines if line.text]
        confs = [line.confidence for line in lines if line.confidence is not None]
        confidence = sum(confs) / len(confs) if confs else None
        paragraph_text = "\n".join(texts).strip()
        return TextRegion(
            id=lines[0].id,
            text=paragraph_text,
            bbox=bbox_union,
            confidence=confidence,
        )

    def _deduplicate_regions(self, regions: List[TextRegion]) -> List[TextRegion]:
        deduped: List[TextRegion] = []
        for region in regions:
            is_dup = False
            for existing in deduped:
                if (
                    region.text.strip().lower() == existing.text.strip().lower()
                    and self._iou(region.bbox, existing.bbox) >= 0.9
                ):
                    self.last_discarded_region_count += 1
                    is_dup = True
                    break
            if not is_dup:
                deduped.append(region)

        return deduped

    def _merge_text(self, left: TextRegion, right: TextRegion, height: int) -> str:
        gap_y = self._vertical_gap_px(left.bbox, right.bbox, height)
        joiner = " "
        if gap_y > max(8.0, (right.bbox.y_min - left.bbox.y_max) * height):
            joiner = "\n"
        return f"{left.text}{joiner}{right.text}".strip()

    def _merge_confidence(self, left: TextRegion, right: TextRegion) -> float | None:
        confidences = [c for c in (left.confidence, right.confidence) if c is not None]
        if not confidences:
            return None
        return max(confidences)

    def _should_merge(
        self, left: TextRegion, right: TextRegion, width: int, height: int
    ) -> bool:
        overlap = self._iou(left.bbox, right.bbox)
        if overlap >= self.MERGE_IOU_THRESHOLD:
            return True

        h_gap = self._horizontal_gap_px(left.bbox, right.bbox, width)
        v_gap = self._vertical_gap_px(left.bbox, right.bbox, height)
        vert_overlap = self._vertical_overlap_ratio(left.bbox, right.bbox)
        horiz_overlap = self._horizontal_overlap_ratio(left.bbox, right.bbox)

        height_a = (left.bbox.y_max - left.bbox.y_min) * height
        height_b = (right.bbox.y_max - right.bbox.y_min) * height
        height_ratio = min(height_a, height_b) / max(height_a, height_b)

        if vert_overlap >= 0.3 and h_gap <= self.MERGE_GAP_PX * 1.5 and height_ratio >= 0.55:
            return True

        if horiz_overlap >= 0.3 and v_gap <= self.MERGE_DISTANCE_PX and height_ratio >= 0.55:
            return True

        distance_px = min(h_gap, v_gap)
        return distance_px <= self.MERGE_DISTANCE_PX and height_ratio >= 0.5

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
        if not regions:
            return []

        filtered: List[TextRegion] = []
        page_area = float(width * height)
        min_area_ratio = max(self.MIN_AREA_RATIO, self.MIN_AREA_PX / page_area)

        for region in regions:
            if not region.bbox:
                continue
            area_ratio = (region.bbox.x_max - region.bbox.x_min) * (
                region.bbox.y_max - region.bbox.y_min
            )
            if area_ratio < min_area_ratio:
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

        filtered = self._deduplicate_regions(filtered)

        if len(filtered) > self.HARD_CAP_PER_PAGE:
            scored = sorted(
                filtered,
                key=lambda r: (
                    (r.confidence if r.confidence is not None else 1.0)
                    * (r.bbox.x_max - r.bbox.x_min)
                    * (r.bbox.y_max - r.bbox.y_min)
                ),
                reverse=True,
            )
            excess = len(filtered) - self.HARD_CAP_PER_PAGE
            self.last_discarded_region_count += excess
            filtered = scored[: self.HARD_CAP_PER_PAGE]

        return filtered

    def _merge_nearby_regions(
        self, regions: List[TextRegion], width: int, height: int
    ) -> List[TextRegion]:
        if not regions:
            return []

        # Orden determinista top-to-bottom, left-to-right
        sorted_regions = sorted(regions, key=lambda r: (r.bbox.y_min, r.bbox.x_min))
        merged: List[TextRegion] = []

        for region in sorted_regions:
            if not merged:
                merged.append(region)
                continue

            last = merged[-1]
            if self._should_merge(last, region, width, height):
                union_bbox = self._union_bbox([last, region])
                merged[-1] = TextRegion(
                    id=last.id,
                    text=self._merge_text(last, region, height),
                    bbox=union_bbox,
                    confidence=self._merge_confidence(last, region),
                )
                self.last_merged_region_count += 1
            else:
                merged.append(region)

        # Reasignar ids secuenciales para mantener orden
        for idx, region in enumerate(merged, start=1):
            region.id = str(idx)

        return merged

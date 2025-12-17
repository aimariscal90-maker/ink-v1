"""Lógica de extracción de texto desde imágenes usando Google Vision OCR."""

from __future__ import annotations

import math
import re
from pathlib import Path
from typing import Iterable, List

from google.cloud import vision

from app.models.text import BBox, TextRegion
from app.services.cache_service import CacheService
from app.services.region_filter import RegionKind, classify_region
from app.core.config import get_settings


class OcrService:
    """
    Extrae regiones de texto desde una imagen usando Google Cloud Vision OCR.
    """

    def __init__(self, cache_service: CacheService | None = None) -> None:
        self.client = None
        self.cache = cache_service or CacheService()
        self.settings = get_settings()
        self.regions_detected_raw: int = 0
        self.regions_after_paragraph_grouping: int = 0
        self.regions_after_filter: int = 0
        self.regions_after_merge: int = 0
        self.last_invalid_bbox_count: int = 0
        self.last_discarded_region_count: int = 0
        self.last_merged_region_count: int = 0
        self.ocr_fallback_used_count: int = 0

    def _get_client(self):
        """Crea el cliente de Vision sólo cuando se necesita."""
        if self.client is None:
            self.client = vision.ImageAnnotatorClient()
        return self.client

    def extract_text_regions(self, image_path: Path) -> List[TextRegion]:
        """
        Devuelve todas las regiones de texto detectadas con bounding boxes normalizados.
        """

        with open(image_path, "rb") as f:
            content = f.read()

        image_hash = CacheService.key_hash(content)
        cache_key = f"ocr:{image_hash}"

        cached = self.cache.get_json(cache_key)
        if cached and isinstance(cached.get("regions"), list):
            regions = [TextRegion.model_validate(region) for region in cached["regions"]]
            self.regions_detected_raw = len(regions)
            self.regions_after_paragraph_grouping = len(regions)
            self.regions_after_filter = len(regions)
            self.regions_after_merge = len(regions)
            self.last_invalid_bbox_count = 0
            self.last_discarded_region_count = 0
            self.last_merged_region_count = 0
            self.ocr_fallback_used_count = 0
            return regions

        image = vision.Image(content=content)
        client = self._get_client()
        response = client.text_detection(image=image)

        if response.error.message:
            raise RuntimeError(f"Google Vision OCR error: {response.error.message}")

        annotations = response.text_annotations
        if not annotations:
            return []

        # Dimensiones reales de la imagen
        import PIL.Image

        with PIL.Image.open(image_path) as img:
            width, height = img.width, img.height

        raw_regions: List[TextRegion] = []
        invalid_bbox_count = 0

        # Primer elemento es TODO el texto; los siguientes son palabras/fragmentos
        for idx, ann in enumerate(annotations[1:], start=1):
            vertices = ann.bounding_poly.vertices

            # Pueden venir como None
            xs = [v.x or 0 for v in vertices]
            ys = [v.y or 0 for v in vertices]

            # Normalizar bounding box a [0,1]
            x_min = min(xs)
            y_min = min(ys)
            x_max = max(xs)
            y_max = max(ys)

            if x_min == x_max or y_min == y_max:
                invalid_bbox_count += 1
                continue

            bbox = BBox(
                x_min=x_min / width,
                y_min=y_min / height,
                x_max=x_max / width,
                y_max=y_max / height,
            ).clamp()

            raw_regions.append(
                TextRegion(
                    id=str(idx),
                    text=ann.description,
                    bbox=bbox,
                    confidence=None,  # Vision no da un score directo para cada palabra
                )
            )

        primary_regions = self._post_process_regions(
            regions=raw_regions,
            image_width=width,
            image_height=height,
            fallback=False,
        )
        self.ocr_fallback_used_count = 0

        if self.settings.ocr_enable_fallback and self._should_retry_ocr(
            raw_regions, primary_regions, width, height
        ):
            primary_regions = self._post_process_regions(
                regions=raw_regions,
                image_width=width,
                image_height=height,
                fallback=True,
            )
            self.ocr_fallback_used_count = 1

        self.last_invalid_bbox_count = invalid_bbox_count

        self.cache.set_json(
            cache_key, {"regions": [r.model_dump() for r in primary_regions]}
        )

        return primary_regions

    # ------------------------------------------------------------------
    # ------------------ Postprocesado para reducir ruido --------------
    # ------------------------------------------------------------------

    def _should_retry_ocr(
        self,
        raw_regions: List[TextRegion],
        processed_regions: List[TextRegion],
        image_width: int,
        image_height: int,
    ) -> bool:
        """Decide si merece la pena repetir el postproceso con ajustes suaves."""
        if len(raw_regions) <= 2 or len(processed_regions) == 0:
            return True

        raw_text = " ".join(r.text for r in raw_regions if r.text)
        total_chars = len(raw_text)
        ascii_letters = sum(1 for c in raw_text if c.isascii() and c.isalpha())

        if len(raw_regions) < 5 and total_chars < 25:
            return True
        if len(processed_regions) < 2 and ascii_letters > 0 and total_chars < 40:
            return True

        # If all boxes are extremely tiny, give fallback a chance to loosen thresholds
        avg_area = sum(
            (r.bbox.x_max - r.bbox.x_min) * (r.bbox.y_max - r.bbox.y_min)
            for r in raw_regions
        ) / max(len(raw_regions), 1)
        if avg_area < self.settings.ocr_min_area_ratio * 0.75:
            return True

        return False

    def _post_process_regions(
        self,
        regions: List[TextRegion],
        image_width: int,
        image_height: int,
        fallback: bool = False,
    ) -> List[TextRegion]:
        """
        Reduce explosión de palabras agrupando por líneas/párrafos, filtrando ruido
        y mergeando globos cercanos.
        """

        self.regions_detected_raw = len(regions)
        if not regions:
            self.regions_after_paragraph_grouping = 0
            self.regions_after_filter = 0
            self.regions_after_merge = 0
            self.last_discarded_region_count = 0
            self.last_merged_region_count = 0
            return []

        line_grouped = self._group_by_lines(regions, image_width, image_height)
        paragraph_grouped = self._group_lines_into_blocks(
            line_grouped, image_width, image_height
        )
        self.regions_after_paragraph_grouping = len(paragraph_grouped)

        filtered = self._filter_regions(
            paragraph_grouped, image_width, image_height, fallback=fallback
        )
        self.regions_after_filter = len(filtered)

        merged = self._merge_nearby_regions(filtered, image_width, image_height)
        self.regions_after_merge = len(merged)

        self.last_merged_region_count = max(0, len(filtered) - len(merged))

        # Orden de lectura estable: agrupar por bucket Y para evitar micro-variaciones
        sorted_regions = sorted(
            merged,
            key=lambda r: (
                math.floor(r.bbox.y_min * image_height / 4),
                r.bbox.x_min,
            ),
        )
        return sorted_regions

    def _group_by_lines(
        self, regions: List[TextRegion], image_width: int, image_height: int
    ) -> List[TextRegion]:
        y_tolerance_px = self.settings.ocr_line_tolerance_px

        sorted_regions = sorted(regions, key=lambda r: (r.bbox.y_min, r.bbox.x_min))
        lines: List[List[TextRegion]] = []

        for region in sorted_regions:
            y_center = (region.bbox.y_min + region.bbox.y_max) / 2
            if not lines:
                lines.append([region])
                continue

            last_line = lines[-1]
            last_center = sum(
                (r.bbox.y_min + r.bbox.y_max) / 2 for r in last_line
            ) / len(last_line)
            if abs(y_center - last_center) * image_height <= y_tolerance_px:
                last_line.append(region)
            else:
                lines.append([region])

        grouped: List[TextRegion] = []
        for idx, line in enumerate(lines):
            ordered = sorted(line, key=lambda r: r.bbox.x_min)
            grouped.append(self._aggregate_regions(ordered, f"line-{idx}"))
        return grouped

    def _group_lines_into_blocks(
        self, lines: List[TextRegion], image_width: int, image_height: int
    ) -> List[TextRegion]:
        if not lines:
            return []

        block_gap_px = self.settings.ocr_block_gap_px
        min_x_overlap_ratio = self.settings.ocr_min_x_overlap_ratio

        ordered = sorted(lines, key=lambda r: (r.bbox.y_min, r.bbox.x_min))
        blocks: List[List[TextRegion]] = [[ordered[0]]]

        for line in ordered[1:]:
            current_block = blocks[-1]
            block_bbox = self._union_bbox([r.bbox for r in current_block])
            x_overlap = self._x_overlap_ratio(block_bbox, line.bbox)
            vertical_gap_px = max(0.0, (line.bbox.y_min - block_bbox.y_max) * image_height)

            if x_overlap >= min_x_overlap_ratio and vertical_gap_px <= block_gap_px:
                current_block.append(line)
            else:
                blocks.append([line])

        return [self._aggregate_regions(block, f"block-{idx}") for idx, block in enumerate(blocks)]

    def _filter_regions(
        self,
        regions: List[TextRegion],
        image_width: int,
        image_height: int,
        fallback: bool,
    ) -> List[TextRegion]:
        settings = self.settings
        min_conf = settings.ocr_min_confidence * (0.7 if fallback else 1.0)
        min_area_ratio = settings.ocr_min_area_ratio * (0.5 if fallback else 1.0)
        max_area_ratio = settings.ocr_max_area_ratio
        min_w_px = settings.ocr_min_width_px
        min_h_px = settings.ocr_min_height_px

        noise_regex = re.compile(r"^[^A-Za-z0-9ÁÉÍÓÚÜÑáéíóúüñ]+$")
        repeated_regex = re.compile(r"^(.)\1{3,}$")

        valid_regions: List[TextRegion] = []
        discarded = 0

        for region in regions:
            text = region.text.strip()
            if len(text) < 3:
                discarded += 1
                continue

            confidence = region.confidence if region.confidence is not None else 1.0
            if confidence < min_conf:
                discarded += 1
                continue

            bbox = region.bbox
            width = (bbox.x_max - bbox.x_min) * image_width
            height = (bbox.y_max - bbox.y_min) * image_height
            area_ratio = (bbox.x_max - bbox.x_min) * (bbox.y_max - bbox.y_min)

            if area_ratio < min_area_ratio or area_ratio > max_area_ratio:
                discarded += 1
                continue
            if width < min_w_px or height < min_h_px:
                discarded += 1
                continue
            if noise_regex.match(text) or repeated_regex.match(text):
                discarded += 1
                continue

            non_alnum_ratio = (
                sum(1 for c in text if not c.isalnum()) / max(1, len(text))
            )
            if non_alnum_ratio > 0.6:
                discarded += 1
                continue

            region_kind = classify_region(
                text=text,
                bbox=bbox,
                confidence=confidence,
                page_w=image_width,
                page_h=image_height,
            )
            if settings.ocr_filter_non_dialogue and region_kind == RegionKind.NON_DIALOGUE:
                discarded += 1
                continue

            valid_regions.append(region)

        self.last_discarded_region_count = discarded
        return valid_regions

    def _merge_nearby_regions(
        self, regions: List[TextRegion], image_width: int, image_height: int
    ) -> List[TextRegion]:
        """Une cajas cercanas que probablemente formen parte del mismo globo."""
        if not regions:
            return []

        MERGE_GAP_PX = self.settings.ocr_merge_gap_px
        MIN_OVERLAP_RATIO = 0.1
        MAX_AREA_GROWTH = self.settings.ocr_merge_max_area_growth_ratio
        MIN_HEIGHT_RATIO = self.settings.ocr_merge_min_height_ratio
        MAX_CENTER_DISTANCE_RATIO = self.settings.ocr_merge_max_center_distance_ratio
        MIN_ALIGNMENT_OVERLAP = self.settings.ocr_merge_min_alignment_overlap
        MAX_CHARACTERS = self.settings.ocr_merge_max_characters
        GUTTER_GAP_PX = self.settings.ocr_merge_gutter_gap_px

        remaining = sorted(regions, key=lambda r: (r.bbox.y_min, r.bbox.x_min))
        merged: List[TextRegion] = []

        def _bbox_area(bbox: BBox) -> float:
            return max(0.0, (bbox.x_max - bbox.x_min) * (bbox.y_max - bbox.y_min))

        while remaining:
            current = remaining.pop(0)
            merged_with_current: List[TextRegion] = [current]
            to_remove = []
            for idx, candidate in enumerate(remaining):
                current_bbox = self._union_bbox([r.bbox for r in merged_with_current])

                x_gap_px = self._axis_gap_px(
                    current_bbox.x_min,
                    current_bbox.x_max,
                    candidate.bbox.x_min,
                    candidate.bbox.x_max,
                    image_width,
                )
                y_gap_px = self._axis_gap_px(
                    current_bbox.y_min,
                    current_bbox.y_max,
                    candidate.bbox.y_min,
                    candidate.bbox.y_max,
                    image_height,
                )

                if x_gap_px > GUTTER_GAP_PX or y_gap_px > GUTTER_GAP_PX:
                    continue

                x_overlap = self._x_overlap_ratio(current_bbox, candidate.bbox)
                y_overlap = self._y_overlap_ratio(current_bbox, candidate.bbox)

                spatial_proximity = (
                    (x_overlap >= MIN_OVERLAP_RATIO and y_gap_px <= MERGE_GAP_PX)
                    or (y_overlap >= MIN_OVERLAP_RATIO and x_gap_px <= MERGE_GAP_PX)
                    or (x_gap_px <= MERGE_GAP_PX and y_gap_px <= MERGE_GAP_PX)
                )

                if not spatial_proximity:
                    continue

                current_height_px = (current_bbox.y_max - current_bbox.y_min) * image_height
                candidate_height_px = (candidate.bbox.y_max - candidate.bbox.y_min) * image_height
                if current_height_px <= 0 or candidate_height_px <= 0:
                    continue

                height_ratio = min(current_height_px, candidate_height_px) / max(
                    current_height_px, candidate_height_px
                )
                if height_ratio < MIN_HEIGHT_RATIO:
                    continue

                y_center_delta_px = abs(
                    ((current_bbox.y_min + current_bbox.y_max) / 2)
                    - ((candidate.bbox.y_min + candidate.bbox.y_max) / 2)
                ) * image_height
                avg_height_px = (current_height_px + candidate_height_px) / 2
                center_distance_ratio = y_center_delta_px / max(avg_height_px, 1e-6)
                if center_distance_ratio > MAX_CENTER_DISTANCE_RATIO:
                    continue

                alignment_overlap = max(x_overlap, y_overlap)
                if alignment_overlap < MIN_ALIGNMENT_OVERLAP:
                    continue

                union_bbox = self._union_bbox([current_bbox, candidate.bbox])
                union_area = _bbox_area(union_bbox)
                combined_area = _bbox_area(current_bbox) + _bbox_area(candidate.bbox)
                if combined_area == 0:
                    continue
                area_growth_ratio = union_area / combined_area
                if area_growth_ratio > MAX_AREA_GROWTH:
                    continue

                total_characters = sum(len(r.text) for r in merged_with_current) + len(
                    candidate.text
                )
                if total_characters > MAX_CHARACTERS:
                    continue

                merged_with_current.append(candidate)
                to_remove.append(idx)

            for idx in reversed(to_remove):
                remaining.pop(idx)

            merged.append(
                self._aggregate_regions(
                    merged_with_current, f"merged-{len(merged_with_current)}"
                )
            )

        return merged

    def _aggregate_regions(self, regions: Iterable[TextRegion], new_id: str) -> TextRegion:
        bbox = self._union_bbox([r.bbox for r in regions])
        texts = [r.text.strip() for r in regions if r.text]
        text = " ".join(t for t in texts if t).strip()
        if not text and texts:
            text = texts[0]

        weighted_conf_sum = 0.0
        total_weight = 0
        for r in regions:
            conf = r.confidence if r.confidence is not None else 1.0
            weight = max(len(r.text.strip()), 1)
            weighted_conf_sum += conf * weight
            total_weight += weight

        confidence = weighted_conf_sum / total_weight if total_weight else None

        return TextRegion(id=new_id, text=text, bbox=bbox, confidence=confidence)

    def _union_bbox(self, bboxes: Iterable[BBox]) -> BBox:
        x_mins = [b.x_min for b in bboxes]
        y_mins = [b.y_min for b in bboxes]
        x_maxs = [b.x_max for b in bboxes]
        y_maxs = [b.y_max for b in bboxes]
        return BBox(
            x_min=min(x_mins),
            y_min=min(y_mins),
            x_max=max(x_maxs),
            y_max=max(y_maxs),
        ).clamp()

    def _axis_gap_px(
        self,
        start_a: float,
        end_a: float,
        start_b: float,
        end_b: float,
        scale: int,
    ) -> float:
        if end_a < start_b:
            return (start_b - end_a) * scale
        if end_b < start_a:
            return (start_a - end_b) * scale
        return 0.0

    def _x_overlap_ratio(self, a: BBox, b: BBox) -> float:
        overlap = min(a.x_max, b.x_max) - max(a.x_min, b.x_min)
        if overlap <= 0:
            return 0.0
        min_width = min(a.x_max - a.x_min, b.x_max - b.x_min)
        if min_width <= 0:
            return 0.0
        return overlap / min_width

    def _y_overlap_ratio(self, a: BBox, b: BBox) -> float:
        overlap = min(a.y_max, b.y_max) - max(a.y_min, b.y_min)
        if overlap <= 0:
            return 0.0
        min_height = min(a.y_max - a.y_min, b.y_max - b.y_min)
        if min_height <= 0:
            return 0.0
        return overlap / min_height

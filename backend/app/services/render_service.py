from __future__ import annotations

"""Pinta el texto traducido encima de las imágenes originales."""

from dataclasses import dataclass
from pathlib import Path
from typing import Any, List, Tuple

import logging
from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageStat

from app.core.config import get_settings
from app.models.text import BBox, TranslatedRegion
from app.services.layout_service import LayoutResult, LayoutService


@dataclass
class RenderResult:
    output_image: Path
    qa_overflow_count: int = 0
    qa_retry_count: int = 0
    render_overflow_count: int = 0
    min_font_hit_count: int = 0
    summarize_triggered_count: int = 0
    cleanup_retry_count: int = 0
    untranslated_skip_count: int = 0
    overflow_skip_count: int = 0
    layouts: List[LayoutResult] | None = None


class RenderService:
    """
    Se encarga de pintar el texto traducido sobre la imagen original.
    """

    def __init__(
        self,
        font_path: Path | str = "DejaVuSans.ttf",
        max_font_size: int = 42,
        min_font_size: int = 10,
        line_height: float = 1.2,
        padding_px: int = 6,
        min_render_size_px: int = 6,
        translation_service: Any | None = None,
        min_readable_font: int | None = None,
    ) -> None:
        self.font_path = Path(font_path)
        self.max_font_size = max_font_size
        self.min_font_size = min_font_size
        self.line_height = line_height
        self.padding_px = padding_px
        self.min_render_size_px = min_render_size_px
        self.translation_service = translation_service
        settings = get_settings()
        self.min_readable_font = min_readable_font or settings.render_min_readable_font_px
        self.summary_max_chars = settings.render_summary_max_chars
        self.summary_min_delta = settings.render_summary_min_delta
        self.mask_tolerance = settings.render_mask_tolerance
        self.layout_service = LayoutService()
        self.logger = logging.getLogger(__name__)

    def render_page(
        self,
        input_image: Path,
        regions: List[TranslatedRegion],
        output_image: Path | None = None,
    ) -> RenderResult:
        """
        Dibuja todas las regiones traducidas sobre la imagen y devuelve
        la ruta del archivo de salida.
        """

        if not input_image.exists():
            raise FileNotFoundError(f"Input image not found: {input_image}")

        img = Image.open(input_image).convert("RGBA")
        draw = ImageDraw.Draw(img)

        width, height = img.width, img.height
        overflow_count = 0
        retry_count = 0
        render_overflow = 0
        min_font_hits = 0
        summarize_hits = 0
        cleanup_retries = 0
        untranslated_skips = 0
        overflow_skips = 0
        layouts: List[LayoutResult] = []

        for region in regions:
            style = self._decide_style(region)
            text_to_render = region.translated_text
            if self._looks_untranslated(text_to_render):
                text_to_render = self._retry_translation(region)
                if self._looks_untranslated(text_to_render):
                    untranslated_skips += 1
                    self.logger.warning(
                        "Skipping region %s due to untranslated content", region.id
                    )
                    continue
            if style.get("keep_original"):
                text_to_render = region.original_text

            # 1) Convertimos el BBox normalizado [0,1] a coordenadas de píxel
            x1, y1, x2, y2 = self._bbox_to_pixels(region.bbox, width, height)

            if (x2 - x1) < self.min_render_size_px or (y2 - y1) < self.min_render_size_px:
                # Si la caja es minúscula, añadimos un poco de espacio para que quepa texto
                pad_needed_x = max(0, self.min_render_size_px - (x2 - x1))
                pad_needed_y = max(0, self.min_render_size_px - (y2 - y1))
                x1 = max(0, x1 - pad_needed_x // 2)
                x2 = min(width, x2 + pad_needed_x - pad_needed_x // 2)
                y1 = max(0, y1 - pad_needed_y // 2)
                y2 = min(height, y2 + pad_needed_y - pad_needed_y // 2)

            # Añadir algo de padding interno (mínimo padding_px) sin colapsar la caja
            raw_pad_x = min(self.padding_px, max(2, int((x2 - x1) * 0.05)))
            raw_pad_y = min(self.padding_px, max(2, int((y2 - y1) * 0.05)))
            pad_x = min(raw_pad_x + style["padding"], max(0, (x2 - x1 - 2) // 2))
            pad_y = min(raw_pad_y + style["padding"], max(0, (y2 - y1 - 2) // 2))
            box_x1 = x1 + pad_x
            box_y1 = y1 + pad_y
            box_x2 = x2 - pad_x
            box_y2 = y2 - pad_y

            area = (box_x1, box_y1, box_x2, box_y2)
            mask, mask_fill = self._build_balloon_mask(img, area, style["fill"])

            original_crop = img.crop(area).convert("L")
            self._clean_region(img, area, mask, mask_fill, expand_px=1)

            cleaned_crop = img.crop(area).convert("L")
            if self._has_residual_text(original_crop, cleaned_crop):
                cleanup_retries += 1
                # Segundo pase más agresivo con expansión y un fallback rectangular
                self._clean_region(
                    img,
                    area,
                    mask,
                    mask_fill,
                    expand_px=3,
                    feather_radius=1.2,
                    force_rect=True,
                )

            # 3) Calcular tamaño de fuente y texto envuelto que quepa en la caja
            box_width = max(1, box_x2 - box_x1)
            box_height = max(1, box_y2 - box_y1)

            text_for_layout = (
                text_to_render.replace(" ", "\u00a0")
                if not style["wrap"]
                else text_to_render
            )
            layout_result = self.layout_service.fit_text_to_box(
                text=text_for_layout,
                box_w=box_width,
                box_h=box_height,
                font_path=self.font_path,
                max_font=min(self.max_font_size + style["font_bonus"], 64),
                min_font=max(self.min_font_size, style["min_font"]),
                line_height=style["line_height"],
            )

            padding = min(pad_x, pad_y)
            overflow = self.layout_service.check_overflow(
                layout_result, box_width, box_height, padding=padding
            )

            if overflow or not layout_result.fits:
                overflow_count += 1
                retry_count += 1
                render_overflow += 1
                cleaned_text = self._normalize_text(text_to_render)
                layout_result = self.layout_service.fit_text_to_box(
                    text=cleaned_text,
                    box_w=box_width,
                    box_h=box_height,
                    font_path=self.font_path,
                    max_font=min(layout_result.font_size, self.max_font_size - 1),
                    min_font=max(self.min_font_size, layout_result.font_size - 2),
                    line_height=max(1.1, self.line_height * 0.95),
                )
                overflow = self.layout_service.check_overflow(
                    layout_result, box_width, box_height, padding=padding
                )

            if layout_result.font_size < self.min_readable_font:
                min_font_hits += 1

            if (
                (overflow or layout_result.font_size < self.min_readable_font)
                and self.translation_service
                and len(text_to_render) > self.summary_min_delta
                and not style.get("keep_original")
            ):
                max_chars = max(
                    self.summary_min_delta,
                    min(
                        self.summary_max_chars,
                        int((box_width * box_height) / max(self.min_readable_font, 1)),
                    ),
                )
                text_to_render = self.translation_service.summarize_to_length(
                    region.original_text, text_to_render, max_chars=max_chars
                )
                summarize_hits += 1
                text_for_layout = (
                    text_to_render.replace(" ", "\u00a0")
                    if not style["wrap"]
                    else text_to_render
                )
                layout_result = self.layout_service.fit_text_to_box(
                    text=text_for_layout,
                    box_w=box_width,
                    box_h=box_height,
                    font_path=self.font_path,
                    max_font=min(self.max_font_size + style["font_bonus"], 64),
                    min_font=max(self.min_font_size, style["min_font"]),
                    line_height=style["line_height"],
                )
                overflow = self.layout_service.check_overflow(
                    layout_result, box_width, box_height, padding=padding
                )

            if overflow and layout_result.font_size <= self.min_font_size:
                layout_result = self._truncate_to_fit(
                    layout_result,
                    box_width,
                    box_height,
                )
                overflow = self.layout_service.check_overflow(
                    layout_result, box_width, box_height, padding=padding
                )

            layouts.append(layout_result)

            font = self._get_base_font(layout_result.font_size)

            # 4) Calcular posición para centrar el texto
            text_block_w = layout_result.final_text_block_w
            text_block_h = layout_result.final_text_block_h

            if overflow or not layout_result.fits:
                overflow_skips += 1
                self.logger.warning(
                    "Skipping render for region %s due to overflow (w=%s h=%s)",
                    region.id,
                    text_block_w,
                    text_block_h,
                )
                continue

            text_x = box_x1 + (box_width - text_block_w) // 2
            text_y = box_y1 + (box_height - text_block_h) // 2

            # 5) Dibujar texto en negro línea a línea centrado
            current_y = text_y
            for line in layout_result.lines:
                line_w = self.layout_service._line_width(line, font)
                line_x = text_x + (text_block_w - line_w) // 2
                draw.text((line_x, current_y), line, font=font, fill="black")
                current_y += layout_result.line_height

        # Determinar ruta de salida
        if output_image is None:
            output_image = input_image.with_name(input_image.stem + "_translated.png")

        img.save(output_image)
        return RenderResult(
            output_image=output_image,
            qa_overflow_count=overflow_count,
            qa_retry_count=retry_count,
            render_overflow_count=render_overflow,
            min_font_hit_count=min_font_hits,
            summarize_triggered_count=summarize_hits,
            cleanup_retry_count=cleanup_retries,
            untranslated_skip_count=untranslated_skips,
            overflow_skip_count=overflow_skips,
            layouts=layouts,
        )

    # ---------- Helpers internos ----------

    def _decide_style(self, region: TranslatedRegion) -> dict[str, Any]:
        kind = (region.region_kind or "").lower()
        text = region.translated_text
        base = {
            "fill": "white",
            "padding": 0,
            "line_height": self.line_height,
            "font_bonus": 0,
            "min_font": self.min_font_size,
            "wrap": True,
            "keep_original": False,
        }

        if kind == "narration":
            base.update(
                {
                    "fill": (245, 242, 232, 255),
                    "padding": 2,
                    "line_height": max(1.05, self.line_height * 0.95),
                    "font_bonus": -2,
                }
            )
        elif kind == "onomatopoeia" or self._looks_like_onomatopoeia(text):
            base.update(
                {
                    "fill": (255, 255, 255, 220),
                    "padding": -1,
                    "line_height": max(1.0, self.line_height * 0.9),
                    "font_bonus": 6,
                    "wrap": False,
                    "keep_original": True,
                }
            )

        return base

    def _looks_like_onomatopoeia(self, text: str) -> bool:
        cleaned = text.strip()
        if not cleaned:
            return False
        if cleaned.isupper() and len(cleaned) <= 8:
            return True
        return len(cleaned.split()) <= 2 and cleaned.isalpha() and cleaned.isupper()

    def _build_balloon_mask(
        self, image: Image.Image, area: tuple[int, int, int, int], fallback_fill: Any
    ) -> tuple[Image.Image | None, Any]:
        x1, y1, x2, y2 = area
        if x2 <= x1 or y2 <= y1:
            return None, fallback_fill

        crop = image.crop(area).convert("RGB")
        gray = crop.convert("L")
        histogram = gray.histogram()
        dominant = max(range(len(histogram)), key=lambda i: histogram[i])
        tolerance = max(6, min(self.mask_tolerance, 255 - dominant))

        mask = gray.point(lambda p: 255 if p >= dominant - tolerance else 0)
        mask = mask.filter(ImageFilter.MinFilter(3))

        coverage = sum(mask.histogram()[128:]) / max(1, crop.size[0] * crop.size[1])
        if coverage < 0.15:
            return None, fallback_fill

        return mask, fallback_fill

    def _clean_region(
        self,
        image: Image.Image,
        area: tuple[int, int, int, int],
        mask: Image.Image | None,
        fill: Any,
        expand_px: int = 1,
        feather_radius: float = 0.6,
        force_rect: bool = False,
    ) -> None:
        x1, y1, x2, y2 = area
        width, height = max(1, x2 - x1), max(1, y2 - y1)

        overlay = Image.new("RGBA", (width, height), fill)
        effective_mask: Image.Image | None = None

        if not force_rect and mask is not None:
            effective_mask = mask.convert("L")
            if expand_px > 0:
                size = max(3, expand_px * 2 + 1)
                effective_mask = effective_mask.filter(ImageFilter.MaxFilter(size))
            if feather_radius > 0:
                effective_mask = effective_mask.filter(
                    ImageFilter.GaussianBlur(radius=feather_radius)
                )

        if effective_mask is not None:
            image.paste(overlay, (x1, y1), effective_mask)
        else:
            draw = ImageDraw.Draw(image)
            draw.rectangle([x1, y1, x2, y2], fill=fill)

    def _bbox_to_pixels(self, bbox: BBox, width: int, height: int) -> Tuple[int, int, int, int]:
        """
        Convierte BBox normalizado [0,1] a coordenadas de píxel (enteros).
        """
        clamped = bbox.clamp()

        x1 = int(clamped.x_min * width)
        y1 = int(clamped.y_min * height)
        x2 = int(clamped.x_max * width)
        y2 = int(clamped.y_max * height)

        # Evitar cajas degeneradas y mantenernos dentro de la imagen
        x1 = max(0, min(x1, width - 1))
        y1 = max(0, min(y1, height - 1))
        x2 = max(x1 + 1, min(x2, width))
        y2 = max(y1 + 1, min(y2, height))

        return x1, y1, x2, y2

    def _get_base_font(self, size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
        """
        Devuelve una fuente. Intentamos usar una TrueType decente; si no,
        usamos la fuente por defecto de Pillow.
        """
        try:
            return self.layout_service.load_font(self.font_path, size)
        except Exception:
            return ImageFont.load_default()

    def _looks_untranslated(self, text: str) -> bool:
        if not text:
            return False

        english_hints = {
            "the",
            "and",
            "of",
            "you",
            "i",
            "my",
            "your",
            "is",
            "are",
            "was",
            "were",
            "when",
            "what",
            "who",
            "hello",
            "hi",
            "why",
            "where",
            "how",
            "brother",
            "sister",
            "long",
            "time",
        }

        tokens = [t.strip(".,;:!?¡¿()[]{}\"'") for t in text.split() if t.strip()]
        if not tokens:
            return False

        alpha_tokens = [t.lower() for t in tokens if any(ch.isalpha() for ch in t)]
        if not alpha_tokens:
            return False

        english_hits = [t for t in alpha_tokens if t in english_hints]
        english_ratio = len(english_hits) / max(1, len(alpha_tokens))
        ascii_ratio = len([t for t in alpha_tokens if t.isascii()]) / len(alpha_tokens)

        return english_ratio >= 0.35 or (english_ratio >= 0.2 and ascii_ratio > 0.6)

    def _retry_translation(self, region: TranslatedRegion) -> str:
        if not self.translation_service or not region.original_text:
            return region.translated_text
        try:
            return self.translation_service.translate_text_cached(
                region.original_text, target_lang="es"
            )
        except Exception:
            return region.translated_text

    def _dark_ratio(self, gray_image: Image.Image) -> float:
        stat = ImageStat.Stat(gray_image)
        histogram = gray_image.histogram()
        dark_pixels = sum(histogram[:80])
        total = max(1, gray_image.size[0] * gray_image.size[1])
        return dark_pixels / total

    def _edge_density(self, gray_image: Image.Image) -> float:
        edges = gray_image.filter(ImageFilter.FIND_EDGES)
        stat = ImageStat.Stat(edges)
        return sum(stat.mean) / max(1, len(stat.mean))

    def _has_residual_text(
        self, before: Image.Image, after: Image.Image, tolerance: float = 0.65
    ) -> bool:
        before_dark = self._dark_ratio(before)
        after_dark = self._dark_ratio(after)
        before_edges = self._edge_density(before)
        after_edges = self._edge_density(after)

        dark_ratio_ok = after_dark < before_dark * tolerance and after_dark < 0.12
        edge_ratio_ok = after_edges < before_edges * tolerance or after_edges < 1.5
        return not (dark_ratio_ok and edge_ratio_ok)

    def _normalize_text(self, text: str) -> str:
        compact = " ".join(text.split())
        return compact.replace("\u00a0", " ")

    def _truncate_to_fit(self, layout_result: LayoutResult, box_w: int, box_h: int) -> LayoutResult:
        font = self._get_base_font(layout_result.font_size)
        max_chars_lines: List[str] = []
        for line in layout_result.lines:
            truncated = line
            while truncated and self.layout_service._line_width(truncated + "...", font) > box_w:
                truncated = truncated[:-1]
            if truncated != line:
                truncated = truncated.rstrip() + "..."
            max_chars_lines.append(truncated)

        block_w, block_h = self.layout_service.measure_text(
            max_chars_lines, font, layout_result.font_size, self.line_height
        )
        fits = block_w <= box_w and block_h <= box_h

        return LayoutResult(
            font_size=layout_result.font_size,
            lines=max_chars_lines,
            line_height=layout_result.line_height,
            fits=fits,
            final_text_block_w=block_w,
            final_text_block_h=block_h,
        )

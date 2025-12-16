from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import List, Tuple

from PIL import Image, ImageDraw, ImageFont

from app.models.text import BBox, TranslatedRegion
from app.services.layout_service import LayoutResult, LayoutService


@dataclass
class RenderResult:
    output_image: Path
    qa_overflow_count: int = 0
    qa_retry_count: int = 0
    invalid_bbox_count: int = 0
    discarded_region_count: int = 0
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
        padding_px: int = 8,
    ) -> None:
        self.font_path = Path(font_path)
        self.max_font_size = max_font_size
        self.min_font_size = min_font_size
        self.line_height = line_height
        self.padding_px = padding_px
        self.layout_service = LayoutService()

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
        invalid_bbox_count = 0
        discarded_region_count = 0
        layouts: List[LayoutResult] = []

        for region in regions:
            pixel_bbox = self._sanitize_bbox(region.bbox, width, height)
            if pixel_bbox is None:
                invalid_bbox_count += 1
                continue

            # 1) Convertimos el BBox normalizado [0,1] a coordenadas de píxel
            x1, y1, x2, y2 = pixel_bbox

            # Añadir algo de padding interno (mínimo padding_px) sin colapsar la caja
            raw_pad_x = max(self.padding_px, int((x2 - x1) * 0.05))
            raw_pad_y = max(self.padding_px, int((y2 - y1) * 0.05))
            pad_x = min(raw_pad_x, max(0, (x2 - x1 - 1) // 2))
            pad_y = min(raw_pad_y, max(0, (y2 - y1 - 1) // 2))
            box_x1 = x1 + pad_x
            box_y1 = y1 + pad_y
            box_x2 = x2 - pad_x
            box_y2 = y2 - pad_y

            if box_x2 - box_x1 < 2 or box_y2 - box_y1 < 2:
                discarded_region_count += 1
                continue

            # 2) Pintar un rectángulo blanco (tapamos texto original)
            draw.rectangle(
                [box_x1, box_y1, box_x2, box_y2],
                fill="white",
            )

            # 3) Calcular tamaño de fuente y texto envuelto que quepa en la caja
            box_width = max(1, box_x2 - box_x1)
            box_height = max(1, box_y2 - box_y1)

            layout_result = self.layout_service.fit_text_to_box(
                text=region.translated_text,
                box_w=box_width,
                box_h=box_height,
                font_path=self.font_path,
                max_font=self.max_font_size,
                min_font=self.min_font_size,
                line_height=self.line_height,
            )

            padding = min(pad_x, pad_y)
            overflow = self.layout_service.check_overflow(
                layout_result, box_width, box_height, padding=padding
            )

            if overflow or not layout_result.fits:
                overflow_count += 1
                retry_count += 1
                cleaned_text = self._normalize_text(region.translated_text)
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
            invalid_bbox_count=invalid_bbox_count,
            discarded_region_count=discarded_region_count,
            layouts=layouts,
        )

    # ---------- Helpers internos ----------

    def _sanitize_bbox(self, bbox: BBox, width: int, height: int) -> Tuple[int, int, int, int] | None:
        """Normaliza el bbox y asegura coordenadas válidas en píxeles."""

        clamped = bbox.clamp()
        x1 = int(clamped.x_min * width)
        y1 = int(clamped.y_min * height)
        x2 = int(clamped.x_max * width)
        y2 = int(clamped.y_max * height)

        x1 = max(0, min(x1, width - 1))
        y1 = max(0, min(y1, height - 1))
        x2 = max(x1 + 1, min(x2, width))
        y2 = max(y1 + 1, min(y2, height))

        if x2 - x1 < 2 or y2 - y1 < 2:
            return None

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

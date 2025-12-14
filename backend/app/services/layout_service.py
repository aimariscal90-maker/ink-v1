from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import List, Tuple

from PIL import Image, ImageDraw, ImageFont


@dataclass
class LayoutResult:
    font_size: int
    lines: List[str]
    line_height: float
    fits: bool
    final_text_block_w: int
    final_text_block_h: int


class LayoutService:
    def __init__(self) -> None:
        # Canvas mínimo para medir texto sin costo de crear imágenes en cada llamada
        self._measure_img = Image.new("RGB", (1, 1))
        self._draw = ImageDraw.Draw(self._measure_img)

    def load_font(self, font: str | Path, size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
        try:
            return ImageFont.truetype(str(font), size=size)
        except Exception:
            return ImageFont.load_default()

    def wrap_text(
        self,
        text: str,
        max_width_px: int,
        font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
        font_size: int,
    ) -> List[str]:
        """
        Divide el texto en líneas que no excedan max_width_px.
        Mantiene saltos de línea explícitos.
        """

        if not text:
            return []

        lines: List[str] = []
        paragraphs = text.splitlines() or [text]

        for paragraph in paragraphs:
            words = paragraph.split()
            if not words:
                lines.append("")
                continue

            current_line = words[0]
            for word in words[1:]:
                test_line = f"{current_line} {word}" if current_line else word
                line_w = self._line_width(test_line, font)
                if line_w <= max_width_px:
                    current_line = test_line
                else:
                    lines.append(current_line)
                    current_line = word
            lines.append(current_line)

        return lines

    def measure_text(
        self,
        lines: List[str],
        font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
        font_size: int,
        line_height: float,
    ) -> Tuple[int, int]:
        if not lines:
            return 0, 0

        max_w = 0
        for line in lines:
            max_w = max(max_w, self._line_width(line, font))

        line_height_px = int(font_size * line_height)
        total_h = line_height_px * len(lines)
        return max_w, total_h

    def fit_text_to_box(
        self,
        text: str,
        box_w: int,
        box_h: int,
        font_path: Path,
        max_font: int,
        min_font: int,
        line_height: float = 1.2,
    ) -> LayoutResult:
        """
        Ajusta el texto al bbox usando búsqueda binaria en el tamaño de fuente.
        Devuelve LayoutResult con la mejor combinación encontrada.
        """
        best_result: LayoutResult | None = None
        low, high = min_font, max_font

        while low <= high:
            mid = (low + high) // 2
            font = self.load_font(font_path, mid)
            lines = self.wrap_text(text, box_w, font, mid)
            block_w, block_h = self.measure_text(lines, font, mid, line_height)
            fits = block_w <= box_w and block_h <= box_h

            current = LayoutResult(
                font_size=mid,
                lines=lines,
                line_height=mid * line_height,
                fits=fits,
                final_text_block_w=block_w,
                final_text_block_h=block_h,
            )

            if fits:
                best_result = current
                low = mid + 1
            else:
                high = mid - 1

        if best_result:
            return best_result

        # Fallback con fuente mínima, aunque no quepa
        font = self.load_font(font_path, min_font)
        lines = self.wrap_text(text, box_w, font, min_font)
        block_w, block_h = self.measure_text(lines, font, min_font, line_height)
        fits = block_w <= box_w and block_h <= box_h
        return LayoutResult(
            font_size=min_font,
            lines=lines,
            line_height=min_font * line_height,
            fits=fits,
            final_text_block_w=block_w,
            final_text_block_h=block_h,
        )

    def check_overflow(self, layout_result: LayoutResult, box_w: int, box_h: int, padding: int) -> bool:
        max_w = max(0, box_w - padding * 2)
        max_h = max(0, box_h - padding * 2)
        return (
            layout_result.final_text_block_w > max_w
            or layout_result.final_text_block_h > max_h
        )

    def _line_width(self, text: str, font: ImageFont.ImageFont) -> int:
        bbox = self._draw.textbbox((0, 0), text, font=font)
        return bbox[2] - bbox[0]

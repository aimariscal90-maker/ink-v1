from __future__ import annotations

from pathlib import Path
from typing import List, Tuple

from PIL import Image, ImageDraw, ImageFont

from app.models.text import BBox, TranslatedRegion


class RenderService:
    """
    Se encarga de pintar el texto traducido sobre la imagen original.
    """

    def render_page(
        self,
        input_image: Path,
        regions: List[TranslatedRegion],
        output_image: Path | None = None,
    ) -> Path:
        """
        Dibuja todas las regiones traducidas sobre la imagen y devuelve
        la ruta del archivo de salida.
        """

        if not input_image.exists():
            raise FileNotFoundError(f"Input image not found: {input_image}")

        img = Image.open(input_image).convert("RGBA")
        draw = ImageDraw.Draw(img)

        width, height = img.width, img.height

        for region in regions:
            # 1) Convertimos el BBox normalizado [0,1] a coordenadas de píxel
            x1, y1, x2, y2 = self._bbox_to_pixels(region.bbox, width, height)

            # Añadir algo de padding interno
            pad_x = int((x2 - x1) * 0.05)
            pad_y = int((y2 - y1) * 0.05)
            box_x1 = x1 + pad_x
            box_y1 = y1 + pad_y
            box_x2 = x2 - pad_x
            box_y2 = y2 - pad_y

            # 2) Pintar un rectángulo blanco (tapamos texto original)
            draw.rectangle(
                [box_x1, box_y1, box_x2, box_y2],
                fill="white",
            )

            # 3) Calcular tamaño de fuente y texto envuelto que quepa en la caja
            box_width = box_x2 - box_x1
            box_height = box_y2 - box_y1

            font, wrapped_text = self._fit_text_in_box(
                text=region.translated_text,
                draw=draw,
                box_width=box_width,
                box_height=box_height,
            )

            # 4) Calcular posición para centrar el texto
            text_bbox = draw.multiline_textbbox((0, 0), wrapped_text, font=font, align="center")
            text_w = text_bbox[2] - text_bbox[0]
            text_h = text_bbox[3] - text_bbox[1]

            text_x = box_x1 + (box_width - text_w) // 2
            text_y = box_y1 + (box_height - text_h) // 2

            # 5) Dibujar texto en negro
            draw.multiline_text(
                (text_x, text_y),
                wrapped_text,
                font=font,
                fill="black",
                align="center",
            )

        # Determinar ruta de salida
        if output_image is None:
            output_image = input_image.with_name(input_image.stem + "_translated.png")

        img.save(output_image)
        return output_image

    # ---------- Helpers internos ----------

    def _bbox_to_pixels(self, bbox: BBox, width: int, height: int) -> Tuple[int, int, int, int]:
        """
        Convierte BBox normalizado [0,1] a coordenadas de píxel (enteros).
        """
        x1 = int(bbox.x_min * width)
        y1 = int(bbox.y_min * height)
        x2 = int(bbox.x_max * width)
        y2 = int(bbox.y_max * height)
        return x1, y1, x2, y2

    def _get_base_font(self, size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
        """
        Devuelve una fuente. Intentamos usar una TrueType decente; si no,
        usamos la fuente por defecto de Pillow.
        """
        try:
            # DejaVuSans suele venir instalada en muchas imágenes base
            return ImageFont.truetype("DejaVuSans.ttf", size=size)
        except Exception:
            return ImageFont.load_default()

    def _fit_text_in_box(
        self,
        text: str,
        draw: ImageDraw.ImageDraw,
        box_width: int,
        box_height: int,
        max_font_size: int = 40,
        min_font_size: int = 10,
    ) -> Tuple[ImageFont.ImageFont, str]:
        """
        Busca el tamaño de fuente más grande que permite que el texto envuelto
        quepa en el rectángulo (box_width x box_height).
        Devuelve (font, wrapped_text).
        """
        # Intentamos desde grande hacia pequeño
        for font_size in range(max_font_size, min_font_size - 1, -2):
            font = self._get_base_font(font_size)
            wrapped = self._wrap_text(text, draw, font, box_width)
            bbox = draw.multiline_textbbox((0, 0), wrapped, font=font)
            text_w = bbox[2] - bbox[0]
            text_h = bbox[3] - bbox[1]

            if text_w <= box_width and text_h <= box_height:
                return font, wrapped

        # Si no cabe ni con la fuente mínima, devolvemos texto truncado
        font = self._get_base_font(min_font_size)
        wrapped = self._wrap_text(text, draw, font, box_width)
        return font, wrapped

    def _wrap_text(
        self,
        text: str,
        draw: ImageDraw.ImageDraw,
        font: ImageFont.ImageFont,
        max_width: int,
    ) -> str:
        """
        Corta el texto en líneas para que cada línea no exceda max_width.
        """
        words = text.split()
        if not words:
            return ""

        lines: list[str] = []
        current_line = words[0]

        for word in words[1:]:
            test_line = current_line + " " + word
            bbox = draw.textbbox((0, 0), test_line, font=font)
            line_width = bbox[2] - bbox[0]

            if line_width <= max_width:
                current_line = test_line
            else:
                lines.append(current_line)
                current_line = word

        lines.append(current_line)
        return "\n".join(lines)

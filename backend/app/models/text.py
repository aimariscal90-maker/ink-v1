from __future__ import annotations

from pydantic import BaseModel, Field


class BBox(BaseModel):
    """
    Bounding box normalizado: coordenadas relativas [0, 1] sobre ancho/alto de la imagen.
    """

    x_min: float = Field(ge=0.0, le=1.0)
    y_min: float = Field(ge=0.0, le=1.0)
    x_max: float = Field(ge=0.0, le=1.0)
    y_max: float = Field(ge=0.0, le=1.0)

    def clamp(self) -> "BBox":
        """
        Asegura que las coordenadas están en [0, 1] y x_min <= x_max, y_min <= y_max.
        """
        x_min = max(0.0, min(self.x_min, 1.0))
        y_min = max(0.0, min(self.y_min, 1.0))
        x_max = max(0.0, min(self.x_max, 1.0))
        y_max = max(0.0, min(self.y_max, 1.0))
        if x_min > x_max:
            x_min, x_max = x_max, x_min
        if y_min > y_max:
            y_min, y_max = y_max, y_min
        return BBox(x_min=x_min, y_min=y_min, x_max=x_max, y_max=y_max)


class TextRegion(BaseModel):
    """
    Trozo de texto detectado por el OCR en una página.
    """

    id: str
    text: str
    bbox: BBox
    confidence: float | None = None  # 0–1 aproximado


class TranslatedRegion(BaseModel):
    """
    TextRegion una vez traducido.
    """

    id: str
    original_text: str
    translated_text: str
    bbox: BBox
    confidence: float | None = None  # podemos arrastrar el del OCR

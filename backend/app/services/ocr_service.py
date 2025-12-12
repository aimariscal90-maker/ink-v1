from __future__ import annotations

from pathlib import Path
from typing import List

from google.cloud import vision

from app.models.text import BBox, TextRegion


class OcrService:
    """
    Extrae regiones de texto desde una imagen usando Google Cloud Vision OCR.
    """

    def __init__(self) -> None:
        self.client = None

    def _get_client(self):
        if self.client is None:
            self.client = vision.ImageAnnotatorClient()
        return self.client

    def extract_text_regions(self, image_path: Path) -> List[TextRegion]:
        """
        Devuelve todas las regiones de texto detectadas con bounding boxes normalizados.
        """

        with open(image_path, "rb") as f:
            content = f.read()

        image = vision.Image(content=content)
        client = self._get_client()
        response = client.text_detection(image=image)

        if response.error.message:
            raise RuntimeError(f"Google Vision OCR error: {response.error.message}")

        annotations = response.text_annotations
        if not annotations:
            return []

        # Primer elemento es TODO el texto; los siguientes son palabras/fragmentos
        regions: List[TextRegion] = []

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

            # Dimensiones reales de la imagen
            import PIL.Image
            with PIL.Image.open(image_path) as img:
                W, H = img.width, img.height

            bbox = BBox(
                x_min=x_min / W,
                y_min=y_min / H,
                x_max=x_max / W,
                y_max=y_max / H,
            ).clamp()

            regions.append(
                TextRegion(
                    id=str(idx),
                    text=ann.description,
                    bbox=bbox,
                    confidence=None,  # Vision no da un score directo para cada palabra
                )
            )

        return regions

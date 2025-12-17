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
        if not annotations:
            return []

        # Primer elemento es TODO el texto; los siguientes son palabras/fragmentos
        regions: List[TextRegion] = []

        # Dimensiones reales de la imagen
        import PIL.Image

        with PIL.Image.open(image_path) as img:
            width, height = img.width, img.height

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

            bbox = BBox(
                x_min=x_min / width,
                y_min=y_min / height,
                x_max=x_max / width,
                y_max=y_max / height,
            ).clamp()

            regions.append(
                TextRegion(
                    id=str(idx),
                    text=ann.description,
                    bbox=bbox,
                    confidence=None,  # Vision no da un score directo para cada palabra
                )
            )

        self.cache.set_json(cache_key, {"regions": [r.model_dump() for r in regions]})

        return regions

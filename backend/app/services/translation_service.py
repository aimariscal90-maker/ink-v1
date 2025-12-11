from __future__ import annotations

from typing import List

from app.models.text import TextRegion, TranslatedRegion


class TranslationService:
    """
    Encapsula llamadas a LLM / API de traducción (OpenAI).
    """

    def translate_regions(
        self,
        regions: List[TextRegion],
        source_lang: str,
        target_lang: str,
    ) -> List[TranslatedRegion]:
        """
        Traduce una lista de regiones manteniendo IDs y bounding boxes.
        """
        raise NotImplementedError("Translation service not implemented yet")

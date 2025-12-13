from __future__ import annotations

import json
from typing import List

from openai import OpenAI

from app.core.config import get_settings
from app.models.text import TextRegion, TranslatedRegion
from app.services.cache_service import CacheService


class TranslationService:
    """
    Encapsula llamadas a LLM / API de traducción (OpenAI) para traducir
    regiones de texto de cómic.
    """

    def __init__(
        self, model: str = "gpt-4.1-mini", cache_service: CacheService | None = None
    ) -> None:
        """
        model: nombre del modelo de OpenAI que se usará para la traducción.
        """
        get_settings()

        # El cliente usa OPENAI_API_KEY del entorno por defecto.
        # Si quieres, puedes también tomarla de settings.openai_api_key.
        self.client = None
        self.model = model
        self.cache = cache_service or CacheService()

    def _get_client(self):
        if self.client is None:
            self.client = OpenAI()
        return self.client

    def translate_text_cached(self, text: str, target_lang: str) -> str:
        cache_key = f"tr:{target_lang}:{CacheService.key_hash(text)}"
        cached = self.cache.get_text(cache_key)
        if cached is not None:
            return cached

        translated = self._translate_single(text=text, target_lang=target_lang)
        self.cache.set_text(cache_key, translated)
        return translated

    def _translate_single(self, text: str, target_lang: str) -> str:
        client = self._get_client()
        response = client.chat.completions.create(
            model=self.model,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Eres un traductor profesional. Traduce al idioma indicado. "
                        "Devuelve solo el texto traducido, sin formato extra."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        "Traduce al idioma destino y responde solo con el texto traducido.\n"
                        f"Idioma destino: {target_lang}\n"
                        f"Texto: {text}"
                    ),
                },
            ],
            temperature=0.2,
        )

        raw = response.choices[0].message.content
        if raw is None:
            raise RuntimeError("OpenAI no devolvió contenido en la respuesta")

        return raw.strip()

    def _translate_texts_batch(
        self, texts: List[str], source_lang: str, target_lang: str
    ) -> List[str]:
        client = self._get_client()
        response = client.chat.completions.create(
            model=self.model,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Eres un traductor profesional de cómics. "
                        "Traduce cada texto manteniendo tono y naturalidad."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        "Traduce cada elemento de la lista a "
                        f"{target_lang} desde {source_lang}.\n"
                        "Devuelve SOLO un JSON válido con esta forma exacta:\n"
                        "{ \"translations\": [\"t1\", \"t2\", ...] }\n"
                        "La lista de salida debe tener la MISMA longitud y orden que la entrada.\n"
                        f"Entrada: {json.dumps(texts, ensure_ascii=False)}"
                    ),
                },
            ],
            temperature=0.2,
        )

        raw = response.choices[0].message.content
        if raw is None:
            raise RuntimeError("OpenAI no devolvió contenido en la respuesta")

        try:
            data = json.loads(raw)
        except json.JSONDecodeError as e:
            raise RuntimeError(
                f"Respuesta de OpenAI no es JSON válido: {e}\nContenido: {raw!r}"
            )

        translations = data.get("translations")
        if not isinstance(translations, list):
            raise RuntimeError(f"Respuesta de OpenAI mal formada: {data!r}")

        return [str(t) for t in translations]

    def translate_regions_batch(
        self,
        regions: List[TextRegion],
        source_lang: str = "en",
        target_lang: str = "es",
    ) -> List[TranslatedRegion]:
        if not regions:
            return []

        texts = [r.text for r in regions]
        translations: List[str | None] = [None] * len(texts)
        missing: list[tuple[int, str]] = []

        for idx, text in enumerate(texts):
            cache_key = f"tr:{target_lang}:{CacheService.key_hash(text)}"
            cached = self.cache.get_text(cache_key)
            if cached is not None:
                translations[idx] = cached
            else:
                missing.append((idx, text))

        if missing:
            try:
                batch_translations = self._translate_texts_batch(
                    [t for _, t in missing], source_lang, target_lang
                )
                if len(batch_translations) != len(missing):
                    raise RuntimeError("Longitud de traducciones no coincide con la entrada")

                for (idx, text), translated in zip(missing, batch_translations):
                    translations[idx] = translated
                    cache_key = f"tr:{target_lang}:{CacheService.key_hash(text)}"
                    self.cache.set_text(cache_key, translated)
            except Exception:
                for idx, text in missing:
                    translations[idx] = self.translate_text_cached(text, target_lang)

        translated_regions: List[TranslatedRegion] = []
        for region, translated_text in zip(regions, translations):
            translated_regions.append(
                TranslatedRegion(
                    id=region.id,
                    original_text=region.text,
                    translated_text=translated_text or region.text,
                    bbox=region.bbox,
                    confidence=region.confidence,
                )
            )

        return translated_regions

    def translate_regions(
        self,
        regions: List[TextRegion],
        source_lang: str,
        target_lang: str,
    ) -> List[TranslatedRegion]:
        return self.translate_regions_batch(
            regions=regions, source_lang=source_lang, target_lang=target_lang
        )

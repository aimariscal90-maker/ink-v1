from __future__ import annotations

import json
from typing import List

from openai import OpenAI

from app.core.config import get_settings
from app.models.text import TextRegion, TranslatedRegion


class TranslationService:
    """
    Encapsula llamadas a LLM / API de traducción (OpenAI) para traducir
    regiones de texto de cómic.
    """

    def __init__(self, model: str = "gpt-4.1-mini") -> None:
        """
        model: nombre del modelo de OpenAI que se usará para la traducción.
        """
        settings = get_settings()

        # El cliente usa OPENAI_API_KEY del entorno por defecto.
        # Si quieres, puedes también tomarla de settings.openai_api_key.
        self.client = OpenAI()
        self.model = model

    def translate_regions(
        self,
        regions: List[TextRegion],
        source_lang: str,
        target_lang: str,
    ) -> List[TranslatedRegion]:
        """
        Traduce una lista de regiones manteniendo IDs y bounding boxes.
        """
        if not regions:
            return []

        # Preparamos los datos de entrada para el modelo
        payload = [
            {
                "id": r.id,
                "text": r.text,
            }
            for r in regions
        ]

        # Prompt: le pedimos JSON abierto muy concreto
        system_prompt = (
            "Eres un traductor profesional de cómics. "
            "Traduces del idioma source_lang al idioma target_lang. "
            "Tu prioridad es mantener el tono, naturalidad y estilo de diálogo.\n"
            "- Respeta nombres propios.\n"
            "- Mantén las onomatopeyas si tienen sentido en el idioma destino, "
            "y si no, adáptalas de forma natural.\n"
            "- NO añadas texto nuevo, no resumas, no expliques nada.\n"
            "- Devuelve siempre un JSON válido y nada más."
        )

        user_content = {
            "source_lang": source_lang,
            "target_lang": target_lang,
            "items": payload,
            # Podríamos añadir más contexto a futuro (escena, personajes, etc.)
        }

        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system_prompt},
                {
                    "role": "user",
                    "content": (
                        "Traduce los diálogos o textos de cómic en 'items'.\n"
                        "Devuelve SOLO un JSON con esta estructura exacta:\n"
                        "{ \"items\": [ { \"id\": \"...\", \"translated_text\": \"...\" }, ... ] }\n\n"
                        "Aquí tienes los datos:\n"
                        f"{json.dumps(user_content, ensure_ascii=False)}"
                    ),
                },
            ],
            temperature=0.2,
        )

        raw = response.choices[0].message.content
        if raw is None:
            raise RuntimeError("OpenAI no devolvió contenido en la respuesta")

        # Intentamos parsear el JSON
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as e:
            raise RuntimeError(f"Respuesta de OpenAI no es JSON válido: {e}\nContenido: {raw!r}")

        items = data.get("items")
        if not isinstance(items, list):
            raise RuntimeError(f"Respuesta de OpenAI mal formada, falta 'items': {data!r}")

        # Crear un índice de id -> translated_text
        translated_map: dict[str, str] = {}
        for item in items:
            if not isinstance(item, dict):
                continue
            item_id = str(item.get("id"))
            translated_text = item.get("translated_text")
            if translated_text is None:
                continue
            translated_map[item_id] = str(translated_text)

        # Ahora construimos la lista final de TranslatedRegion en el mismo orden
        translated_regions: List[TranslatedRegion] = []
        for r in regions:
            translated_text = translated_map.get(r.id)
            if translated_text is None:
                # Si falta alguna, como fallback devolvemos el texto original
                translated_text = r.text

            translated_regions.append(
                TranslatedRegion(
                    id=r.id,
                    original_text=r.text,
                    translated_text=translated_text,
                    bbox=r.bbox,
                    confidence=r.confidence,
                )
            )

        return translated_regions

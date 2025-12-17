from __future__ import annotations

"""Capa de caché muy simple basada en archivos.

Se usa para evitar recalcular OCR o traducciones. Las rutas son seguras para
el sistema de archivos y cada método está documentado con un propósito claro.
"""

import json
from hashlib import sha256
from pathlib import Path
from typing import Any

from app.core.config import get_settings


class CacheService:
    """Simple filesystem-based cache for JSON and text blobs."""

    def __init__(self, base_dir: Path | None = None) -> None:
        settings = get_settings()
        self.base_dir = base_dir or settings.data_dir / "cache"
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def _path_for_key(self, key: str, suffix: str) -> Path:
        """Construye una ruta segura para un identificador arbitrario."""
        # Avoid problematic characters in filenames
        safe_key = key.replace(":", "_")
        filename = f"{safe_key}.{suffix}"
        return self.base_dir / filename

    def get_json(self, key: str) -> dict | None:
        """Lee un diccionario JSON cacheado, o None si no existe/está corrupto."""
        path = self._path_for_key(key, "json")
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return None

    def set_json(self, key: str, value: dict) -> None:
        """Guarda un diccionario en disco como JSON legible."""
        path = self._path_for_key(key, "json")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value), encoding="utf-8")

    def get_text(self, key: str) -> str | None:
        """Recupera texto plano previamente cacheado."""
        path = self._path_for_key(key, "txt")
        if not path.exists():
            return None
        try:
            return path.read_text(encoding="utf-8")
        except OSError:
            return None

    def set_text(self, key: str, value: str) -> None:
        """Guarda texto plano en disco."""
        path = self._path_for_key(key, "txt")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(value, encoding="utf-8")

    @staticmethod
    def key_hash(data: bytes | str) -> str:
        """Crea un hash estable para usar como clave de caché."""
        if isinstance(data, str):
            data = data.encode("utf-8")
        return sha256(data).hexdigest()

from __future__ import annotations

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
        # Avoid problematic characters in filenames
        safe_key = key.replace(":", "_")
        filename = f"{safe_key}.{suffix}"
        return self.base_dir / filename

    def get_json(self, key: str) -> dict | None:
        path = self._path_for_key(key, "json")
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return None

    def set_json(self, key: str, value: dict) -> None:
        path = self._path_for_key(key, "json")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value), encoding="utf-8")

    def get_text(self, key: str) -> str | None:
        path = self._path_for_key(key, "txt")
        if not path.exists():
            return None
        try:
            return path.read_text(encoding="utf-8")
        except OSError:
            return None

    def set_text(self, key: str, value: str) -> None:
        path = self._path_for_key(key, "txt")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(value, encoding="utf-8")

    @staticmethod
    def key_hash(data: bytes | str) -> str:
        if isinstance(data, str):
            data = data.encode("utf-8")
        return sha256(data).hexdigest()

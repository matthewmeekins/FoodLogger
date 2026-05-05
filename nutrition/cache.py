import time
from typing import Any, Optional


class TTLCache:
    """Simple in-memory TTL cache for normalized nutrition queries."""

    def __init__(self, ttl_seconds: int = 3600, max_items: int = 500) -> None:
        self.ttl_seconds = ttl_seconds
        self.max_items = max_items
        self._items: dict[str, tuple[float, Any]] = {}

    def get(self, key: str) -> Optional[Any]:
        item = self._items.get(key)
        if not item:
            return None

        expires_at, value = item
        if expires_at < time.time():
            self._items.pop(key, None)
            return None

        return value

    def set(self, key: str, value: Any) -> None:
        if len(self._items) >= self.max_items:
            # Remove an arbitrary item to keep memory bounded.
            self._items.pop(next(iter(self._items)), None)

        self._items[key] = (time.time() + self.ttl_seconds, value)

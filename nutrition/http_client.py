import json
import time
import urllib.parse
import urllib.request
from typing import Any, Optional


class HttpClient:
    """Minimal JSON HTTP client with timeout and retry support."""

    def __init__(self, timeout_seconds: float = 6.0, retries: int = 2) -> None:
        self.timeout_seconds = timeout_seconds
        self.retries = retries

    def get_json(self, url: str, params: Optional[dict[str, Any]] = None) -> Any:
        full_url = url
        if params:
            query_string = urllib.parse.urlencode(params)
            full_url = f"{url}?{query_string}"

        last_error: Optional[Exception] = None
        for attempt in range(self.retries + 1):
            try:
                req = urllib.request.Request(full_url, method="GET")
                with urllib.request.urlopen(req, timeout=self.timeout_seconds) as resp:
                    return json.loads(resp.read().decode("utf-8"))
            except Exception as exc:
                last_error = exc
                if attempt < self.retries:
                    time.sleep(0.25 * (attempt + 1))

        if last_error:
            raise last_error
        raise RuntimeError("HTTP request failed")

    def post_json(self, url: str, payload: dict[str, Any], params: Optional[dict[str, Any]] = None) -> Any:
        full_url = url
        if params:
            query_string = urllib.parse.urlencode(params)
            full_url = f"{url}?{query_string}"

        data = json.dumps(payload).encode("utf-8")
        headers = {"Content-Type": "application/json"}

        last_error: Optional[Exception] = None
        for attempt in range(self.retries + 1):
            try:
                req = urllib.request.Request(full_url, data=data, headers=headers, method="POST")
                with urllib.request.urlopen(req, timeout=self.timeout_seconds) as resp:
                    return json.loads(resp.read().decode("utf-8"))
            except Exception as exc:
                last_error = exc
                if attempt < self.retries:
                    time.sleep(0.25 * (attempt + 1))

        if last_error:
            raise last_error
        raise RuntimeError("HTTP request failed")

"""In-memory sliding window rate limiter for Vercel serverless."""
from __future__ import annotations

import time
import threading
from typing import Callable

from fastapi import Request, Response

_LOCK = threading.Lock()
# {ip: [timestamps...]}
_WINDOWS: dict[str, list[float]] = {}

MAX_REQUESTS_PER_WINDOW = 30
WINDOW_SECONDS = 60
RATE_LIMITED_PREFIXES = (
    "/api/search",
    "/api/tenders",
    "/api/funding",
    "/api/suggest",
    "/api/subscriptions",
)

MAX_GENERAL = 120
GENERAL_WINDOW = 60


def _cleanup_expired(key: str, now: float, window: float) -> None:
    """Remove expired timestamps from a window."""
    window_list = _WINDOWS.get(key)
    if not window_list:
        return
    cutoff = now - window
    _WINDOWS[key] = [t for t in window_list if t > cutoff]


def _check_rate_limit(key: str, max_req: int, window: float) -> tuple[bool, int]:
    """Return (allowed, retry_after_seconds)."""
    now = time.time()
    with _LOCK:
        if key not in _WINDOWS:
            _WINDOWS[key] = []
        _cleanup_expired(key, now, window)
        requests = _WINDOWS[key]
        if len(requests) >= max_req:
            oldest = min(requests)
            retry_after = max(1, int(window - (now - oldest)))
            return False, retry_after
        requests.append(now)
        return True, 0


async def rate_limit_middleware(request: Request, call_next: Callable) -> Response:
    """Rate-limit search/suggest endpoints; gentle limit on all."""
    client_ip = request.headers.get("x-forwarded-for", request.client.host if request.client else "127.0.0.1")
    client_ip = client_ip.split(",")[0].strip()

    path = request.url.path

    if any(path.startswith(prefix) for prefix in RATE_LIMITED_PREFIXES):
        allowed, retry_after = _check_rate_limit(client_ip, MAX_REQUESTS_PER_WINDOW, WINDOW_SECONDS)
    else:
        allowed, retry_after = _check_rate_limit(client_ip, MAX_GENERAL, GENERAL_WINDOW)

    if not allowed:
        return Response(
            content='{"error":"rate_limited","detail":"Слишком много запросов. Повторите позже."}',
            status_code=429,
            media_type="application/json",
            headers={"Retry-After": str(retry_after)},
        )

    return await call_next(request)

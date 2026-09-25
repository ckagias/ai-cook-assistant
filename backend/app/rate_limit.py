import time
from collections import defaultdict, deque

_WINDOWS: dict[str, deque] = defaultdict(deque)


def check_rate_limit(key: str, *, max_requests: int, window_sec: float) -> bool:
    """Returns True if the call is allowed (and records it), False if the
    caller is over the limit for this key within the window. Prunes
    timestamps older than window_sec on every call - no separate cleanup
    task needed for a single-process deployment."""
    now = time.monotonic()
    window = _WINDOWS[key]

    while window and now - window[0] > window_sec:
        window.popleft()

    if len(window) >= max_requests:
        return False

    window.append(now)
    return True

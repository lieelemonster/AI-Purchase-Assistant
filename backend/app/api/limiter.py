import time
from collections import deque
from typing import Deque, Literal

Decision = Literal["ok", "rate_limited", "busy"]


class RequestLimiter:
    """限制每分钟进入的推荐次数，以及同时进行的推荐数量。"""

    def __init__(self, per_minute: int, max_concurrent: int):
        self.per_minute = per_minute
        self.max_concurrent = max_concurrent
        self._started: Deque[float] = deque()
        self._inflight = 0

    def enter(self, now: float = None) -> Decision:
        current = time.monotonic() if now is None else now
        while self._started and current - self._started[0] >= 60:
            self._started.popleft()
        if len(self._started) >= self.per_minute:
            return "rate_limited"
        if self._inflight >= self.max_concurrent:
            return "busy"
        self._started.append(current)
        self._inflight += 1
        return "ok"

    def leave(self) -> None:
        self._inflight = max(0, self._inflight - 1)

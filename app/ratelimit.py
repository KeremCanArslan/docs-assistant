"""In-memory request limits: per client per minute and per day, and one shared daily budget.

Good for a single instance (this demo). With several instances the counters
would move to Redis or the database.
"""

from __future__ import annotations

import threading
import time
from collections import defaultdict, deque
from datetime import datetime
from zoneinfo import ZoneInfo


class RateLimiter:
    def __init__(
        self,
        per_minute: int,
        per_day: int,
        per_client_day: int = 0,
        timezone: str = "Europe/Berlin",
        clock=time.monotonic,
    ) -> None:
        self.per_minute = per_minute
        self.per_day = per_day
        self.per_client_day = per_client_day  # 0 = no per-client daily limit
        self.zone = ZoneInfo(timezone)
        self.clock = clock
        self._recent: dict[str, deque[float]] = defaultdict(deque)
        self._day = ""
        self._day_count = 0
        self._client_day_counts: dict[str, int] = defaultdict(int)
        self._lock = threading.Lock()

    def _today(self) -> str:
        return datetime.now(self.zone).date().isoformat()

    def check(self, client: str) -> str | None:
        """Records the request and returns None, or "minute", "client-day" or "day" when a limit is reached."""
        now = self.clock()
        with self._lock:
            today = self._today()
            if today != self._day:
                self._day, self._day_count = today, 0
                self._client_day_counts.clear()
            if self._day_count >= self.per_day:
                return "day"
            if self.per_client_day and self._client_day_counts[client] >= self.per_client_day:
                return "client-day"
            window = self._recent[client]
            while window and now - window[0] >= 60:
                window.popleft()
            if len(window) >= self.per_minute:
                return "minute"
            window.append(now)
            self._day_count += 1
            self._client_day_counts[client] += 1
            if len(self._recent) > 10_000:  # forget idle clients so memory stays bounded
                for key in [k for k, v in self._recent.items() if not v or now - v[-1] >= 60]:
                    del self._recent[key]
            return None

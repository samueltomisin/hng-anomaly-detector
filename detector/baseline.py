import time
import math
from collections import deque

class BaselineTracker:
    """
    Maintains a 30-minute rolling window of per-second request counts.
    Recalculates mean and stddev every 60 seconds.
    Uses per-hour slots — prefers current hour's data when sufficient.
    """
    def __init__(self, window_minutes=30, recalc_interval=60):
        self.window_seconds = window_minutes * 60
        self.recalc_interval = recalc_interval
        # Each entry: (timestamp, count)
        self.per_second_counts = deque()
        self.hourly_slots = {}  # hour_key -> list of per-second counts
        self.mean = 1.0   # floor value — never 0
        self.stddev = 1.0
        self.last_recalc = time.time()

    def record(self, timestamp, count):
        """Add a per-second count snapshot."""
        now = time.time()
        self.per_second_counts.append((now, count))
        # Evict entries older than 30 minutes
        while self.per_second_counts and \
              now - self.per_second_counts[0][0] > self.window_seconds:
            self.per_second_counts.popleft()

        # Also store in hourly slot
        hour_key = int(now // 3600)
        self.hourly_slots.setdefault(hour_key, []).append(count)

        # Recalculate periodically
        if now - self.last_recalc >= self.recalc_interval:
            self.recalculate()
            self.last_recalc = now

    def recalculate(self):
        """Recompute mean and stddev from rolling window."""
        counts = [c for _, c in self.per_second_counts]
        if len(counts) < 10:
            return  # Not enough data yet

        n = len(counts)
        mean = sum(counts) / n
        variance = sum((x - mean) ** 2 for x in counts) / n
        stddev = math.sqrt(variance)

        self.mean = max(mean, 1.0)    # Floor at 1 to avoid division by zero
        self.stddev = max(stddev, 0.5)

    def get_zscore(self, current_rate):
        return (current_rate - self.mean) / self.stddev

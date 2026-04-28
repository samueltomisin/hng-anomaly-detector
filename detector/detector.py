import time
from collections import deque, defaultdict
import math

class AnomalyDetector:
    """
    Two sliding windows (deques): one per-IP, one global.
    Evicts entries older than 60 seconds.
    Compares current rate to baseline using z-score and multiplier checks.
    """
    def __init__(self, config, baseline):
        self.window_seconds = config['sliding_window_seconds']
        self.zscore_threshold = config['anomaly_zscore_threshold']
        self.rate_multiplier = config['anomaly_rate_multiplier']
        self.error_multiplier = config['error_rate_multiplier']
        self.baseline = baseline

        # Global window: deque of (timestamp,) — one entry per request
        self.global_window = deque()
        # Per-IP window: {ip -> deque of (timestamp,)}
        self.ip_windows = defaultdict(deque)
        # Per-IP error window: {ip -> deque of (timestamp,)}
        self.ip_error_windows = defaultdict(deque)

    def record_request(self, ip, timestamp, status):
        now = time.time()
        # Add to global window
        self.global_window.append(now)
        self._evict(self.global_window)

        # Add to IP window
        self.ip_windows[ip].append(now)
        self._evict(self.ip_windows[ip])

        # Track errors
        if status >= 400:
            self.ip_error_windows[ip].append(now)
            self._evict(self.ip_error_windows[ip])

    def _evict(self, window):
        """Remove entries older than the sliding window."""
        cutoff = time.time() - self.window_seconds
        while window and window[0] < cutoff:
            window.popleft()

    def get_ip_rate(self, ip):
        self._evict(self.ip_windows[ip])
        return len(self.ip_windows[ip]) / self.window_seconds

    def get_global_rate(self):
        self._evict(self.global_window)
        return len(self.global_window) / self.window_seconds

    def get_ip_error_rate(self, ip):
        self._evict(self.ip_error_windows[ip])
        return len(self.ip_error_windows[ip]) / self.window_seconds

    def check_ip(self, ip):
        """Returns (is_anomalous, reason) for a given IP."""
        rate = self.get_ip_rate(ip)
        zscore = self.baseline.get_zscore(rate)
        error_rate = self.get_ip_error_rate(ip)
        error_baseline = max(self.baseline.mean * 0.1, 0.1)

        # Tighten thresholds if IP has high error rate
        zscore_threshold = self.zscore_threshold
        if error_rate > error_baseline * self.error_multiplier:
            zscore_threshold = self.zscore_threshold * 0.6  # Tighter threshold

        if zscore > zscore_threshold:
            return True, f"z-score={zscore:.2f} > {zscore_threshold}"
        if rate > self.baseline.mean * self.rate_multiplier:
            return True, f"rate={rate:.2f} > {self.rate_multiplier}x baseline"
        return False, None

    def check_global(self):
        rate = self.get_global_rate()
        zscore = self.baseline.get_zscore(rate)
        if zscore > self.zscore_threshold:
            return True, f"global z-score={zscore:.2f}"
        if rate > self.baseline.mean * self.rate_multiplier:
            return True, f"global rate={rate:.2f} > {self.rate_multiplier}x baseline"
        return False, None

"""Per-caller token-bucket rate limiting and retry with exponential backoff and full jitter."""
import random
import threading
import time


class RateLimited(Exception):
    def __init__(self, key: str, retry_after: float):
        super().__init__(f"rate limit exceeded for {key}; retry after {retry_after:.2f}s")
        self.retry_after = retry_after


class TokenBucket:
    def __init__(self, rate_per_s: float, burst: int, clock=time.monotonic):
        self.rate, self.burst, self.clock = rate_per_s, burst, clock
        self._state: dict[str, tuple[float, float]] = {}
        self._lock = threading.Lock()

    def take(self, key: str, cost: float = 1.0) -> None:
        with self._lock:
            now = self.clock()
            tokens, last = self._state.get(key, (float(self.burst), now))
            tokens = min(self.burst, tokens + (now - last) * self.rate)
            if tokens < cost:
                self._state[key] = (tokens, now)
                raise RateLimited(key, (cost - tokens) / self.rate)
            self._state[key] = (tokens - cost, now)


def retry_with_backoff(fn, *, retries: int = 4, base: float = 0.2, cap: float = 5.0,
                       retry_on: tuple = (ConnectionError, TimeoutError, RateLimited),
                       sleep=time.sleep, rng=random.random):
    """Call fn(); on a retryable error wait base*2^n with full jitter (capped) and try again."""
    attempt = 0
    while True:
        try:
            return fn()
        except retry_on as e:
            if attempt >= retries:
                raise
            delay = min(cap, base * (2 ** attempt)) * rng()
            if isinstance(e, RateLimited):
                delay = max(delay, e.retry_after)
            sleep(delay)
            attempt += 1

import threading
import time

MAX_INPUT_CHARS = 500
HISTORY_WINDOW = 6
NUM_CTX = 2048
NUM_PREDICT = 220


class TokenBucket:
    def __init__(self, rate_per_sec, burst):
        self.rate = rate_per_sec
        self.burst = burst
        self.tokens = burst
        self.updated = time.time()
        self.lock = threading.Lock()

    def take(self):
        with self.lock:
            now = time.time()
            self.tokens = min(self.burst, self.tokens + (now - self.updated) * self.rate)
            self.updated = now
            if self.tokens >= 1:
                self.tokens -= 1
                return True, 0.0
            wait = (1 - self.tokens) / self.rate
            return False, round(wait, 1)


class RateLimiter:
    def __init__(self, per_ip_rate, per_ip_burst, global_rate, global_burst):
        self.per_ip_rate = per_ip_rate
        self.per_ip_burst = per_ip_burst
        self.buckets = {}
        self.lock = threading.Lock()
        self.global_bucket = TokenBucket(global_rate, global_burst)

    def _bucket_for(self, ip):
        with self.lock:
            bucket = self.buckets.get(ip)
            if bucket is None:
                bucket = TokenBucket(self.per_ip_rate, self.per_ip_burst)
                self.buckets[ip] = bucket
            return bucket

    def check(self, ip):
        ok, wait = self._bucket_for(ip).take()
        if not ok:
            return False, wait, "ip"
        ok, wait = self.global_bucket.take()
        if not ok:
            return False, wait, "global"
        return True, 0.0, ""


def clip_input(text):
    text = (text or "").strip()
    if len(text) > MAX_INPUT_CHARS:
        return text[:MAX_INPUT_CHARS], True
    return text, False


def trim_history(history):
    return history[-HISTORY_WINDOW:]

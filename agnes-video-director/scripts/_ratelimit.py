#!/usr/bin/env python3
"""Shared cross-process concurrency limiter + 429 retry for the Agnes API.

Measured behaviour of apihub.agnes-ai.com (free tier, agnes-image-2.5-flash):
  * at most 5 requests may be IN FLIGHT at once -> 6th+ returns HTTP 429
  * sequential requests are never throttled (no per-minute quota)
  * no x-ratelimit / retry-after headers are returned
So we cap concurrency (default 5, use 4 for safety) and retry 429 with backoff.

The limiter is a directory of slot files guarded by flock, so it also works when
several shell processes call gen_image.py in parallel.
"""
import errno
import fcntl
import json
import os
import time
import urllib.error

DEFAULT_MAX_CONCURRENT = 4  # server allows 5; stay one below for safety
SLOT_DIR = os.path.expanduser(os.environ.get("AGNES_SLOT_DIR", "~/.cache/agnes_slots"))
STATE_LOCK = os.path.join(SLOT_DIR, ".lock")


def _ensure_dir():
    os.makedirs(SLOT_DIR, exist_ok=True)


class Slot:
    """Context manager taking one concurrency slot (blocking until free)."""

    def __init__(self, max_concurrent=DEFAULT_MAX_CONCURRENT, verbose=True):
        self.max_concurrent = max(1, int(max_concurrent))
        self.verbose = verbose
        self.path = None
        self.waited = 0.0

    def __enter__(self):
        _ensure_dir()
        start = time.time()
        while True:
            with open(STATE_LOCK, "a+") as lockf:
                fcntl.flock(lockf, fcntl.LOCK_EX)
                try:
                    held = [f for f in os.listdir(SLOT_DIR) if f.startswith("slot.")]
                    dead = []
                    for f in held:
                        p = os.path.join(SLOT_DIR, f)
                        try:
                            pid = int(open(p).read().strip() or 0)
                        except Exception:
                            pid = 0
                        # reclaim slots whose owner process is gone
                        if pid and not _pid_alive(pid):
                            dead.append(p)
                    for p in dead:
                        try:
                            os.unlink(p)
                        except OSError:
                            pass
                    held = [f for f in os.listdir(SLOT_DIR) if f.startswith("slot.")]
                    if len(held) < self.max_concurrent:
                        self.path = os.path.join(
                            SLOT_DIR, f"slot.{os.getpid()}.{time.time_ns()}"
                        )
                        with open(self.path, "w") as fh:
                            fh.write(str(os.getpid()))
                        break
                finally:
                    fcntl.flock(lockf, fcntl.LOCK_UN)
            time.sleep(0.25)
        self.waited = time.time() - start
        if self.verbose and self.waited > 1.5:
            print(
                f"[ratelimit] waited {self.waited:.1f}s for a free slot "
                f"(max {self.max_concurrent} concurrent)"
            )
        return self

    def __exit__(self, *exc):
        if self.path:
            try:
                os.unlink(self.path)
            except OSError:
                pass
        return False


def _pid_alive(pid):
    try:
        os.kill(pid, 0)
    except OSError as e:
        return e.errno == errno.EPERM
    return True


def is_rate_limit(exc):
    if not isinstance(exc, urllib.error.HTTPError):
        return False
    if exc.code == 429:
        return True
    if exc.code in (500, 502, 503, 504):
        return True
    return False


def with_retry(fn, max_attempts=8, base_delay=10.0, max_delay=120.0, verbose=True,
               what="request"):
    """Call fn(); on 429/5xx retry with exponential backoff + jitter.

    Returns fn()'s value; re-raises the last HTTPError if all attempts fail.
    """
    import random

    last = None
    for attempt in range(1, max_attempts + 1):
        try:
            return fn()
        except urllib.error.HTTPError as e:
            body = ""
            try:
                body = e.read().decode(errors="replace")[:200]
            except Exception:
                pass
            if not is_rate_limit(e):
                raise
            last = e
            if attempt == max_attempts:
                break
            delay = min(max_delay, base_delay * (2 ** (attempt - 1)))
            delay += random.uniform(0, delay * 0.25)
            if verbose:
                print(
                    f"[ratelimit] {what}: HTTP {e.code} "
                    f"(attempt {attempt}/{max_attempts}), retrying in {delay:.0f}s",
                    flush=True,
                )
            time.sleep(delay)
    if verbose:
        print(f"[ratelimit] {what}: giving up after {max_attempts} attempts", flush=True)
    raise last
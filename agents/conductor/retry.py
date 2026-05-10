from __future__ import annotations

import functools
import time


def retry(max_attempts: int = 3, backoff_base: int = 2, exceptions=(Exception,)):
    def decorator(fn):
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            for attempt in range(1, max_attempts + 1):
                try:
                    return fn(*args, **kwargs)
                except exceptions:
                    if attempt == max_attempts:
                        raise
                    time.sleep(backoff_base ** attempt)
        return wrapper
    return decorator

"""
MeetingMind — Performance Metrics & Observability
Provides timing decorators and request tracking for monitoring system performance.
"""

import time
import uuid
import logging
from contextlib import contextmanager
from functools import wraps


@contextmanager
def track_request(operation_name):
    """Track request with unique ID and duration.

    Args:
        operation_name: Name of the operation being tracked.

    Yields:
        request_id: Unique 8-character request identifier.
    """
    request_id = str(uuid.uuid4())[:8]
    start = time.time()
    logging.info(f"📊 [{request_id}] {operation_name} STARTED")
    try:
        yield request_id
    finally:
        duration = time.time() - start
        logging.info(f"📊 [{request_id}] {operation_name} COMPLETED in {duration:.2f}s")


def timed_operation(operation_name):
    """Decorator for timing function execution.

    Logs operation duration and any failures with timing context.

    Args:
        operation_name: Name of the operation for logging.

    Returns:
        Decorated function with timing instrumentation.
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            start = time.time()
            try:
                result = func(*args, **kwargs)
                duration = time.time() - start
                logging.info(f"⏱️  {operation_name} took {duration:.3f}s")
                return result
            except Exception as e:
                duration = time.time() - start
                logging.error(f"❌ {operation_name} FAILED after {duration:.3f}s: {e}")
                raise
        return wrapper
    return decorator

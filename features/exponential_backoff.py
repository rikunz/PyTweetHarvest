from . import *

BASE_TIMEOUT = 60_000  # ms
MAXIMUM_TIMEOUT = 600_000  # ms
RATIO = 2

from ..env import ENABLE_EXPONENTIAL_BACKOFF


def calculate_for_rate_limit(attempt: int) -> int:
    if not ENABLE_EXPONENTIAL_BACKOFF:
        return BASE_TIMEOUT
    timeout = RATIO * attempt * BASE_TIMEOUT + BASE_TIMEOUT
    return min(timeout, MAXIMUM_TIMEOUT)

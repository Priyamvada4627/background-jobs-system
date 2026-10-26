import random
from typing import Optional


def calculate_backoff_delay(
    attempt_count: int,
    base_delay: float = 1.0,
    max_delay: float = 300.0,
    jitter_factor: float = 0.5,
    enable_jitter: bool = True,
) -> float:
    """
    Calculates retry backoff delay with exponential scaling and bounded random jitter.
    
    Formula:
        delay = min(max_delay, base_delay * 2^(attempt - 1)) + uniform(0, jitter)
    
    Args:
        attempt_count: 1-indexed count of executions performed so far.
        base_delay: Initial delay in seconds for the first retry.
        max_delay: Ceiling cap for exponential delay.
        jitter_factor: Proportion of calculated delay to use as upper bound for jitter.
        enable_jitter: Set to False in deterministic testing environments.
        
    Returns:
        float: Total backoff delay in seconds.
    """
    if attempt_count < 1:
        attempt_count = 1

    # Exponential component: attempt 1 -> base_delay * 2^0 = base_delay
    exponential = min(max_delay, base_delay * (2 ** (attempt_count - 1)))

    if not enable_jitter or jitter_factor <= 0:
        return round(float(exponential), 3)

    max_jitter = exponential * jitter_factor
    jitter = random.uniform(0.0, max_jitter)
    total_delay = min(max_delay, exponential + jitter)

    return round(float(total_delay), 3)

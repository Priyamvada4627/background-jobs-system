import pytest
from app.services.retry_policy import calculate_backoff_delay


def test_exponential_backoff_deterministic():
    """Verifies pure exponential backoff sequence when jitter is disabled."""
    base = 2.0
    cap = 50.0

    assert calculate_backoff_delay(1, base_delay=base, max_delay=cap, enable_jitter=False) == 2.0
    assert calculate_backoff_delay(2, base_delay=base, max_delay=cap, enable_jitter=False) == 4.0
    assert calculate_backoff_delay(3, base_delay=base, max_delay=cap, enable_jitter=False) == 8.0
    assert calculate_backoff_delay(4, base_delay=base, max_delay=cap, enable_jitter=False) == 16.0
    assert calculate_backoff_delay(5, base_delay=base, max_delay=cap, enable_jitter=False) == 32.0
    # Capped at max_delay
    assert calculate_backoff_delay(6, base_delay=base, max_delay=cap, enable_jitter=False) == 50.0
    assert calculate_backoff_delay(10, base_delay=base, max_delay=cap, enable_jitter=False) == 50.0


def test_bounded_jitter_distribution():
    """Verifies that jitter adds variance strictly within [exponential, min(cap, exponential * 1.5)]."""
    base = 10.0
    cap = 100.0
    jitter_factor = 0.5

    delays = [
        calculate_backoff_delay(1, base_delay=base, max_delay=cap, jitter_factor=jitter_factor, enable_jitter=True)
        for _ in range(50)
    ]

    for d in delays:
        assert 10.0 <= d <= 15.0

    # Ensure non-trivial variance across 50 samples
    assert len(set(delays)) > 10


def test_edge_case_zero_negative_attempt_count():
    """Verifies defensive handling of attempt_count <= 0."""
    delay = calculate_backoff_delay(0, base_delay=1.0, max_delay=10.0, enable_jitter=False)
    assert delay == 1.0

    delay_neg = calculate_backoff_delay(-5, base_delay=1.0, max_delay=10.0, enable_jitter=False)
    assert delay_neg == 1.0

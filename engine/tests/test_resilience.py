"""Tests for engine.resilience — rate_limiter, circuit_breaker."""

import pytest
from engine.resilience.circuit_breaker import CircuitBreaker
from engine.resilience.rate_limiter import RateLimiter


class TestCircuitBreaker:
    def test_initial_state_closed(self):
        cb = CircuitBreaker("test")
        assert cb.allow_request() is True

    def test_opens_after_failures(self):
        cb = CircuitBreaker("test", failure_threshold=3)
        for _ in range(3):
            cb.record_failure()
        assert cb.allow_request() is False

    def test_success_resets_counter(self):
        cb = CircuitBreaker("test", failure_threshold=3)
        cb.record_failure()
        cb.record_failure()
        cb.record_success()
        assert cb.allow_request() is True

    def test_half_open_after_cooldown(self):
        cb = CircuitBreaker("test", failure_threshold=2, cooldown_seconds=0.01)
        cb.record_failure()
        cb.record_failure()
        assert cb.allow_request() is False

        import time
        time.sleep(0.02)
        # After cooldown, should allow (half-open)
        assert cb.allow_request() is True


class TestRateLimiter:
    def test_wait_no_crash(self):
        # With zero delay, should not hang
        rl = RateLimiter(min_delay=0.0, max_delay=0.0)
        rl.wait()  # Should return immediately

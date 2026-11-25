from app.ratelimit import RateLimiter


class Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


def test_per_minute_limit_is_per_client_and_resets():
    clock = Clock()
    limiter = RateLimiter(per_minute=2, per_day=100, clock=clock)
    assert limiter.check("a") is None
    assert limiter.check("a") is None
    assert limiter.check("a") == "minute"
    assert limiter.check("b") is None
    clock.now += 60
    assert limiter.check("a") is None


def test_daily_limit_is_shared_by_all_clients():
    limiter = RateLimiter(per_minute=10, per_day=3, clock=Clock())
    assert [limiter.check(c) for c in "abc"] == [None, None, None]
    assert limiter.check("d") == "day"


def test_rejected_requests_do_not_use_the_daily_budget():
    limiter = RateLimiter(per_minute=1, per_day=2, clock=Clock())
    assert limiter.check("a") is None
    assert limiter.check("a") == "minute"
    assert limiter.check("b") is None
    assert limiter.check("c") == "day"


def test_one_client_cannot_use_the_whole_daily_budget():
    clock = Clock()
    limiter = RateLimiter(per_minute=10, per_day=100, per_client_day=2, clock=clock)
    assert limiter.check("a") is None
    assert limiter.check("a") is None
    clock.now += 60
    assert limiter.check("a") == "client-day"
    assert limiter.check("b") is None

import sys
from pathlib import Path

# Добавляем корень проекта (bot/) в sys.path
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.middlewares.rate_limit import RateLimiter


def test_rate_limiter_allows_within_limit():
    rl = RateLimiter(max_requests=2, window_seconds=10)

    allowed1, retry1 = rl.check(1, now=0.0)
    allowed2, retry2 = rl.check(1, now=1.0)

    assert allowed1 is True
    assert retry1 == 0.0
    assert allowed2 is True
    assert retry2 == 0.0


def test_rate_limiter_blocks_after_limit():
    rl = RateLimiter(max_requests=2, window_seconds=10)

    rl.check(1, now=0.0)
    rl.check(1, now=1.0)

    allowed3, retry3 = rl.check(1, now=2.0)

    assert allowed3 is False
    assert 0.0 < retry3 <= 10.0


def test_rate_limiter_resets_after_window():
    rl = RateLimiter(max_requests=2, window_seconds=10)

    rl.check(1, now=0.0)
    rl.check(1, now=1.0)

    # блок
    allowed3, _ = rl.check(1, now=2.0)
    assert allowed3 is False

    # новое окно
    allowed4, retry4 = rl.check(1, now=15.0)

    assert allowed4 is True
    assert retry4 == 0.0

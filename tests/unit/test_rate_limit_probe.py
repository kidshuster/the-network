from __future__ import annotations

import pytest

from tests.core.rate_limit_probe import (
    RateLimitHeaders,
    SmokeQuotaReport,
    _evaluate_probe,
    format_quota_report,
)


def test_rate_limit_headers_from_429_body() -> None:
    headers = {"X-RateLimit-Scope": "user"}
    rl = RateLimitHeaders.from_response(
        headers,
        body='{"message": "You are being rate limited.", "retry_after": 145.5}',
        status=429,
    )
    assert rl.retry_after == 145.5
    assert rl.scope == "user"


def test_rate_limit_headers_from_success() -> None:
    rl = RateLimitHeaders.from_response(
        {
            "X-RateLimit-Limit": "10",
            "X-RateLimit-Remaining": "7",
            "X-RateLimit-Reset-After": "12.345",
            "X-RateLimit-Scope": "shared",
        },
        status=201,
    )
    assert rl.limit == 10
    assert rl.remaining == 7
    assert rl.reset_after == pytest.approx(12.345)
    assert rl.scope == "shared"


def test_evaluate_probe_blocks_long_retry_after(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SMOKE_MAX_RETRY_AFTER_SEC", "30")
    from tests.core import rate_limit_probe as mod

    monkeypatch.setattr(mod, "MAX_RETRY_AFTER_SEC", 30.0)
    endpoint = _evaluate_probe(
        name="role POST",
        method="POST",
        path="/guilds/1/roles",
        status=429,
        headers=RateLimitHeaders(
            limit=None,
            remaining=0,
            reset=None,
            reset_after=None,
            scope="shared",
            retry_after=482.0,
        ),
    )
    assert endpoint.ok is False
    assert "482" in endpoint.detail


def test_evaluate_probe_ok_when_remaining_sufficient(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SMOKE_MIN_RATE_LIMIT_REMAINING", "1")
    from tests.core import rate_limit_probe as mod

    monkeypatch.setattr(mod, "MIN_REMAINING", 1)
    endpoint = _evaluate_probe(
        name="role POST",
        method="POST",
        path="/guilds/1/roles",
        status=201,
        headers=RateLimitHeaders(
            limit=10,
            remaining=5,
            reset=999,
            reset_after=1.0,
            scope="shared",
            retry_after=None,
        ),
    )
    assert endpoint.ok is True


def test_format_quota_report_ready() -> None:
    report = SmokeQuotaReport(
        guild_id=123,
        endpoints=[
            _evaluate_probe(
                name="role POST",
                method="POST",
                path="/guilds/123/roles",
                status=201,
                headers=RateLimitHeaders(
                    limit=10,
                    remaining=9,
                    reset=None,
                    reset_after=1.0,
                    scope="shared",
                    retry_after=None,
                ),
            ),
        ],
    )
    text = format_quota_report(report)
    assert "READY" in text
    assert "remaining=9" in text

from __future__ import annotations

import json
import os
import secrets
from dataclasses import dataclass, field
from typing import Any

import aiohttp

API_BASE = "https://discord.com/api/v10"
PROBE_PREFIX = "smoke-quota-probe"


def _delay_seconds(env_var: str, default: float) -> float:
    raw = os.environ.get(env_var)
    if raw is None or raw.strip() == "":
        return default
    try:
        return max(0.0, float(raw))
    except ValueError:
        return default


def _int_env(env_var: str, default: int) -> int:
    raw = os.environ.get(env_var)
    if raw is None or raw.strip() == "":
        return default
    try:
        return max(0, int(raw))
    except ValueError:
        return default


# Fail when 429 retry_after exceeds this (seconds).
MAX_RETRY_AFTER_SEC = _delay_seconds("SMOKE_MAX_RETRY_AFTER_SEC", 30.0)

# Require at least this many requests left in bucket after a successful probe POST.
MIN_REMAINING = _int_env("SMOKE_MIN_RATE_LIMIT_REMAINING", 1)


@dataclass(frozen=True)
class RateLimitHeaders:
    limit: int | None
    remaining: int | None
    reset: int | None
    reset_after: float | None
    scope: str | None
    retry_after: float | None

    @classmethod
    def from_response(
        cls,
        headers: Any,
        *,
        body: str | None = None,
        status: int,
    ) -> RateLimitHeaders:
        def header(name: str) -> str | None:
            return headers.get(name) if hasattr(headers, "get") else None

        retry_after: float | None = None
        if status == 429:
            if body:
                try:
                    payload = json.loads(body)
                    raw = payload.get("retry_after")
                    if raw is not None:
                        retry_after = float(raw)
                except (json.JSONDecodeError, TypeError, ValueError):
                    pass
            if retry_after is None:
                raw_header = header("Retry-After")
                if raw_header is not None:
                    try:
                        retry_after = float(raw_header)
                    except ValueError:
                        retry_after = None

        reset_after_raw = header("X-RateLimit-Reset-After")
        reset_after = float(reset_after_raw) if reset_after_raw is not None else None

        return cls(
            limit=_optional_int(header("X-RateLimit-Limit")),
            remaining=_optional_int(header("X-RateLimit-Remaining")),
            reset=_optional_int(header("X-RateLimit-Reset")),
            reset_after=reset_after,
            scope=header("X-RateLimit-Scope"),
            retry_after=retry_after,
        )


def _optional_int(raw: str | None) -> int | None:
    if raw is None:
        return None
    try:
        return int(raw)
    except ValueError:
        return None


@dataclass
class EndpointQuota:
    name: str
    method: str
    path: str
    status: int
    ok: bool
    headers: RateLimitHeaders
    detail: str = ""


@dataclass
class SmokeQuotaReport:
    guild_id: int
    endpoints: list[EndpointQuota] = field(default_factory=list)

    @property
    def ready(self) -> bool:
        return all(endpoint.ok for endpoint in self.endpoints)

    def blockers(self) -> list[EndpointQuota]:
        return [endpoint for endpoint in self.endpoints if not endpoint.ok]


def _evaluate_probe(
    *,
    name: str,
    method: str,
    path: str,
    status: int,
    headers: RateLimitHeaders,
    detail: str = "",
) -> EndpointQuota:
    ok = True
    reasons: list[str] = []

    if status == 429:
        ok = False
        retry = headers.retry_after
        if retry is not None:
            reasons.append(f"rate limited — retry after {retry:.1f}s")
            if retry > MAX_RETRY_AFTER_SEC:
                reasons.append(
                    f"exceeds SMOKE_MAX_RETRY_AFTER_SEC ({MAX_RETRY_AFTER_SEC:g}s)",
                )
        else:
            reasons.append("rate limited (429)")
    elif status >= 400:
        ok = False
        reasons.append(f"HTTP {status}")
    elif headers.remaining is not None and headers.remaining < MIN_REMAINING:
        ok = False
        reasons.append(
            f"only {headers.remaining} request(s) remaining "
            f"(need {MIN_REMAINING}, set SMOKE_MIN_RATE_LIMIT_REMAINING)",
        )

    merged_detail = detail
    if reasons:
        extra = "; ".join(reasons)
        merged_detail = f"{detail} — {extra}" if detail else extra

    return EndpointQuota(
        name=name,
        method=method,
        path=path,
        status=status,
        ok=ok,
        headers=headers,
        detail=merged_detail,
    )


def format_quota_report(report: SmokeQuotaReport) -> str:
    lines = [f"Discord smoke quota check (guild {report.guild_id})"]
    for endpoint in report.endpoints:
        mark = "OK" if endpoint.ok else "BLOCKED"
        h = endpoint.headers
        parts = [
            f"[{mark}] {endpoint.name}",
            f"{endpoint.method} {endpoint.path}",
            f"status={endpoint.status}",
        ]
        if h.limit is not None:
            parts.append(f"limit={h.limit}")
        if h.remaining is not None:
            parts.append(f"remaining={h.remaining}")
        if h.reset_after is not None:
            parts.append(f"reset_after={h.reset_after:.1f}s")
        if h.scope:
            parts.append(f"scope={h.scope}")
        if h.retry_after is not None:
            parts.append(f"retry_after={h.retry_after:.1f}s")
        if endpoint.detail:
            parts.append(endpoint.detail)
        lines.append("  " + " | ".join(parts))

    if report.ready:
        lines.append("Overall: READY for live smoke")
    else:
        lines.append("Overall: NOT READY — wait for buckets to reset or use a staging guild")
    return "\n".join(lines)


async def check_smoke_quota(
    *,
    token: str,
    guild_id: int,
    session: aiohttp.ClientSession | None = None,
) -> SmokeQuotaReport:
    """Probe Discord buckets used by live smoke (role + category + in-category channel)."""
    report = SmokeQuotaReport(guild_id=guild_id)
    owns_session = session is None
    if session is None:
        session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=30),
        )

    headers = {
        "Authorization": f"Bot {token}",
        "Content-Type": "application/json",
        "User-Agent": "TheNetworkSmokeQuotaProbe/1.0",
    }
    suffix = secrets.token_hex(3)

    try:
        async with session.get(f"{API_BASE}/guilds/{guild_id}", headers=headers) as resp:
            body = await resp.text()
            report.endpoints.append(
                _evaluate_probe(
                    name="guild GET (connectivity)",
                    method="GET",
                    path=f"/guilds/{guild_id}",
                    status=resp.status,
                    headers=RateLimitHeaders.from_response(
                        resp.headers,
                        body=body,
                        status=resp.status,
                    ),
                    detail="guild reachable" if resp.status == 200 else body[:120],
                ),
            )
            if resp.status != 200:
                return report

        role_id: str | None = None
        async with session.post(
            f"{API_BASE}/guilds/{guild_id}/roles",
            headers=headers,
            json={"name": f"{PROBE_PREFIX}-role-{suffix}"[:100]},
        ) as resp:
            body = await resp.text()
            rl = RateLimitHeaders.from_response(resp.headers, body=body, status=resp.status)
            if resp.status in (200, 201):
                role_id = json.loads(body)["id"]
            report.endpoints.append(
                _evaluate_probe(
                    name="role POST (operator/provision probes)",
                    method="POST",
                    path=f"/guilds/{guild_id}/roles",
                    status=resp.status,
                    headers=rl,
                    detail="create role" if resp.status in (200, 201) else body[:120],
                ),
            )

        category_id: str | None = None
        async with session.post(
            f"{API_BASE}/guilds/{guild_id}/channels",
            headers=headers,
            json={"name": f"{PROBE_PREFIX}-cat-{suffix}", "type": 4},
        ) as resp:
            body = await resp.text()
            rl = RateLimitHeaders.from_response(resp.headers, body=body, status=resp.status)
            if resp.status in (200, 201):
                category_id = json.loads(body)["id"]
            report.endpoints.append(
                _evaluate_probe(
                    name="category POST (provision probes)",
                    method="POST",
                    path=f"/guilds/{guild_id}/channels",
                    status=resp.status,
                    headers=rl,
                    detail="create category" if resp.status in (200, 201) else body[:120],
                ),
            )

        channel_id: str | None = None
        if category_id is not None:
            async with session.post(
                f"{API_BASE}/guilds/{guild_id}/channels",
                headers=headers,
                json={
                    "name": f"{PROBE_PREFIX}-ch-{suffix}",
                    "type": 0,
                    "parent_id": category_id,
                },
            ) as resp:
                body = await resp.text()
                rl = RateLimitHeaders.from_response(
                    resp.headers,
                    body=body,
                    status=resp.status,
                )
                if resp.status in (200, 201):
                    channel_id = json.loads(body)["id"]
                report.endpoints.append(
                    _evaluate_probe(
                        name="channel POST in category (operator probe)",
                        method="POST",
                        path=f"/guilds/{guild_id}/channels?parent_id=…",
                        status=resp.status,
                        headers=rl,
                        detail=(
                            "create in-category channel"
                            if resp.status in (200, 201)
                            else body[:120]
                        ),
                    ),
                )
        else:
            report.endpoints.append(
                EndpointQuota(
                    name="channel POST in category (operator probe)",
                    method="POST",
                    path=f"/guilds/{guild_id}/channels?parent_id=…",
                    status=0,
                    ok=False,
                    headers=RateLimitHeaders.from_response({}, status=0),
                    detail="skipped — category probe did not create a category",
                ),
            )

        # Best-effort cleanup of probe artifacts (ignore cleanup failures).
        if channel_id is not None:
            async with session.delete(
                f"{API_BASE}/channels/{channel_id}",
                headers=headers,
                json={"reason": "smoke quota probe cleanup"},
            ):
                pass
        if category_id is not None:
            async with session.delete(
                f"{API_BASE}/channels/{category_id}",
                headers=headers,
                json={"reason": "smoke quota probe cleanup"},
            ):
                pass
        if role_id is not None:
            async with session.delete(
                f"{API_BASE}/guilds/{guild_id}/roles/{role_id}",
                headers=headers,
                json={"reason": "smoke quota probe cleanup"},
            ):
                pass

    finally:
        if owns_session and session is not None:
            await session.close()

    return report

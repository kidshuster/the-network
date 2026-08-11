# Refactor Plan

Proposed behavior-preserving simplifications. **Do not execute until subsystem characterization tests pass.** Each item includes verification commands and rollback boundary.

Prioritized by confidence and duplication evidence from baseline inspection.

---

## First-track completion status (2026-08-10)

| Item | Status |
|------|--------|
| R1.1 Interaction authorization helper | **Done** — `ensure_manage_guild()` in `bot/cogs/_checks.py` |
| R1.2 Client role authorization helper | **Done** — `ensure_client_access()` in `bot/ui/_auth.py` |
| R1.3 Discord HTTP 50013 helper | **Done** — `tests/unit/discord_helpers.py` |
| R1.4 Repository row-fetch boilerplate | **Partial** — helpers added; further dedup in deeper Phase 3 |
| R2.1 Permission overwrite sync fallback | **Partial** — `sync_channel_permission_overwrites` + guild_init wiring |
| R2.2 Overwrite builder composition | **Deferred** — deeper Phase 4 (truth-table tests first) |
| R3.1 Sticky sync algorithm | **Partial** — `sticky_sync.py` for join + network-admin |
| R4.1 Wire `DeferredEphemeralResponse` | **Done** — `bot/cogs/servers.py` |
| R4.2 UI defer-then-followup helper | **Partial** — `defer_ephemeral()` applied; Phase 7 for response-mode centralization |
| R5.1 Client reconnect step runner | **Partial** — `step_runner.py` + `_finish_client_reconnect` |
| R5.2 Subscription resync discovery | **Done** — `resolve_subscription_channels_in_category()` |
| R6.1 Modal construction | **Partial** — hub/client modal validators in `bot/ui/_auth.py` |

See [refactor-results.md](refactor-results.md) for measurement deltas and deeper-track phase progress.

---

## Priority 1 — High-confidence mechanism duplication

### R1.1 Interaction authorization helper unification

| Field | Value |
|-------|-------|
| Files | `bot/cogs/_checks.py`, `bot/ui/network_admin_views.py`, scattered UI handlers |
| Duplication | `_require_manage_guild(interaction)` duplicates `require_manage_guild()` predicate + sends popup |
| Protecting tests | `test_require_manage_guild.py`, `test_button_command_parity.py` |
| Proposed abstraction | Shared `async def ensure_manage_guild(interaction) -> bool` returning False after sending `manage_guild_required` |
| Expected reduction | ~40 lines |
| Behavioral risks | Message must remain `manage_guild_required` popup text; timing of send vs raise |
| Verification | `pytest tests/unit/test_require_manage_guild.py tests/unit/test_network_admin.py tests/unit/test_button_command_parity.py -q` |
| Rollback boundary | Single commit; revert if any admin UI auth test fails |
| User-facing messages | No change expected |

### R1.2 Client role authorization helper

| Field | Value |
|-------|-------|
| Files | `bot/ui/network_views.py`, `bot/ui/profile_views.py` |
| Duplication | Repeated client-role-or-admin checks with distinct popup keys |
| Protecting tests | `test_network_views_handlers.py` (+ new handler error tests needed) |
| Proposed abstraction | `ensure_client_access(interaction, client, *, popup_key)` — policy explicit at call site |
| Expected reduction | ~60 lines |
| Behavioral risks | Different popup keys per action (`client_role_required_subscribe` vs `_edit` vs `_delete`) must remain |
| Verification | `pytest tests/unit/test_network_views_handlers.py tests/unit/test_client_deletion.py -q` |
| Rollback boundary | UI layer only |
| User-facing messages | Must preserve exact popup keys |

### R1.3 Discord HTTP 50013 helper usage

| Field | Value |
|-------|-------|
| Files | Multiple services; `tests/unit/discord_helpers.py` has `http_50013` |
| Duplication | Inline `_http_50013()` copies in individual test files |
| Protecting tests | All permission-related tests |
| Proposed abstraction | Consolidate tests to import `discord_helpers.http_50013` |
| Expected reduction | ~30 lines (tests only) |
| Behavioral risks | None (test-only) |
| Verification | Full pytest |
| Rollback boundary | Test-only commit |

### R1.4 Repository row-fetch boilerplate

| Field | Value |
|-------|-------|
| Files | `bot/db/repositories.py` |
| Duplication | Repeated create → commit → fetch → `RuntimeError` if missing patterns |
| Protecting tests | All `test_*_repository.py` |
| Proposed abstraction | Private `_fetch_required_client(id)` / shared insert helper — **not** a generic ORM |
| Expected reduction | ~80 lines |
| Behavioral risks | Error types and messages on not-found must remain identical |
| Verification | `pytest tests/unit/test_*_repository.py -q` |
| Rollback boundary | Single db/repositories commit |
| User-facing messages | Repository errors only (domain exceptions unchanged)

---

## Priority 2 — Permission and overwrite mechanics

### R2.1 Permission overwrite sync fallback chain

| Field | Value |
|-------|-------|
| Files | `bot/services/guild_permissions.py` |
| Duplication | Bulk edit → category sync → incremental set_permissions repeated for multiple channel types |
| Protecting tests | `test_guild_permissions.py`, `test_guild_permissions_client.py`, `test_permission_probe.py` |
| Proposed abstraction | `async def apply_overwrites_with_fallback(channel, overwrites, *, label)` callback for logging context |
| Expected reduction | ~50 lines |
| Behavioral risks | **High** — effective access must remain identical |
| Verification | Permission tests + compare overwrite dicts before/after; `pytest tests/unit/test_guild_permissions*.py tests/unit/test_permission_probe.py -q` |
| Rollback boundary | guild_permissions.py only |
| User-facing messages | Discord step errors via `discord_errors.py` unchanged |

### R2.2 Overwrite builder composition

| Field | Value |
|-------|-------|
| Files | `bot/services/guild_permissions.py` |
| Duplication | Similar everyone-deny + role-allow patterns across channel types |
| Protecting tests | `test_guild_permissions.py` |
| Proposed abstraction | Data table mapping channel kind → overwrite recipe; builders stay explicit |
| Expected reduction | ~40 lines |
| Behavioral risks | Category inheritance interactions |
| Verification | Full guild permission test suite |
| Rollback boundary | Do not merge hub vs client policies without truth-table proof |

---

## Priority 3 — Sticky synchronization skeleton

### R3.1 Sticky sync algorithm

| Field | Value |
|-------|-------|
| Files | `join_requests_sticky.py`, `rules_sticky.py`, `network_admin_sticky.py`, `subscription_setup_sticky.py` |
| Duplication | Version/footer signature check; fetch-or-send; settings callback persistence |
| Protecting tests | `test_*_sticky.py`, `test_subscription_setup.py` |
| Proposed abstraction | Shared `StickySyncContext` with injected content builder and wipe policy |
| Expected reduction | ~100 lines |
| Behavioral risks | Rules sticky always wipes; others differ — mode flags must be explicit |
| Verification | All sticky tests + template snapshot comparisons |
| Rollback boundary | One sticky service at a time |
| User-facing messages | Embed content byte-identical |

---

## Priority 4 — Interaction response handling

### R4.1 Wire `DeferredEphemeralResponse` into slash commands

| Field | Value |
|-------|-------|
| Files | `bot/cogs/servers.py`, `bot/cogs/_responses.py` |
| Duplication | Manual defer/followup/ensure-sent patterns in init/uninit |
| Protecting tests | `test_deferred_ephemeral_response.py`, guild init tests |
| Proposed abstraction | Use existing `DeferredEphemeralResponse` class |
| Expected reduction | ~25 lines |
| Behavioral risks | `ensure_sent` fallback only when nothing sent — must not double-send |
| Verification | `pytest tests/unit/test_guild_init.py tests/unit/test_guild_uninit.py tests/unit/test_deferred_ephemeral_response.py -q` |
| Rollback boundary | servers.py cog only |

### R4.2 UI defer-then-followup helper

| Field | Value |
|-------|-------|
| Files | `bot/ui/network_views.py`, `join_views.py`, `network_admin_views.py` |
| Duplication | Repeated `interaction.response.defer(ephemeral=True)` + error followup patterns |
| Protecting tests | Need expanded handler tests first (**blocker**) |
| Proposed abstraction | `async def defer_ephemeral(interaction)` + `send_embed_followup` |
| Expected reduction | ~80 lines |
| Behavioral risks | Ephemeral flag consistency (known omissions must be preserved or documented as fixes) |
| Verification | UI handler characterization suite |
| Rollback boundary | UI layer |

---

## Priority 5 — Service orchestration

### R5.1 Client reconnect step runner

| Field | Value |
|-------|-------|
| Files | `bot/services/client_reconnect.py`, `bot/services/guild_init.py` |
| Duplication | Per-step try/except/log/continue loops |
| Protecting tests | `test_client_reconnect.py`, `test_guild_init.py` |
| Proposed abstraction | Step list with name + async callable; shared timeout wrapper |
| Expected reduction | ~40 lines |
| Behavioral risks | Step order is contractual |
| Verification | Reconnect + init tests |

### R5.2 Subscription resync shared discovery

| Field | Value |
|-------|-------|
| Files | `client_subscription.py`, `client_permission_rectification.py` |
| Duplication | Orphan channel discovery by name prefix |
| Protecting tests | `test_client_subscription.py`, `test_client_permission_rectification.py` |
| Proposed abstraction | `find_orphan_subscription_channels(guild, client)` |
| Expected reduction | ~35 lines |
| Behavioral risks | Name slug rules from `channel_names.py` |

---

## Priority 6 — Message/template infrastructure

### R6.1 Modal construction

| Field | Value |
|-------|-------|
| Files | `bot/ui/*_views.py`, `bot/messages/modals_builder.py` |
| Duplication | Each modal repeats bot_context checks and guild validation |
| Protecting tests | `test_button_command_parity.py`, `test_message_templates_flows.py` |
| Proposed abstraction | Pre-submit validation helper returning rendered error text |
| Expected reduction | ~45 lines |
| User-facing messages | Preserve exact template keys |

---

## Intentionally NOT deduplicating (yet)

| Area | Reason |
|------|--------|
| Hub vs client permission policies | Different authorization rules and overwrite truth tables |
| Join vs rules vs network admin sticky wipe policies | Different transactional semantics |
| `server_request_service` approve vs deny | Different side effects and cleanup |
| Network vs client validation errors | Different audience and corrective actions |
| Smoke probe modules | Live Discord coupling; dedup risks cleanup guarantees |
| Function-local imports in services | Investigate cycle root cause before moving |

---

## Circular dependency investigation

| Location | Notes |
|----------|-------|
| `client_profile_edit.py` → `emoji_service` (inline import) | Likely avoids client→service cycle |
| `network_admin.py` → multiple services | Review after domain protocol extraction |

**Preferred remedies:** dependency-neutral types in `bot/domain/`; explicit dependency injection; no mechanical import moves.

---

## Execution order

1. Complete UI handler characterization tests (blocker for R1.2, R4.2)
2. R1.3 (test-only consolidation)
3. R1.1 (auth helper)
4. R1.4 (repository helpers)
5. R4.1 (deferred response wiring)
6. R2.1–R2.2 (permissions — highest risk, maximum test coverage required)
7. R3.1 (stickies — one module per commit)
8. R5.x (orchestration)
9. R6.1 (modals)

---

## Verification commands (full gate)

```bash
source .venv/bin/activate
ruff check .
mypy bot
pytest
# Live (when Discord env available):
# tests/live/smoke_server_init.sh
# tests/live/smoke_testwork.sh
```

---

*Phase 3 plan. Update after each completed refactor with actual line-count delta and any deferred items.*

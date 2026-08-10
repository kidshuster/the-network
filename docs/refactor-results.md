# Refactor Results

Running log of behavior-preserving refactor progress. Updated after each phase.

**Last updated:** 2026-08-10  
**Branch:** main @ Phase 3 partial

---

## Measurement columns

| Metric | Pre-characterization | Post-characterization / pre-first-refactor | Post-first-refactor | Current |
|--------|--------------------:|------------------------------------------:|--------------------:|--------:|
| Production Python lines (`bot/`) | ~18,119 | ~18,119 | 18,017 | 18,017 |
| Test Python lines (`tests/`) | ~11,080 | ~11,080 | 12,376 | 12,395 |
| Test count | ~421 | 455 | 468 | 468 |
| Ruff errors | — | 4 (pre-existing) | 13 | **0** |
| Pytest warnings | — | 1 (`audioop`) | 1 | **0** |
| Function-local `bot` imports | — | — | 174 | 174 |
| Mypy errors (`mypy bot`) | — | ~132 | ~135 | ~135 |

Pre-characterization figures from original inventory (~421 tests). Post-characterization reflects characterization test additions before the first refactor track. Post-first-refactor reflects commit `def2e29`.

---

## First refactor track (complete @ `def2e29`)

| Item | Status | Notes |
|------|--------|-------|
| R1.1 `ensure_manage_guild()` | **Done** | `bot/cogs/_checks.py` |
| R1.2 `ensure_client_access()` | **Done** | `bot/ui/_auth.py`; popup keys preserved per action |
| R1.3 `http_50013` test helper | **Done** | `tests/discord_helpers.py` |
| R1.4 Repository row helpers | **Partial** | `_insert_row_id`, `_fetch_row_by_id`, `_row_after_insert`; further dedup in Phase 3 |
| R2.1 Permission overwrite fallback | **Partial** | `sync_channel_permission_overwrites`; wired into `guild_init._edit_overwrites` |
| R2.2 Overwrite builder composition | **Deferred** | Phase 4 (truth-table tests first) |
| R3.1 Sticky sync algorithm | **Partial** | `sticky_sync.py` for join + network-admin; rules/subscription deferred |
| R4.1 `DeferredEphemeralResponse` | **Done** | `bot/cogs/servers.py` |
| R4.2 `defer_ephemeral()` UI helper | **Partial** | Applied across UI handlers; response-mode centralization in Phase 7 |
| R5.1 Step runner | **Partial** | `step_runner.py`; init/uninit + reconnect finish |
| R5.2 Subscription channel discovery | **Done** | `resolve_subscription_channels_in_category()` |
| R6.1 Modal validation helpers | **Partial** | `validate_hub_modal_context`, `validate_client_modal_context` |

### Dead code removed (first track)

- `ProfileRepository`, `ProfileRow`, `bot/domain/profile.py`
- `bot/domain/network_route.py`
- `bot/services/guild_channels.py` (merged into `guild_layout.py`)
- `sync_partner_feed_channel_permissions()` (never called)
- Legacy join sticky aliases, `JoinServerView`/`JoinRequestModal` aliases
- `tests/test_profile_repository.py`

### New shared modules (first track)

- `bot/services/step_runner.py`
- `bot/services/sticky_sync.py`
- `bot/ui/_auth.py`

---

## Deeper refactor track progress

| Phase | Status | Commit | Notes |
|-------|--------|--------|-------|
| 0 — Quality gate | **Done** | `ee17a0e` | Ruff 0 errors; pytest 468 passed, 0 warnings; audioop filter |
| 1 — Docs reconciliation | **In progress** | — | This document + baseline/plan updates |
| 2 — Dependency boundaries | Pending | — | Target: zero service→UI imports |
| 3 — Repository simplification | Pending | — | Target: 15–25% reduction in `repositories.py` |
| 4 — Permission policy | Pending | — | Truth-table tests before refactor |
| 5 — Guild init decomposition | Pending | — | |
| 6 — Sticky consolidation | Pending | — | |
| 7 — UI auth/responses | Pending | — | |
| 8 — Client resource resolver | Pending | — | |
| 9 — Smoke infrastructure | Pending | — | |
| 10 — Dead code pass | Pending | — | |
| 11 — Final verification | Pending | — | |

---

## Preserved behaviors (verified)

- All 468 tests pass after first refactor track and Phase 0
- Distinct popup keys per client-access action unchanged
- Join modal uses `hub_guild_only` (not `central_guild_only`); ephemeral omissions preserved
- `guild_init._edit_overwrites` uses explicit `bool` return + `fallback=False`
- Rules sticky wipe-first semantics unchanged
- Hub vs client permission policies remain separate

---

## Intentionally not deduplicated

| Area | Reason |
|------|--------|
| Hub vs client permission policies | Different authorization rules; Phase 4 requires truth-table proof |
| Rules sticky vs stored stickies | Different wipe/transaction semantics |
| Subscription setup stickies | History-scan discovery workflow |
| Smoke probe modules | Live Discord coupling; cleanup guarantees |

---

## Risks and known gaps

- Mypy: ~135 pre-existing errors in 28 files (not a refactor gate today)
- Coverage: ~61% overall; UI handlers and smoke modules under-tested
- Service→UI import violations remain (Phase 2 target)
- Largest files unchanged: `repositories.py` (1096), `guild_init.py` (1062), `guild_permissions.py` (974)

---

*Update this document after each deeper-track phase with line counts, test count, completed items, and any behavioral notes.*

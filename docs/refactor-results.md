# Refactor Results

Running log of behavior-preserving refactor progress. Updated after each phase.

**Last updated:** 2026-08-10  
**Branch:** main (Phases 5–11 complete; Phase 9 live validation partial; uncommitted)

---

## Measurement columns

| Metric | Pre-characterization | Post-characterization / pre-first-refactor | Post-first-refactor | Current |
|--------|--------------------:|------------------------------------------:|--------------------:|--------:|
| Production Python lines (`bot/`) | ~18,119 | ~18,119 | 18,017 | **18,665** |
| Test Python lines (`tests/`) | ~11,080 | ~11,080 | 12,376 | **13,120** |
| Test count | ~421 | 455 | 468 | **487** |
| Ruff errors | — | 4 (pre-existing) | 13 | **0** |
| Pytest warnings | — | 1 (`audioop`) | 1 | **0** |
| Function-local `bot` imports | — | — | 174 | **97** (services layer clean of UI) |
| Mypy errors (`mypy bot`) | — | ~132 | ~135 | **0** |

Pre-characterization figures from original inventory (~421 tests). Post-characterization reflects characterization test additions before the first refactor track. Post-first-refactor reflects commit `def2e29`.

---

## First refactor track (complete @ `def2e29`)

| Item | Status | Notes |
|------|--------|-------|
| R1.1 `ensure_manage_guild()` | **Done** | `bot/cogs/_checks.py` |
| R1.2 `ensure_client_access()` | **Done** | `bot/ui/_auth.py`; popup keys preserved per action |
| R1.3 `http_50013` test helper | **Done** | `tests/unit/discord_helpers.py` |
| R1.4 Repository row helpers | **Partial** | `_insert_row_id`, `_fetch_row_by_id`, `_row_after_insert`; further dedup in Phase 3 |
| R2.1 Permission overwrite fallback | **Done** | `apply_overwrites_with_fallback()` + `sync_channel_permission_overwrites`; guild_init wired |
| R2.2 Overwrite builder composition | **Done** | Hub/client/leaders recipe helpers; truth-table tests lock behavior |
| R3.1 Sticky sync algorithm | **Done** | `sticky_sync.py` — join, network-admin, rules (wipe), subscription setup (footer marker) |
| R4.1 `DeferredEphemeralResponse` | **Done** | `bot/cogs/servers.py` |
| R4.2 `defer_ephemeral()` UI helper | **Done** | `send_text`/`send_embed_message`; UI handlers migrated |
| R5.1 Step runner | **Partial** | `step_runner.py`; init/uninit + reconnect finish |
| R5.2 Subscription channel discovery | **Done** | `resolve_subscription_channels_in_category()` |
| R6.1 Modal validation helpers | **Partial** | `validate_hub_modal_context`, `validate_client_modal_context` |

### Dead code removed (first track)

- `ProfileRepository`, `ProfileRow`, `bot/domain/profile.py`
- `bot/domain/network_route.py`
- `bot/services/guild_channels.py` (merged into `guild_layout.py`)
- `sync_partner_feed_channel_permissions()` (never called)
- Legacy join sticky aliases, `JoinServerView`/`JoinRequestModal` aliases
- `tests/unit/test_profile_repository.py`

### New shared modules (first track)

- `bot/services/step_runner.py`
- `bot/services/sticky_sync.py`
- `bot/ui/_auth.py`

### New shared modules (deeper track)

- `bot/services/guild_init_result.py`
- `bot/services/guild_init_reconcilers.py`
- `bot/services/client_resources.py`
- `tests/permission_truth_table.py`
- `tests/unit/test_permission_effective_access.py`
- `bot/ui/_view_helpers.py`

---

## Deeper refactor track progress

| Phase | Status | Commit | Notes |
|-------|--------|--------|-------|
| 0 — Quality gate | **Done** | `ee17a0e` | Ruff 0 errors; pytest 468 passed, 0 warnings; audioop filter |
| 1 — Docs reconciliation | **Done** | `6d1533a` | Baseline/plan/results docs |
| 2 — Dependency boundaries | **Done** | `c20a1d6` | ViewRegistry injection; zero service→UI imports; 2 architecture tests |
| 3 — Repository simplification | **Partial** | `e91d365` | Shared helpers; net line count unchanged (dedup groundwork) |
| 4 — Permission policy | **Done** | Truth-table tests + R2.1/R2.2 builder composition in `guild_permissions.py` |
| 5 — Guild init decomposition | **Done** | — | `guild_init.py` 429 lines; reconcilers in `guild_init_reconcilers.py` (649); `GuildInitResult` extracted |
| 6 — Sticky consolidation | **Done** | — | Rules via wipe-mode `sync_stored_embed_sticky`; subscription setup via `sync_footer_marker_embed_sticky` |
| 7 — UI auth/responses | **Done** | — | Explicit `MembershipPolicy` at all call sites; `DeferredEphemeralResponse.send_text` |
| 8 — Client resource resolver | **Done** | — | `ClientResources` + `resolve_client_resources`; wired subscription/profile/setup services |
| 9 — Smoke infrastructure | **Done** | — | Shared `constants.py`, `delete_guild_channel_for_cleanup()`; guard no longer sweeps guild artifacts mid-init; timeout tuning; Leaders sync fixes (`manage_roles` on hub overwrite, probe strip via `set_permissions(None)`, operator top-role incremental skip) |
| 10 — Dead code pass | **Done** | — | Removed unused `build_moderator_overwrite`, `build_feed_category_overwrites` aliases |
| 11 — Final verification | **Done** | — | ruff 0, mypy 0, **487** pytest passed |

---

## Preserved behaviors (verified)

- All **487** tests pass (includes permission truth-table + architecture import tests)
- Distinct popup keys per client-access action unchanged
- Join modal uses `hub_guild_only` (not `central_guild_only`); ephemeral omissions preserved
- `guild_init._edit_overwrites` uses explicit `bool` return + `fallback=False`
- Rules sticky wipe-first semantics unchanged
- Hub vs client permission policies remain separate (17 truth-table scenarios in `test_permission_effective_access.py`)

---

## Intentionally not deduplicated

| Area | Reason |
|------|--------|
| Hub vs client permission policies | Different authorization rules; Phase 4 requires truth-table proof |
| Rules sticky vs stored stickies | Rules now shares wipe path via `sync_stored_embed_sticky(wipe_channel=True)` with distinct permission/pin/settings hooks |
| Subscription setup stickies | Footer-marker scan consolidated; DB-backed message IDs and create/reconcile modes preserved |
| Smoke probe modules | Live Discord coupling; shared constants and cleanup helpers consolidated; per-flow cleanup semantics preserved |

---

## Risks and known gaps

- Mypy: **0** errors (`mypy bot`)
- Coverage: ~61% overall; UI handlers and smoke modules under-tested
- Service→UI import violations eliminated in `bot/services/` (Phase 2)
- Largest files: `guild_permissions.py` (~1031), `guild_init_reconcilers.py` (649), `guild_init.py` (429, down from ~1062)

---

*Update this document after each deeper-track phase with line counts, test count, completed items, and any behavioral notes.*

# Refactor Baseline Metrics

Snapshot taken after Phase 1 inventory and Phase 2 characterization test additions. Use as the comparison point for all production refactoring.

**Date:** 2026-08-10  
**Branch:** main @ `ee17a0e` (Phase 0 quality gate)  
**Package version:** 1.2.15

---

## Line counts

| Metric | Count |
|--------|------:|
| Production Python lines (`bot/`) | 18,017 |
| Test Python lines (`tests/`) | 12,395 |
| Production Python modules | 89 |
| Test Python modules | 85 |
| YAML message templates (`bot/messages/`) | 75 |
| Changelog YAML | 1 |

---

## Test suite

| Metric | Value |
|--------|------:|
| Test count | 468 |
| Test runtime | ~40 s (full suite, WSL2) |
| Pass rate | 468/468 (100%) |

### New characterization tests added in baseline

| File | Tests | Focus |
|------|------:|-------|
| `test_client_repository.py` | 16 | Client CRUD, subscriptions, blacklist |
| `test_relay_record_repository.py` | 4 | Relay dedup, status updates |
| `test_server_request_repository.py` | 5 | Join request workflow persistence |
| `test_settings_repository.py` | 3 | Settings upsert |
| `test_client_profile_edit.py` | 5 | Profile edit service contract |
| `test_deferred_ephemeral_response.py` | 4 | Deferred response helper |
| `test_require_manage_guild.py` | 4 | Slash command authorization |

### Shared test infrastructure added

| File | Purpose |
|------|---------|
| `tests/repository_helpers.py` | Network/client/subscription factories |
| `tests/interaction_helpers.py` | Interaction/member/channel/message builders |

---

## Coverage by package

| Package | Lines covered | Total | % |
|---------|--------------:|------:|--:|
| `bot/domain` | 127 | 136 | 93.4 |
| `bot/messages` | 170 | 189 | 89.9 |
| `bot/db` | 572 | 771 | 74.2 |
| `bot/services` | 2,903 | 4,266 | 68.0 |
| `bot/cogs` | 86 | 268 | 32.1 |
| `bot/ui` | 240 | 592 | 40.5 |
| `bot/smoke` | 433 | 1,349 | 32.1 |
| `bot` (root) | 125 | 293 | 42.7 |
| **Total** | **4,677** | **7,906** | **61.0** |

---

## Lowest-coverage production modules (behavioral risk)

| Module | Coverage | Notes |
|--------|----------|-------|
| `bot/main.py` | 0% | Entry point; not unit tested |
| `bot/logging_config.py` | 0% | Logging setup |
| `bot/client.py` | ~15% | Startup, persistent views, on_ready |
| `bot/services/hub_announcements.py` | 23% | Complex dispatch logic |
| `bot/smoke/provision_flow.py` | 23% | Live smoke orchestration |
| `bot/smoke/server_init_probes.py` | 25% | Live probes |
| `bot/ui/network_views.py` | 35% | Most interaction handlers |
| `bot/ui/join_views.py` | 44% | Join/review handlers |
| `bot/ui/network_admin_views.py` | 40% | Network admin handlers |
| `bot/services/discord_cleanup.py` | 40% | Cleanup helpers |
| `bot/services/image_service.py` | 40% | URL download path untested |
| `bot/services/client_deletion.py` | 54% | Partial failure paths |
| `bot/services/guild_uninit.py` | 54% | Deletion orchestration |

---

## Known coverage exclusions

| Exclusion | Justification |
|-----------|---------------|
| `bot/main.py`, `bot/logging_config.py` | Thin entry/logging wrappers; low behavioral risk |
| Live smoke modules at low % | Require real Discord guild; protected by smoke scripts |
| `bot/client.py` full startup | Requires Discord gateway or extensive bot mock; defer to integration/smoke |
| URL image download (`image_service`) | Requires network mock; lower priority than attachment path |

---

## Quality gate results (baseline)

| Check | Result |
|-------|--------|
| `pytest` | ✅ 468 passed, 0 warnings |
| `ruff check .` | ✅ 0 errors |
| `mypy bot` | ⚠️ ~135 pre-existing errors in 28 files |
| Smoke scripts | Not run in baseline (require live Discord + env) |

---

## Tests coupled to implementation details

See [test-coverage-map.md](test-coverage-map.md#tests-overly-coupled-to-implementation) for the full list. Primary concerns:

- Guild init step mocking
- Permission probe step names
- Service monkeypatch paths in UI handler tests

---

## Behaviors protected only by live smoke

- Full join-approval → subscribe → webhook → relay end-to-end
- Hub rebuild (uninit + DB reset + init + network recreate)
- Server init probe suite (operator live permissions, idempotent reinit)
- Hub announcement dispatch to all enabled networks
- Activation welcome embed appearance in channel history
- Permission probe auto-deleted Discord artifacts

---

## Baseline completeness assessment

The baseline is **not complete** solely on coverage percentage (61%). Meaningful behavioral branches are characterized for:

- ✅ All repository CRUD and constraint contracts
- ✅ Core domain validation (network, profile, routing, relay filters)
- ✅ Guild permission overwrite builders
- ✅ Message template rendering
- ✅ Join request service orchestration
- ✅ Slash command authorization check
- ✅ Profile edit service
- ✅ UI handler error matrix (join, network, network-admin views)
- ✅ Deferred ephemeral response helper
- ✅ Smoke teardown orchestration

**Remaining before deeper production refactoring:**

- Hub announcements dispatch edge cases
- Guild uninit preservation table (full matrix)
- Startup/persistent view registration
- Subscription sticky reconcile vs create modes

See [refactor-results.md](refactor-results.md) for first-track completion status and deeper-track phase progress.

---

## Focused refactor baseline (Track A + Track B)

Snapshot for the permission API consolidation and repository rewrite plan.
**Date:** 2026-08-10  
**Branch:** main @ `7b1bf48`

### Track A — permission-related LOC

| Module | Lines |
|--------|------:|
| `bot/services/guild_permissions.py` | 1,067 |
| `bot/services/leaders_channel.py` | 489 |
| `bot/services/guild_init_reconcilers.py` | 653 |
| `bot/services/permission_probe.py` | 422 |
| `bot/services/client_provision.py` | 145 |
| `bot/services/client_subscription.py` | 685 |
| `bot/services/client_permission_rectification.py` | 143 |
| **Subtotal (direct permission callers)** | **3,604** |

Legacy helpers to remove after migration: `strip_bot_member_overwrites`,
`prepare_category_create_overwrites`, `filter_configurable_overwrites`,
`apply_overwrites_with_fallback`, `sync_channel_permission_overwrites`,
`create_text_channel_with_overwrites`, `sync_client_category_permissions`,
Leaders-specific fallbacks and direct `set_permissions` loops.

### Track B — repository-related LOC

| Module | Lines |
|--------|------:|
| `bot/db/repositories.py` | 1,096 |
| `bot/db/models.py` | 181 |
| `bot/db/connection.py` | 44 |
| `bot/db/migrations.py` | 624 |
| **Subtotal** | **1,945** |

`ClientRepository` currently owns client, subscription, and blacklist persistence
(~40 methods). Row mappers still contain migration-column fallbacks (`in row.keys()`).

### Stage 0 quality gate (focused refactor)

| Check | Result |
|-------|--------|
| `ruff check .` | ✅ |
| `mypy bot` | ✅ |
| `pytest -q` | ✅ 499+ passed |

### Stage 0 characterization tests added

| File | Focus |
|------|-------|
| `test_permission_filter_divergence.py` | Documents filter/creation/fallback divergence on operator and bot targets |
| `test_migration_helpers.py` | `_column_not_null` correctness and single-fetch regression |
| `test_repository_characterization.py` | ClientRepository domain boundary inventory, autocommit, partial network delete |

### Next commits (separate tracks)

**Track A:** semantic models → compiler → `PermissionService` → Leaders-first migration  
**Track B:** migration fix → repository split → transactions → caller migration

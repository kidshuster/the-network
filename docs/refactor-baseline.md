# Refactor Baseline Metrics

Snapshot taken after Phase 1 inventory and Phase 2 characterization test additions. Use as the comparison point for all production refactoring.

**Date:** 2026-08-10  
**Branch:** main (uncommitted baseline work)  
**Package version:** 1.2.15

---

## Line counts

| Metric | Count |
|--------|------:|
| Production Python lines (`bot/`) | 18,119 |
| Test Python lines (`tests/`) | 11,080 |
| Production Python modules | 89 |
| Test Python modules | 78 |
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
| Top.gg posting | External API; warning-only on failure |

---

## Quality gate results (baseline)

| Check | Result |
|-------|--------|
| `pytest` | ✅ 455 passed |
| `ruff check .` | ⚠️ 4 pre-existing issues (unrelated files) |
| `mypy bot` | ⚠️ 132 pre-existing errors in 28 files |
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

**Remaining before production refactoring should proceed subsystem-by-subsystem:**

- UI interaction handler error matrix
- Hub announcements dispatch
- Guild uninit preservation table
- Startup/persistent view registration
- Subscription sticky reconcile vs create modes

---

*Do not edit production code until subsystem-specific characterization tests exist for the refactor target. Update this document after each refactoring step.*

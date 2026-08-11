# Test Coverage Map

Maps major observable behaviors to protecting tests. See [behavioral-contract.md](behavioral-contract.md) for full behavior specifications.

**Legend**

- ✅ Direct characterization test exists
- ⚠️ Partial coverage (some branches untested)
- 🔴 Missing local test (live smoke only or no coverage)
- 📋 Implementation-coupled (may need refactor to behavior-level)

---

## Slash commands

| Behavior | Tests | Coverage |
|----------|-------|----------|
| `/server init` success path | `test_guild_init.py`, `test_guild_init_hub_order.py`, `test_guild_init_moderator_role.py` | ⚠️ |
| `/server init` validation failure | `test_guild_init.py`, `test_permission_probe.py` | ✅ |
| `/server init` rectification embeds | `test_server_init_rectification_embed.py` | ✅ |
| `/server init` step timeout/HTTP continue | `test_guild_init.py` | ⚠️ |
| `/server uninit` | `test_guild_uninit.py` | ⚠️ |
| `/server uninit` DB reset | `test_hub_data_reset.py` | ✅ |
| `/server sync-join-guide` | `test_join_requests_sticky.py` | ⚠️ |
| `require_manage_guild` check | `test_require_manage_guild.py` | ✅ |
| `DeferredEphemeralResponse` | `test_deferred_ephemeral_response.py` | ✅ |

## Buttons, modals, selects

| Behavior | Tests | Coverage |
|----------|-------|----------|
| View structure / custom IDs | `test_button_command_parity.py`, `test_ui_custom_ids.py` | ✅ |
| Subscribe button success | `test_network_views_handlers.py` | ⚠️ |
| Subscribe button errors | `test_network_views_handlers.py` | ⚠️ |
| Join modal submit | `test_join_views_handlers.py`, `test_server_request_service.py` | ⚠️ |
| Moderator approve/deny handlers | `test_join_views_handlers.py`, `test_server_request_service.py` | ⚠️ |
| Create/delete network modals | `test_network_admin.py` | ⚠️ |
| Edit profile modal | `test_client_profile_edit.py` | ⚠️ |
| Blacklist select flow | `test_network_views_handlers.py` | ⚠️ |
| Delete client confirm flow | `test_client_deletion.py` | ⚠️ |
| Timecode toggle | — | 🔴 |
| Leave network button | `test_client_subscription.py` | ⚠️ |

## Network lifecycle

| Behavior | Tests | Coverage |
|----------|-------|----------|
| Key validation | `test_network_repository.py` | ✅ |
| Create/delete network | `test_network_admin.py`, `test_network_repository.py` | ✅ |
| Operator/hub permission validation | `test_network_provision.py`, `test_network_provision_operator.py` | ✅ |
| Channel validation | `test_network_validation.py` | ✅ |
| Network admin sticky | `test_network_admin_sticky.py` | ⚠️ |

## Client lifecycle

| Behavior | Tests | Coverage |
|----------|-------|----------|
| Client provision | `test_client_provision.py` | ⚠️ |
| Client reconnect on init | `test_client_reconnect.py` | ✅ |
| Permission rectification | `test_client_permission_rectification.py` | ⚠️ |
| Profile sync/post | `test_client_profile_sync.py`, `test_client_profile_post.py` | ⚠️ |
| Profile edit | `test_client_profile_edit.py` | ✅ |
| Client deletion | `test_client_deletion.py` | ⚠️ |
| Channel name allocation | `test_channel_names.py` | ⚠️ |
| Leaders channel access | `test_leaders_channel.py`, `test_client_leaders_access.py` | ⚠️ |

## Join requests

| Behavior | Tests | Coverage |
|----------|-------|----------|
| Submit request | `test_server_request_service.py` | ✅ |
| Approve/deny | `test_server_request_service.py` | ✅ |
| Moderator notification | `test_server_request_notify.py` | ✅ |
| Smoke cleanup | `test_smoke_join_request_cleanup.py` | ⚠️ |

## Subscriptions and relay

| Behavior | Tests | Coverage |
|----------|-------|----------|
| Subscribe/unsubscribe | `test_client_subscription.py`, `test_client_subscription_subscribe.py` | ✅ |
| Subscription setup state | `test_subscription_setup.py` | ✅ |
| Setup sticky sync | `test_subscription_setup.py` | ⚠️ |
| Activation welcome | `test_setup_welcome_smoke.py` | ⚠️ |
| Routing lookup | `test_routing_service.py` | ✅ |
| Relay delivery | `test_relay_service.py` | ✅ |
| Relay dedup | `test_relay_service.py` | ✅ |
| Blacklist relay block | `test_client_repository.py` | ✅ |
| Resync subscriptions | `test_client_subscription.py` | ⚠️ |

## Guild layout and permissions

| Behavior | Tests | Coverage |
|----------|-------|----------|
| Channel/category resolvers | `test_guild_layout.py` | ✅ |
| Malformed layout handling | `test_guild_init_malformed_layout.py` | ✅ |
| Overwrite builders | `test_guild_permissions.py`, `test_guild_permissions_client.py` | ✅ |
| Permission probe | `test_permission_probe.py`, `test_permission_probe_errors.py` | ✅ |
| Guild notifications | `test_guild_notifications.py` | ⚠️ |
| Discord cleanup | `test_discord_cleanup.py` | ⚠️ |
| Discord error formatting | `test_discord_errors.py` | ✅ |

## Sticky messages

| Behavior | Tests | Coverage |
|----------|-------|----------|
| Join-the-network sticky | `test_join_requests_sticky.py` | ✅ |
| Rules sticky | `test_rules_sticky.py` | ✅ |
| Network admin sticky | `test_network_admin_sticky.py` | ⚠️ |
| Subscription setup stickies | `test_subscription_setup.py` | ⚠️ |

## Hub announcements

| Behavior | Tests | Coverage |
|----------|-------|----------|
| Client/subscription setup | `test_hub_announcements.py` | ⚠️ |
| Message parsing/dispatch | `test_hub_announcements.py` | ⚠️ |
| Live smoke | `test_hub_announcements_smoke.py`, `bin/smoke_hub_announcements.sh` | 🔴 local |

## Messages and templates

| Behavior | Tests | Coverage |
|----------|-------|----------|
| Template validation | `test_message_templates.py` | ✅ |
| Template rendering flows | `test_message_templates_flows.py` | ✅ |
| Message formatter | `test_message_formatter.py` | ✅ |
| Message delivery (silent/mentions) | `test_message_delivery.py` | ✅ |
| Date parsing | `test_date_parser.py` | ✅ |

## Emoji and images

| Behavior | Tests | Coverage |
|----------|-------|----------|
| Emoji sync/degraded | `test_emoji_service.py` | ✅ |
| Image normalization | `test_image_service.py` | ⚠️ |

## Database

| Behavior | Tests | Coverage |
|----------|-------|----------|
| Migrations | `test_migrations.py` | ⚠️ |
| NetworkRepository | `test_network_repository.py` | ✅ |
| ProfileRepository (legacy) | removed — migrated to ClientRepository |
| ClientRepository | `test_client_repository.py` | ✅ |
| RelayRecordRepository | `test_relay_record_repository.py` | ✅ |
| ServerRequestRepository | `test_server_request_repository.py` | ✅ |
| SettingsRepository | `test_settings_repository.py` | ✅ |

## Changelog and config

| Behavior | Tests | Coverage |
|----------|-------|----------|
| Changelog sync | `test_changelog.py` | ⚠️ |
| Bot settings | `test_bot_settings.py` | ✅ |
| Config loading | `test_config.py` | ✅ |

## Startup and infrastructure

| Behavior | Tests | Coverage |
|----------|-------|----------|
| Bot client startup | `test_client_startup.py` | ⚠️ |
| Persistent view registration | `test_client_startup.py` | ⚠️ |
| Profile parser | `test_profile_parser.py` | ✅ |
| Discord API compat | `test_discord_api_compat.py` | ⚠️ |

## Smoke probes (live Discord required)

| Behavior | Local tests | Live script |
|----------|-------------|-------------|
| Server init probes | `test_server_init_probes.py` | `bin/smoke_server_init.sh` |
| Provision/join flow | — | `bin/smoke_provision_flow.sh` |
| Hub rebuild | `test_hub_rebuild.py` | `bin/smoke_hub_rebuild.sh` |
| Hub announcements | `test_hub_announcements_smoke.py` | `bin/smoke_hub_announcements.sh` |
| Setup welcome | `test_setup_welcome_smoke.py` | `bin/smoke_setup_welcome.sh` |
| Resource guard | `test_resource_guard.py` | — |
| Teardown | `test_smoke_teardown.py` | `bin/smoke_teardown.sh` |
| Join approval + leaders | `test_join_approval_leaders_smoke.py` | — |

---

## Test infrastructure

| Module | Purpose |
|--------|---------|
| `tests/conftest.py` | Real SQLite + migrations (`db` fixture) |
| `tests/context_helpers.py` | `make_test_context()` with real repos |
| `tests/discord_helpers.py` | Guild/role/bot mocks, HTTP 50013, channel create simulation |
| `tests/interaction_helpers.py` | Interaction, member, channel, message builders |
| `tests/repository_helpers.py` | Network/client/subscription test factories |
| `tests/subscription_helpers.py` | `make_client_subscription()` |
| `tests/request_helpers.py` | `make_server_request()` |
| `bot/testing/png_fixtures.py` | Valid probe PNG bytes |

---

## Tests overly coupled to implementation

| Test file | Coupling concern |
|-----------|------------------|
| `test_guild_init.py` | Mocks internal step ordering; brittle to refactor |
| `test_permission_probe.py` | Exercises probe step names directly |
| `test_server_init_probes.py` | Coupled to probe report structure |
| `test_network_views_handlers.py` | Monkeypatches service class methods by path |
| Smoke probe tests | Depend on Discord resource naming conventions |

---

## Priority gaps for additional characterization tests

1. ~~UI handler error paths (subscribe, join modal, moderator review, blacklist)~~ — partial coverage added in Phase 2 continuation
2. ~~`hub_announcements.py` parse/dispatch matrix~~ — dispatch tests added; live handler reply path still partial
3. ~~`guild_uninit.py` preservation/deletion truth table~~ — expanded; full uninit orchestration still partial
4. `subscription_setup_sticky.py` create vs reconcile modes — covered in `test_subscription_setup.py`
5. ~~`client_deletion.py` partial failure cleanup~~ — unsubscribe failure abort test added
6. ~~`NetworkRelayBot` startup and persistent view registration~~ — `_register_persistent_views` covered
7. Interaction response state machine (defer failure, followup failure) — partial via `ensure_sent` HTTPException test
8. ~~Permission overwrite effective access comparison tests~~ — `test_permission_effective_access.py` (hub/client/leaders truth tables)

---

*Updated with Phase 2 continuation and R1.1. 455 tests total.*

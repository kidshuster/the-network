# Behavioral Contract — The Network Discord Bot

Observable behavior inventory for behavior-preserving refactoring. Each entry documents inputs, preconditions, side effects, user-visible output, error messages, logging, failure modes, idempotency, cleanup, existing tests, and missing coverage.

**Guild model:** The **hub** is the central guild (`settings.guild_id`). **Clients** are partner communities represented by hub-side profiles, roles, and channels—not separate guilds for slash commands and UI interactions. Partner servers publish via Channel Follow into client publish channels.

---

## Table of Contents

1. [Slash commands](#1-slash-commands)
2. [Context commands, buttons, selects, modals](#2-context-commands-buttons-selects-modals)
3. [Interaction authorization](#3-interaction-authorization)
4. [Network lifecycle](#4-network-lifecycle)
5. [Client lifecycle](#5-client-lifecycle)
6. [Join requests and moderator review](#6-join-requests-and-moderator-review)
7. [Subscriptions, blacklists, routing, relay](#7-subscriptions-blacklists-routing-relay)
8. [Message formatting, templates, embeds](#8-message-formatting-templates-embeds)
9. [Guild initialization and uninitialization](#9-guild-initialization-and-uninitialization)
10. [Roles, permission overwrites, hierarchy](#10-roles-permission-overwrites-hierarchy)
11. [Sticky-message synchronization](#11-sticky-message-synchronization)
12. [Changelog](#12-changelog)
13. [Date parsing and timestamps](#13-date-parsing-and-timestamps)
14. [Emoji and image processing](#14-emoji-and-image-processing)
15. [Database layer](#15-database-layer)
16. [Cache invalidation](#16-cache-invalidation)
17. [Startup, reconnect, persistent views](#17-startup-reconnect-persistent-views)
18. [Discord API failure cleanup](#18-discord-api-failure-cleanup)
19. [Live smoke probes](#19-live-smoke-probes)

---

## 1. Slash commands

All commands are in **`ServerCog`** (`bot/cogs/servers.py`), group **`/server`**.

| Command | Auth | Guild | Response pattern | Services |
|---------|------|-------|------------------|----------|
| `/server init` | Manage Server | Hub only | defer(ephemeral) → async task → multiple followups | `initialize_guild`, optional rectification embeds |
| `/server uninit` | Hub only | defer → async → followups | `uninitialize_guild`, optional `reset_hub_layout_data` |
| `/server sync-join-guide` | Hub only | defer → sync → followup | `sync_hub_join_sticky`, `bot.add_view(JoinNetworkView)` |

**Group defaults:** `@app_commands.default_permissions(manage_guild=True)` + `@require_manage_guild()`.

### `/server init`

| Aspect | Contract |
|--------|----------|
| Preconditions | Hub guild; bot member available; operator/access roles valid |
| Discord calls | Category/channel/role create-edit-delete; sticky sync; client reconnect |
| DB | Settings keys for sticky message IDs; no schema change |
| Success output | `server_init_success` embed; optional rectification embeds |
| Stable errors | `central_guild_only`, `bot_member_unavailable`, `server_init_started` (progress) |
| Failure output | `server_init_failed` embed; `NetworkValidationError` → failed embed with reason |
| Logging | Per-step warnings on timeout (45s) or HTTP failure; `logger.exception` on unexpected |
| Idempotency | Re-run syncs existing resources by name; partial init possible with `failed_steps` |
| Cleanup | None on partial init; failed steps recorded in result notes |
| Tests | `test_guild_init.py`, `test_server_init_probes.py`, `test_guild_init_*`, smoke scripts |

### `/server uninit`

| Aspect | Contract |
|--------|----------|
| Preconditions | Bot needs Manage Channels; Manage Roles for role cleanup |
| Preserved | Community rules, `#rules`, `#leaders-channel`, `#moderator-only` |
| Deleted | Hub categories, managed channels, Moderator role, deletable hub roles |
| Success | `server_uninit_success` embed |
| Failure | `server_uninit_failed`; early exit if missing Manage Channels |
| DB reset | Optional `reset_hub_layout_data` — deletes networks, subscriptions, relay records, requests; **preserves client rows** |
| Tests | `test_guild_uninit.py`, `test_hub_data_reset.py` |

### `/server sync-join-guide`

| Aspect | Contract |
|--------|----------|
| Success | `sync_join_guide_success` embed with channel mention + message URL |
| Errors | `central_guild_only`, `bot_member_unavailable_short`, `join_channel_missing`, `sync_join_guide_failed` |
| Tests | `test_join_requests_sticky.py` |

**Relay cog** (`bot/cogs/relay.py`): no slash commands; event-driven relay and hub announcements.

---

## 2. Context commands, buttons, selects, modals

**Context commands:** none.

Custom IDs use prefix `tn:` (`bot/widgets/views/custom_ids.py`).

### Buttons

| Label | custom_id | View | Auth | Response |
|-------|-----------|------|------|----------|
| Join Network | `tn:join_network` | `JoinNetworkView` | Open | `send_modal` |
| Accept / Deny | `tn:req_approve:{id}` / `tn:req_deny:{id}` | `ModeratorReviewView` | Manage Server | defer → followup |
| Create / Delete Network | `tn:network_create` / `tn:network_delete` | `NetworkAdminView` | Manage Server | `send_modal` |
| Join `{key}` | `tn:sub:{client_id}:{key}` | `NetworkProfileView` | Client role or admin | defer → followup |
| Timecodes On/Off | `tn:timecode_toggle:{client_id}` | `NetworkProfileView` | Client role or admin | defer → followup |
| Edit Profile | `tn:profile_edit:{client_id}` | `NetworkProfileView` | Modal re-checks | `send_modal` |
| Delete Client | `tn:delete_client:{client_id}` | `NetworkProfileView` | Client role or admin | ephemeral + confirm view |
| Subscribed channel connected | `tn:sub_connected:{id}` | Setup/moderation views | Open | defer → followup |
| Blacklist | `tn:blacklist:{id}` | `SubscriptionModerationView` | Client role or admin | ephemeral + select |
| Leave `{key}` | `tn:leave:{id}` | `SubscriptionModerationView` | Client role or admin | defer → followup |

### Modals

| Modal | YAML | Trigger | Key services |
|-------|------|---------|--------------|
| `JoinNetworkModal` | `join_network` | Join button | `ServerRequestService.submit_request` |
| `CreateNetworkModal` | `create_network` | Create button | `create_network`, sticky refresh |
| `DeleteNetworkModal` | `delete_network` | Delete button | `delete_network`, sticky refresh |
| `EditClientProfileModal` | `edit_client_profile` | Edit button | `apply_client_profile_edit` |

### Select menus

| View | Auth | Behavior |
|------|------|----------|
| `BlacklistSelectView` | Inherited from Blacklist button | Multi-select up to 25; toggles `client_blacklists` rows |

### Stable user-facing messages (interaction-triggered)

| Key | Kind | Trigger |
|-----|------|---------|
| `central_guild_only` | text | Admin commands/modals outside hub |
| `hub_guild_only` | text | Join modal outside hub |
| `hub_guild_form_only` | text | Edit profile outside hub |
| `manage_guild_required` | text | Admin UI without permission |
| `bot_not_ready` | text | `bot_context` is None |
| `client_role_required_*` | text | Client-scoped action without role |
| `subscribe_success` / `subscribe_failed` | embed | Subscribe button |
| `review_success` / `review_failed` | embed | Moderator approve/deny |
| `profile_updated` / `profile_update_failed` | embed | Edit profile modal |

**Known inconsistency (preserve):** Some modal error followups omit `ephemeral=True` on `JoinNetworkModal` and `EditClientProfileModal` error paths.

**Tests:** `test_button_command_parity.py`, `test_network_views_handlers.py`, `test_ui_custom_ids.py`, `test_message_templates_flows.py`

**Missing tests:** Full handler matrix for join/admin modals, blacklist select, delete confirm flow, moderator review error paths.

---

## 3. Interaction authorization

| Tier | Rule |
|------|------|
| Manage Server | Hub admins; `/server` commands, network CRUD, join review |
| Client role | Holder of role tied to client profile; subscribe, edit, delete, leave, blacklist |
| Admin bypass | Manage Server holders may perform client-scoped actions without client role |
| Open | Join Network button/modal (any hub member) |

**Check helper:** `require_manage_guild()` in `bot/cogs/_checks.py`

| Failure | Exact message |
|---------|---------------|
| Not in guild | `This command can only be used in a server.` |
| Not Member / no manage_guild | `You need **Manage Server** permission to run admin commands.` |

Duplicate inline check in `network_admin_views._require_manage_guild` sends `manage_guild_required` popup.

**Tests:** `test_require_manage_guild.py`, `test_client_leaders_access.py`, `test_guild_permissions*.py`

---

## 4. Network lifecycle

### Validation (`network_provision.py`, `network_validation.py`)

| Error (stable) | Condition |
|----------------|-----------|
| `Access role must belong to this guild.` | Role guild mismatch |
| `Could not find access role {name!r}. Discord auto-creates **The Network**...` | Missing access role |
| Operator setup multi-line instructions | Missing/wrong operator role, hierarchy, permissions |
| `Bot cannot provision network infrastructure yet:\n• **Manage Channels**...` | Bot missing provision perms |
| `#{name} must be an announcement channel.` | Wrong channel type |
| `Missing permissions on {label}: {perms}. Run `/server init`...` | Channel permission gaps |

### Create (`network_admin.create_network`)

| Aspect | Contract |
|--------|----------|
| Duplicate key | `Network \`{key}\` already exists.` |
| Success | `network_created` embed; cache reload; subscription resync |
| Tests | `test_network_admin.py`, `test_network_provision.py`, `test_network_validation.py` |

### Delete (`network_admin.delete_network`)

| Aspect | Contract |
|--------|----------|
| Not found | `Network \`{key}\` was not found.` |
| Failure | `Network delete failed. Check bot logs.` |
| DB | Detach subscriptions, delete relay records + requests + network |
| Tests | `test_network_admin.py`, `test_network_repository.py` |

---

## 5. Client lifecycle

### Provision (`client_provision.py`, join approval)

| Error | Condition |
|-------|-----------|
| `Bot needs Manage Roles...` / `Manage Channels...` | Missing bot permissions |
| `Could not allocate a unique client role name.` | Role name exhaustion |
| Tests | `test_client_provision.py`, `test_server_request_service.py` |

### Reconnect (`client_reconnect.py`)

Per client on init: rectify permissions → sync channel names → subscription setup reconcile → reorder channels → register views → refresh profile → resync subscriptions.

| Failure | Continue other clients; note in `rectification_failures` |
| Tests | `test_client_reconnect.py`, `test_client_permission_rectification.py` |

### Profile edit (`client_profile_edit.py`)

| Error | Condition |
|-------|-----------|
| `Client profile was not found.` | Stale client_id |
| `Display name cannot be empty.` | Blank display name |
| Image validation errors from `image_service` | Invalid attachment |
| Tests | `test_client_profile_edit.py`, `test_client_profile_sync.py` |

### Deletion (`client_deletion.py`)

Flow: unsubscribe all → delete blacklists/emoji → remove role from members → delete channels/category → delete role → DB delete.

| Error | `Could not remove a network subscription.`, `Client was not found.` |
| Partial failure | Logs warnings; continues where possible |
| Tests | `test_client_deletion.py` |

---

## 6. Join requests and moderator review

### Submit (`server_request_service.submit_request`)

| Error | Condition |
|-------|-----------|
| `Name cannot be empty.` | Blank name |
| `You already have a pending join request.` | Duplicate pending |
| `A client named {name!r} already exists...` | Name collision |
| Image validation errors | Invalid/missing image |
| `Moderator #join-requests channel was not found...` | Missing channel |
| `Bot member is unavailable.` | No bot member |
| `Discord API error: {exc}` | HTTP failure |

Success: `join_request_submitted` embed; moderator message in `#join-requests` with `ModeratorReviewView`.

### Approve / Deny

| Error | Condition |
|-------|-----------|
| `Join request was not found.` | Stale ID |
| `This request was already reviewed.` | Non-pending status |
| `Client provisioning failed unexpectedly. Check bot logs.` | Unexpected provision error |

Approve: full client provision, role grant, leaders access, DM requester, edit review embed.

**Tests:** `test_server_request_service.py`, `test_server_request_notify.py`, `test_live_join_request_cleanup.py`

---

## 7. Subscriptions, blacklists, routing, relay

### Subscribe (`client_subscription.py`)

| Aspect | Contract |
|--------|----------|
| Idempotency | Returns existing subscription if present |
| Rollback | Deletes newly created channels on HTTP error during create |
| Errors | `Client role was not found.`, `Client category was not found.`, `Discord API error: {exc}` |
| Tests | `test_client_subscription*.py`, `test_subscription_setup.py` |

### Blacklist

| Aspect | Contract |
|--------|----------|
| Storage | `client_blacklists(subscription_id, blocked_client_id)` |
| Relay check | Symmetric: either party blacklisting blocks delivery |
| Idempotency | `add_blacklist` ignores duplicate IntegrityError |
| Tests | `test_client_repository.py` |

### Routing (`routing_service.py`)

| Error | `Network '{key}' was not found.` |
| Tests | `test_routing_service.py` |

### Relay (`relay_service.py`)

| Reject reason | Condition |
|---------------|-----------|
| `publish channel not registered` | Unknown publish channel |
| `network '{key}' is disabled` | Disabled network |
| `client is disabled` | Disabled client |
| Bot-not-webhook / manual relay hints | Wrong message source |
| `message has no relayable...` | Empty content |

| Aspect | Contract |
|--------|----------|
| Idempotency | Per-message lock + `relay_records.exists(message.id)` |
| Discord | Send embed to subscribe channels; `message.publish()` with 3 retries |
| DB status | PENDING → PUBLISHED / PARTIAL / FAILED_* |
| Skip | Hub announcements client as destination; blacklist |
| Tests | `test_relay_service.py`, `test_relay_record_repository.py` |

---

## 8. Message formatting, templates, embeds

### Template system (`bot/widgets/templates/` and `bot/channels/templates/`)

| Kind | Output |
|------|--------|
| embed | `discord.Embed` |
| text | `str` (popups) |
| modal | `ModalTemplateSpec` |
| relay_embed | Relay-specific config |

Rendering: `{key}` placeholders; `when:` conditional fields; named/hex colours.

Startup: `validate_all_templates()` fails fast on invalid YAML.

**Tests:** `test_message_templates.py`, `test_message_templates_flows.py`, `test_message_formatter.py`, `test_message_delivery.py`

### Relay formatting (`message_formatter.py`)

- Sanitize author, extract body, date replacement via `date_parser`
- Date parse failure: log exception, use original text (degraded)
- Tests: `test_message_formatter.py`, `test_date_parser.py`

---

## 9. Guild initialization and uninitialization

See §1 and service modules `guild_init.py`, `guild_uninit.py`.

### Init flow highlights

1. `validate_hub_permissions`
2. Smoke probes (`permission_probe`, `provision_flow`)
3. Create/sync categories, channels, roles
4. Sticky sync (rules, join, network admin)
5. Leaders channel setup
6. Hub announcements client setup
7. `reconnect_clients_on_init`
8. Register persistent views

### Permission rectification

Post-init optional embeds listing rectifications skipped/failed.

**Tests:** `test_guild_init.py`, `test_guild_layout.py`, `test_guild_permissions.py`, `test_permission_probe*.py`, `test_server_init_rectification_embed.py`

---

## 10. Roles, permission overwrites, hierarchy

### Overwrite builders (`guild_permissions.py`)

- Category, client, partner feed, moderator-only, leaders, profile channel overwrites
- `filter_configurable_overwrites` — excludes bot-member targets on channels (50013 prevention)
- Sync chain: bulk edit → sync from category → incremental `set_permissions`

| Error | `sync_channel_permission_overwrites is for non-category channels` |

**Tests:** `test_guild_permissions.py`, `test_guild_permissions_client.py`, `test_permission_probe.py`

**Requirement:** Preserve every effective allow/deny; test effective access not just overwrite dict shape.

---

## 11. Sticky-message synchronization

| Service | Channel | Settings key | Wipe? | Version |
|---------|---------|--------------|-------|---------|
| `join_requests_sticky` | `#join-the-network` | `hub_join_the_network_sticky` | Optional | v10 |
| `rules_sticky` | Community rules | `hub_rules_sticky_message` | Always | v2 |
| `network_admin_sticky` | `#commands` | `hub_network_admin_sticky` | Optional | v1 |
| `subscription_setup_sticky` | publish/subscribe | DB message IDs | No | footer markers |
| `hub_announcements` | `#network-announcements` | — | No | guide footer |

Idempotency: content signature + footer version match → edit view only, `skipped=True`.

**Tests:** `test_join_requests_sticky.py`, `test_rules_sticky.py`, `test_network_admin_sticky.py`, `test_subscription_setup.py`

---

## 12. Changelog

- Source: `bot/changelog/releases.yaml`
- Posts pending releases up to installed package version to `#changelog`
- Setting: `hub_changelog_last_version`
- Stops batch on first send failure; advances per successful post
- **Tests:** `test_changelog.py`

---

## 13. Date parsing and timestamps

- `replace_dates(text)` → Discord `<t:unix>` timestamps
- Default TZ: `America/New_York`; US timezone aliases supported
- No errors raised; unmatched patterns unchanged
- **Tests:** `test_date_parser.py`

---

## 14. Emoji and image processing

### Emoji (`emoji_service.py`)

| Degraded message | Condition |
|------------------|-----------|
| `Guild emoji limit reached; using fallback symbol.` | Limit hit |
| `Bot lacks Manage Expressions permission; using fallback symbol.` | Missing perm |
| `Emoji creation failed; using fallback symbol.` | Default fallback |

Idempotency: skip if hash unchanged and emoji exists.

**Tests:** `test_emoji_service.py`

### Images (`image_service.py`)

| Error | Condition |
|-------|-----------|
| `Profile image could not be decoded.` | Invalid bytes |
| `Profile image exceeds the {N}MB limit.` | Size limit |
| `Profile image must be a PNG, JPG, WebP, or GIF file.` | Wrong type |
| `Profile image is too large to fit Discord emoji limits.` | Emoji resize failure |

**Tests:** `test_image_service.py`, `test_client_profile_edit.py`

---

## 15. Database layer

**Schema version:** 13. **FK:** enforced. **Commits:** per statement (no explicit multi-statement transactions).

### Key constraints

| Table | Constraint |
|-------|------------|
| networks | UNIQUE(key) |
| clients | UNIQUE(guild_id, server_name) COLLATE NOCASE; UNIQUE category/profile channel |
| client_subscriptions | UNIQUE(client_id, network_key); UNIQUE publish/subscribe channel IDs |
| client_blacklists | composite PK |
| relay_records | UNIQUE(source_message_id) |
| server_requests | index on status; (requester, status) |

### Repository error mapping

| Exception | Source |
|-----------|--------|
| `NetworkValidationError` | Network key/display validation, duplicates |
| `ProfileValidationError` | Client/subscription duplicates, empty names |
| `RelayError` | Duplicate relay record |

**Tests:** `test_network_repository.py`, `test_profile_repository.py`, `test_client_repository.py`, `test_relay_record_repository.py`, `test_server_request_repository.py`, `test_settings_repository.py`, `test_migrations.py`

---

## 16. Cache invalidation

| Cache | Reload trigger |
|-------|----------------|
| `ClientCache` | After client CRUD, subscription changes, init reconnect, hub reset |
| `RoutingService` | After network CRUD, hub reset |
| Message templates | Module `_cache`; `clear_template_cache()` in tests |

**Tests:** `test_client_cache` (via service tests), `test_hub_data_reset.py`, `test_routing_service.py`

---

## 17. Startup, reconnect, persistent views

### `setup_hook` order

1. DB connect + migrations
2. Repositories + services + `BotContext`
3. Load cogs
4. `validate_all_templates()`
5. `_register_persistent_views()`
6. Copy slash commands to guild

### `on_ready` (once each)

- Slash sync (30s timeout)
- Guild visibility check
- `sync_all_subscription_setups()`
- `sync_changelog_on_ready()`

### Persistent views

Registered from DB state: pending requests, all clients, unconfirmed subscriptions.

**Not covered locally:** Full `NetworkRelayBot` startup integration (requires live Discord or heavy mocking).

**Tests:** Partial via component tests; smoke scripts for live verification.

---

## 18. Discord API failure cleanup

| Module | Behavior |
|--------|----------|
| `discord_cleanup.py` | `wipe_text_channel`, `delete_channel`, `delete_role` with fetch fallback + warnings |
| `client_subscription.py` | Rollback newly created channels on subscribe HTTP error |
| `client_deletion.py` | Continue on individual delete failures; log warnings |
| `resource_guard.py` | RAII tracking for smoke/probe artifacts |
| `teardown.py` | Remove smoke clients + orphan channels |

**Tests:** `test_discord_cleanup.py`, `test_discord_errors.py`, `test_resource_guard.py`, `test_live_teardown.py`

---

## 19. Live smoke probes

| Script | Probes |
|--------|--------|
| `tests/live/smoke_testwork.sh` | Consolidated functional suite using one gateway session |
| `tests/live/smoke_server_init.sh` | Optional repeated layout/permission burn-in |

**Resource guarantees:** `GuildTestResourceGuard` tracks and deletes webhooks, emojis, channels, categories, roles created during probes. Prefixes: `Smoke *`, `tnprobe`, `network-perm-probe`.

**Tests:** mocked probe tests live in `tests/unit`; real API code lives only in `tests/live`.

---

## Error message classification

| Class | Testing approach |
|-------|------------------|
| Stable user-facing contract | Assert exact text |
| Structured with variables | Assert complete rendered result with representative values |
| Internal diagnostic/logging | Assert severity + contextual fields |
| Incidental discord.py wording | Do not freeze unless intentionally exposed |

---

## Cross-cutting error types (`bot/domain/errors.py`)

`NetworkValidationError`, `ProfileValidationError`, `ProfileParseError`, `RoutingError`, `EmojiSyncError`, `RelayError`, `DiscordStepError`, `PermissionValidationError`, `ConfigurationError`, `ProfileSyncError`

---

*Generated as Phase 1 behavioral inventory. Update when adding characterization tests or discovering new observable behavior.*

# The Network — Traceability Matrix

## Document Status

| Field | Value |
|-------|-------|
| **Product** | The Network (*Discord Announcement Network Relay*) |
| **Status** | Traceability — implementation pass |
| **MVP requirements** | 165 (`REQ-001`–`REQ-165`) |
| **Sources** | `doc/design-spec.md`, `doc/architecture.md`, `doc/plan.md` §20–§22 |
| **Last updated** | 2026-07-17 |

### ID mapping note

Matrix rows use sequential **`REQ-NNN`** IDs required by `TraceabilityValidator` (`REQ-\d+` regex). Each maps to the prefixed design-spec ID:

| Matrix ID | Design-spec ID | Prefix family |
|-----------|----------------|---------------|
| REQ-001 | REQ-OVR-001 | Overview |
| REQ-002 | REQ-OVR-002 | Overview |
| REQ-003 | REQ-OVR-003 | Overview |
| REQ-004 | REQ-OVR-004 | Overview |
| REQ-005 | REQ-OVR-005 | Overview |
| REQ-006 | REQ-ACT-001 | Actor Types |
| REQ-007 | REQ-ACT-002 | Actor Types |
| REQ-008 | REQ-ACT-003 | Actor Types |
| REQ-009 | REQ-ACT-004 | Actor Types |
| REQ-010 | REQ-ACT-005 | Actor Types |
| REQ-011 | REQ-ACT-006 | Actor Types |
| REQ-012 | REQ-ACT-007 | Actor Types |
| REQ-013 | REQ-ACT-008 | Actor Types |
| REQ-014 | REQ-ACT-009 | Actor Types |
| REQ-015 | REQ-ACT-010 | Actor Types |
| REQ-016 | REQ-ACT-011 | Actor Types |
| REQ-017 | REQ-ACT-012 | Actor Types |
| REQ-018 | REQ-ACT-013 | Actor Types |
| REQ-019 | REQ-ACT-014 | Actor Types |
| REQ-020 | REQ-ACT-015 | Actor Types |
| REQ-021 | REQ-ACT-016 | Actor Types |
| REQ-022 | REQ-ACT-017 | Actor Types |
| REQ-023 | REQ-ITM-001 | Item Types |
| REQ-024 | REQ-ITM-002 | Item Types |
| REQ-025 | REQ-ITM-003 | Item Types |
| REQ-026 | REQ-ITM-004 | Item Types |
| REQ-027 | REQ-ITM-005 | Item Types |
| REQ-028 | REQ-ITM-006 | Item Types |
| REQ-029 | REQ-ITM-007 | Item Types |
| REQ-030 | REQ-ITM-008 | Item Types |
| REQ-031 | REQ-ITM-009 | Item Types |
| REQ-032 | REQ-ITM-010 | Item Types |
| REQ-033 | REQ-ITM-011 | Item Types |
| REQ-034 | REQ-ITM-012 | Item Types |
| REQ-035 | REQ-ITM-013 | Item Types |
| REQ-036 | REQ-ITM-014 | Item Types |
| REQ-037 | REQ-COR-001 | Core Mechanics |
| REQ-038 | REQ-COR-002 | Core Mechanics |
| REQ-039 | REQ-COR-003 | Core Mechanics |
| REQ-040 | REQ-COR-004 | Core Mechanics |
| REQ-041 | REQ-COR-005 | Core Mechanics |
| REQ-042 | REQ-COR-006 | Core Mechanics |
| REQ-043 | REQ-COR-007 | Core Mechanics |
| REQ-044 | REQ-COR-008 | Core Mechanics |
| REQ-045 | REQ-COR-009 | Core Mechanics |
| REQ-046 | REQ-COR-010 | Core Mechanics |
| REQ-047 | REQ-COR-011 | Core Mechanics |
| REQ-048 | REQ-COR-012 | Core Mechanics |
| REQ-049 | REQ-COR-013 | Core Mechanics |
| REQ-050 | REQ-COR-014 | Core Mechanics |
| REQ-051 | REQ-COR-015 | Core Mechanics |
| REQ-052 | REQ-COR-016 | Core Mechanics |
| REQ-053 | REQ-COR-017 | Core Mechanics |
| REQ-054 | REQ-COR-018 | Core Mechanics |
| REQ-055 | REQ-COR-019 | Core Mechanics |
| REQ-056 | REQ-COR-020 | Core Mechanics |
| REQ-057 | REQ-COR-021 | Core Mechanics |
| REQ-058 | REQ-COR-022 | Core Mechanics |
| REQ-059 | REQ-COR-023 | Core Mechanics |
| REQ-060 | REQ-COR-024 | Core Mechanics |
| REQ-061 | REQ-COR-025 | Core Mechanics |
| REQ-062 | REQ-COR-026 | Core Mechanics |
| REQ-063 | REQ-COR-027 | Core Mechanics |
| REQ-064 | REQ-COR-028 | Core Mechanics |
| REQ-065 | REQ-COR-029 | Core Mechanics |
| REQ-066 | REQ-COR-030 | Core Mechanics |
| REQ-067 | REQ-COR-031 | Core Mechanics |
| REQ-068 | REQ-COR-032 | Core Mechanics |
| REQ-069 | REQ-COR-033 | Core Mechanics |
| REQ-070 | REQ-COR-034 | Core Mechanics |
| REQ-071 | REQ-COR-035 | Core Mechanics |
| REQ-072 | REQ-COR-036 | Core Mechanics |
| REQ-073 | REQ-COR-037 | Core Mechanics |
| REQ-074 | REQ-REL-001 | Relay Pipeline |
| REQ-075 | REQ-REL-002 | Relay Pipeline |
| REQ-076 | REQ-REL-003 | Relay Pipeline |
| REQ-077 | REQ-REL-004 | Relay Pipeline |
| REQ-078 | REQ-REL-005 | Relay Pipeline |
| REQ-079 | REQ-REL-006 | Relay Pipeline |
| REQ-080 | REQ-REL-007 | Relay Pipeline |
| REQ-081 | REQ-REL-008 | Relay Pipeline |
| REQ-082 | REQ-REL-009 | Relay Pipeline |
| REQ-083 | REQ-REL-010 | Relay Pipeline |
| REQ-084 | REQ-REL-011 | Relay Pipeline |
| REQ-085 | REQ-REL-012 | Relay Pipeline |
| REQ-086 | REQ-REL-013 | Relay Pipeline |
| REQ-087 | REQ-REL-014 | Relay Pipeline |
| REQ-088 | REQ-REL-015 | Relay Pipeline |
| REQ-089 | REQ-REL-016 | Relay Pipeline |
| REQ-090 | REQ-REL-017 | Relay Pipeline |
| REQ-091 | REQ-REL-018 | Relay Pipeline |
| REQ-092 | REQ-REL-019 | Relay Pipeline |
| REQ-093 | REQ-REL-020 | Relay Pipeline |
| REQ-094 | REQ-REL-022 | Relay Pipeline |
| REQ-095 | REQ-REL-023 | Relay Pipeline |
| REQ-096 | REQ-REL-024 | Relay Pipeline |
| REQ-097 | REQ-REL-025 | Relay Pipeline |
| REQ-098 | REQ-REL-026 | Relay Pipeline |
| REQ-099 | REQ-REL-027 | Relay Pipeline |
| REQ-100 | REQ-REL-028 | Relay Pipeline |
| REQ-101 | REQ-REL-029 | Relay Pipeline |
| REQ-102 | REQ-REL-030 | Relay Pipeline |
| REQ-103 | REQ-REL-031 | Relay Pipeline |
| REQ-104 | REQ-REL-032 | Relay Pipeline |
| REQ-105 | REQ-REL-033 | Relay Pipeline |
| REQ-106 | REQ-REL-034 | Relay Pipeline |
| REQ-107 | REQ-REL-035 | Relay Pipeline |
| REQ-108 | REQ-REL-036 | Relay Pipeline |
| REQ-109 | REQ-REL-037 | Relay Pipeline |
| REQ-110 | REQ-REL-038 | Relay Pipeline |
| REQ-111 | REQ-ADV-001 | Advancement |
| REQ-112 | REQ-ADV-002 | Advancement |
| REQ-113 | REQ-ADV-003 | Advancement |
| REQ-114 | REQ-ADV-004 | Advancement |
| REQ-115 | REQ-ADV-005 | Advancement |
| REQ-116 | REQ-ADV-006 | Advancement |
| REQ-117 | REQ-ADV-007 | Advancement |
| REQ-118 | REQ-ADV-008 | Advancement |
| REQ-119 | REQ-ADV-009 | Advancement |
| REQ-120 | REQ-ADV-010 | Advancement |
| REQ-121 | REQ-ADV-011 | Advancement |
| REQ-122 | REQ-ADV-012 | Advancement |
| REQ-123 | REQ-ADV-013 | Advancement |
| REQ-124 | REQ-ADV-014 | Advancement |
| REQ-125 | REQ-ADV-015 | Advancement |
| REQ-126 | REQ-ADV-016 | Advancement |
| REQ-127 | REQ-PWR-001 | Power Budget |
| REQ-128 | REQ-PWR-002 | Power Budget |
| REQ-129 | REQ-PWR-003 | Power Budget |
| REQ-130 | REQ-PWR-004 | Power Budget |
| REQ-131 | REQ-PWR-005 | Power Budget |
| REQ-132 | REQ-PWR-006 | Power Budget |
| REQ-133 | REQ-PWR-007 | Power Budget |
| REQ-134 | REQ-PWR-009 | Power Budget |
| REQ-135 | REQ-PWR-010 | Power Budget |
| REQ-136 | REQ-PWR-011 | Power Budget |
| REQ-137 | REQ-PWR-012 | Power Budget |
| REQ-138 | REQ-PWR-013 | Power Budget |
| REQ-139 | REQ-PWR-014 | Power Budget |
| REQ-140 | REQ-PWR-015 | Power Budget |
| REQ-141 | REQ-UI-001 | User Interface |
| REQ-142 | REQ-UI-002 | User Interface |
| REQ-143 | REQ-UI-003 | User Interface |
| REQ-144 | REQ-UI-004 | User Interface |
| REQ-145 | REQ-UI-005 | User Interface |
| REQ-146 | REQ-UI-006 | User Interface |
| REQ-147 | REQ-UI-007 | User Interface |
| REQ-148 | REQ-UI-008 | User Interface |
| REQ-149 | REQ-UI-009 | User Interface |
| REQ-150 | REQ-UI-010 | User Interface |
| REQ-151 | REQ-UI-011 | User Interface |
| REQ-152 | REQ-UI-012 | User Interface |
| REQ-153 | REQ-UI-013 | User Interface |
| REQ-154 | REQ-UI-014 | User Interface |
| REQ-155 | REQ-UI-015 | User Interface |
| REQ-156 | REQ-UI-016 | User Interface |
| REQ-157 | REQ-UI-017 | User Interface |
| REQ-158 | REQ-UI-018 | User Interface |
| REQ-159 | REQ-UI-019 | User Interface |
| REQ-160 | REQ-UI-020 | User Interface |
| REQ-161 | REQ-UI-021 | User Interface |
| REQ-162 | REQ-UI-022 | User Interface |
| REQ-163 | REQ-UI-023 | User Interface |
| REQ-164 | REQ-UI-025 | User Interface |
| REQ-165 | REQ-UI-026 | User Interface |

## Matrix

| REQ-ID | Description | Scope | Owner | Implementation Tasks | Automated Validations |
|--------|-------------|-------|-------|----------------------|----------------------|
| REQ-001 | The bot must be installed and operate only in the single central Discord guild identified by `GUILD_ID`. | MVP | bot/client.py | Phase 1: validate GUILD_ID single-guild scope | Manual Discord: bot only responds in central guild identified by GUILD_ID |
| REQ-002 | The bot must relay followed webhook announcements from configured source channels through transformed, published mess... | MVP | bot/client.py | Phase 1: relay webhook announcements end-to-end scope | Manual Discord: followed webhook announcement relayed to output and published |
| REQ-003 | The MVP release must implement all functionality through implementation phases 1–8 as defined in `doc/plan.md` §22. | MVP | bot/client.py | Phase 1: implement phases 1-8 MVP boundary | Integration: tests/test_client.py::test_startup_sequence |
| REQ-004 | The bot must use Python 3.12+, discord.py 2.x, aiosqlite, and Pillow as the required runtime stack. | MVP | bot/config.py | Phase 1: Python 3.12+ discord.py aiosqlite Pillow stack | Unit: tests/test_config.py::test_settings_validation |
| REQ-005 | Network routes and profile data must be stored in SQLite; the bot must not require an external database for v1. | MVP | bot/db/connection.py | Phase 1: SQLite persistence no external DB | Integration: tests/test_repositories.py::test_crud_operations |
| REQ-006 | The bot must connect to Discord on startup, initialize the SQLite database, run migrations, and validate the configur... | MVP | bot/client.py | Phase 1: connect Discord init DB migrations validate guild | Integration: tests/test_client.py::test_startup_migrations_and_guild_validation |
| REQ-007 | The bot must load networks and profiles into in-memory caches after startup without automatically rebuilding every em... | MVP | bot/client.py | Phase 1: load network profile caches on startup | Integration: tests/test_client.py::test_startup_sequence |
| REQ-008 | The bot must sync application slash commands to the central guild on startup. | MVP | bot/client.py | Phase 1: sync slash commands to central guild | Integration: tests/test_client.py::test_startup_sequence |
| REQ-009 | The bot must ignore messages sent by itself to prevent self-relay loops. | MVP | bot/cogs/relay.py | Phase 1: ignore self-authored messages | Integration: tests/test_relay_service.py::test_ignore_bot_self_messages |
| REQ-010 | Each network must have exactly one output announcement channel and one feed category. | MVP | bot/db/repositories.py | Phase 2: one output channel one feed category per network | Integration: tests/test_repositories.py::test_crud_operations |
| REQ-011 | Each network must support zero or more source channels inside its feed category. | MVP | bot/db/repositories.py | Phase 2: zero or more source channels in feed category | Integration: tests/test_repositories.py::test_crud_operations |
| REQ-012 | Network routes must be persisted in the `networks` SQLite table and managed via slash commands, not hardcoded in sour... | MVP | bot/db/repositories.py | Phase 2: persist networks table manage via slash commands | Integration: tests/test_repositories.py::test_crud_operations |
| REQ-013 | A disabled network must cause the bot to ignore messages from its source channels without affecting other networks. | MVP | bot/db/repositories.py | Phase 2: disabled network ignores source messages | Integration: tests/test_repositories.py::test_crud_operations |
| REQ-014 | Each ServerProfile must correspond to exactly one forum thread and one unique source channel ID. | MVP | bot/services/profile_sync.py | Phase 3: one forum thread one source channel per profile | Integration: tests/test_profile_sync.py::test_sync_profile_success |
| REQ-015 | The source channel ID must be the authoritative identity for a participating server, not the webhook author name or d... | MVP | bot/services/profile_sync.py | Phase 3: source channel ID authoritative identity | Integration: tests/test_profile_sync.py::test_sync_profile_success |
| REQ-016 | A disabled profile must cause the bot to ignore messages from its source channel without blocking relays for other pr... | MVP | bot/services/profile_sync.py | Phase 3: disabled profile ignores source channel | Integration: tests/test_profile_sync.py::test_sync_profile_success |
| REQ-017 | Forum profile threads must be treated as configuration records, not free-form discussion threads. | MVP | bot/services/profile_sync.py | Phase 3: forum threads as configuration records | Integration: tests/test_profile_sync.py::test_sync_profile_success |
| REQ-018 | Each relayed source message must have at most one RelayRecord keyed by `source_message_id`. | MVP | bot/domain/relay_record.py | Phase 5: at most one RelayRecord per source_message_id | Integration: tests/test_client.py::test_startup_sequence |
| REQ-019 | RelayRecord status must progress through defined states: `pending`, `sent`, `published`, or failure states `failed_se... | MVP | bot/domain/relay_record.py | Phase 5: RelayRecord status lifecycle states | Integration: tests/test_client.py::test_startup_sequence |
| REQ-020 | The bot must persist runtime settings in the `settings` table with string keys and values. | MVP | bot/db/repositories.py | Phase 1: settings table key-value persistence | Integration: tests/test_repositories.py::test_crud_operations |
| REQ-021 | All administrative slash commands must require `Manage Guild` permission or a configured moderator role (moderator ro... | MVP | bot/cogs/_checks.py | Phase 1: admin commands Manage Guild or moderator role gate | Manual Discord: non-admin user denied admin slash commands |
| REQ-022 | Downstream followers must receive announcements only through Discord's published crosspost mechanism from the output ... | MVP | — | Phase 5: downstream followers via published crosspost only | Manual Discord: downstream followers receive crossposts only no bot commands |
| REQ-023 | A FollowedAnnouncementMessage must be identified by its Discord `source_message_id` and `source_channel_id`. | MVP | bot/services/relay_service.py | Phase 5: FollowedAnnouncementMessage source_message_id channel_id | Integration: tests/test_relay_service.py::test_end_to_end_webhook_relay |
| REQ-024 | By default, only webhook-delivered followed announcements (non-null `webhook_id`) must be eligible for relay unless `... | MVP | bot/services/relay_service.py | Phase 5: webhook-only unless MANUAL_RELAY_ENABLED | Integration: tests/test_relay_service.py::test_end_to_end_webhook_relay |
| REQ-025 | A RelayedMessage must include a header formatted as `**Original Username** <server emoji>` followed by preserved sour... | MVP | bot/services/message_formatter.py | Phase 5: header **Username** emoji plus content | Unit: tests/test_message_formatter.py::test_relay_header_format |
| REQ-026 | RelayedMessages must be new Discord messages (recreated), not forwards of the source message. | MVP | bot/services/relay_service.py | Phase 5: recreated messages not forwards | Unit: tests/test_message_formatter.py::test_recreated_not_forward |
| REQ-027 | Each published RelayedMessage must originate from the configured output announcement channel of the source message's ... | MVP | bot/services/routing_service.py | Phase 5: output from network announcement channel | Unit: tests/test_routing_service.py::test_resolve_route_disabled_network |
| REQ-028 | ContinuationMessages must be prefixed with `↳ continued` and linked to the same source message in the relay database. | MVP | bot/utils/text_splitter.py | Phase 6: ContinuationMessage ↳ continued prefix | Unit: tests/test_text_splitter.py::test_continued_prefix |
| REQ-029 | All ContinuationMessages for one source event must be published individually for downstream Channel Follow. | MVP | bot/services/relay_service.py | Phase 6: publish each continuation for downstream follow | Integration: tests/test_relay_service.py::test_end_to_end_webhook_relay |
| REQ-030 | ProfileImage must be sourced only from Discord-hosted attachments on the forum starter message in v1; arbitrary exter... | MVP | bot/services/image_service.py | Phase 3: ProfileImage from Discord-hosted forum starter attachment only | Unit: tests/test_image_service.py::test_normalize_png_128 |
| REQ-031 | ProfileImage must be normalized to PNG, center-cropped to square, resized to 128×128, and hashed with SHA-256 for cha... | MVP | bot/services/image_service.py | Phase 4: normalize PNG 128x128 SHA-256 hash | Unit: tests/test_image_service.py::test_normalize_png_128 |
| REQ-032 | CustomEmoji names must follow the pattern `net_<slug>_<short_channel_id>` (e.g. `net_vanguard_345678`); rendering mus... | MVP | bot/services/emoji_service.py | Phase 4: emoji name net_slug_shortid pattern | Unit: tests/test_emoji_service.py::test_emoji_name_pattern |
| REQ-033 | When emoji creation fails due to guild emoji limits, the system must use fallback symbol `◈` and record a degraded re... | MVP | bot/services/emoji_service.py | Phase 4: guild emoji limit fallback ◈ degraded reason | Unit: tests/test_emoji_service.py::test_degrade_on_guild_cap |
| REQ-034 | NetworkRoute resolution must map a source channel to its parent feed category's network output channel. | MVP | bot/services/routing_service.py | Phase 2: NetworkRoute resolution source to output channel | Unit: tests/test_routing_service.py::test_resolve_route_by_category |
| REQ-035 | AuditLogEntry must include source message ID, source channel ID, profile ID, network ID, destination channel ID, dest... | MVP | bot/services/audit_service.py | Phase 7: AuditLogEntry structured fields | Integration: tests/test_audit_service.py::test_log_relay_and_concat_mirror |
| REQ-036 | Concise human-readable audit messages must be written to the configured relay log channel (`RELAY_LOG_CHANNEL_ID`). | MVP | bot/services/audit_service.py | Phase 7: human-readable relay log channel messages | Integration: tests/test_audit_service.py::test_log_relay_and_concat_mirror |
| REQ-037 | The bot must reject duplicate relay attempts for the same `source_message_id` by checking `relay_records` before proc... | MVP | bot/services/relay_service.py | Phase 5: reject duplicate source_message_id via relay_records | Integration: tests/test_relay_service.py::test_duplicate_source_ignored |
| REQ-038 | Messages in any configured source channel must be routed to the output announcement channel associated with that chan... | MVP | bot/services/routing_service.py | Phase 2: route source channel to network output via feed category | Unit: tests/test_routing_service.py::test_source_to_output_routing |
| REQ-039 | The bot must accept followed announcements delivered by Discord Channel Follow into dedicated source channels inside ... | MVP | bot/cogs/relay.py | Phase 5: core mechanic routing safety persistence rule 3 | Manual Discord: Channel Follow delivers announcement to dedicated source channel; acceptance #2 |
| REQ-040 | The bot must recognize when an incoming message is in a configured source channel with a mapped ServerProfile. | MVP | bot/services/routing_service.py | Phase 5: core mechanic routing safety persistence rule 4 | Unit: tests/test_routing_service.py::test_resolve_route_disabled_network |
| REQ-041 | The bot must load the ServerProfile whose `source_channel_id` matches the message's channel. | MVP | bot/services/routing_service.py | Phase 5: core mechanic routing safety persistence rule 5 | Unit: tests/test_routing_service.py::test_resolve_route_disabled_network |
| REQ-042 | The bot must ignore messages outside configured feed categories. | MVP | bot/services/routing_service.py | Phase 5: core mechanic routing safety persistence rule 6 | Unit: tests/test_routing_service.py::test_resolve_route_disabled_network |
| REQ-043 | The bot must ignore messages posted in the concat channel. | MVP | bot/services/relay_service.py | Phase 5: core mechanic routing safety persistence rule 7 | Integration: tests/test_relay_service.py::test_end_to_end_webhook_relay |
| REQ-044 | The bot must ignore message updates generated by Discord after a message has already been relayed. | MVP | bot/services/relay_service.py | Phase 5: core mechanic routing safety persistence rule 8 | Integration: tests/test_relay_service.py::test_end_to_end_webhook_relay |
| REQ-045 | When `MANUAL_RELAY_ENABLED` is false, the bot must ignore non-webhook messages in source channels. | MVP | bot/services/relay_service.py | Phase 5: core mechanic routing safety persistence rule 9 | Integration: tests/test_relay_service.py::test_non_webhook_ignored_when_manual_disabled |
| REQ-046 | When `MANUAL_RELAY_ENABLED` is true, the bot must accept non-webhook messages in source channels for relay. | MVP | bot/services/relay_service.py | Phase 5: core mechanic routing safety persistence rule 10 | Integration: tests/test_relay_service.py::test_non_webhook_accepted_when_manual_enabled |
| REQ-047 | Profile forum threads must define server display name, source feed channel, enabled state, optional network override,... | MVP | bot/services/profile_parser.py | Phase 3: profile forum thread field definitions | Unit: tests/test_profile_parser.py::test_parse_profile_valid |
| REQ-048 | The profile parser must accept YAML-like key-value bodies with case-insensitive keys, ignoring blank lines and `#` co... | MVP | bot/services/profile_parser.py | Phase 3: YAML-like parser case-insensitive keys | Unit: tests/test_profile_parser.py::test_case_insensitive_keys |
| REQ-049 | The profile parser must accept source channel as raw ID or `<#channel_id>` mention format. | MVP | bot/services/profile_parser.py | Phase 3: source channel ID or mention format | Unit: tests/test_profile_parser.py::test_source_channel_mention_format |
| REQ-050 | The profile parser must fall back to thread title for `server_name` and to `server_name` for `display_name` when omit... | MVP | bot/services/profile_parser.py | Phase 3: fallback server_name display_name | Unit: tests/test_profile_parser.py::test_fallback_server_display_name |
| REQ-051 | The profile parser must resolve `network` by key or infer network from the source channel's parent category when absent. | MVP | bot/services/profile_parser.py | Phase 3: network key or category inference | Unit: tests/test_profile_parser.py::test_network_inference |
| REQ-052 | When profile parsing fails, the bot must not overwrite a previously valid profile and must reply in the forum thread ... | MVP | bot/services/profile_sync.py | Phase 3: parse failure no overwrite thread error reply | Integration: tests/test_profile_sync.py::test_sync_profile_success |
| REQ-053 | Profile synchronization must run on forum thread create, starter message edit, thread title change, attachment add/re... | MVP | bot/services/profile_sync.py | Phase 3: sync on thread create edit attachment /profile sync | Integration: tests/test_profile_sync.py::test_sync_profile_success |
| REQ-054 | The bot must use the webhook author name from the followed announcement for the relay header username. | MVP | bot/services/message_formatter.py | Phase 5: webhook author name for relay header | Unit: tests/test_message_formatter.py::test_build_relay_content |
| REQ-055 | The bot must derive source server identity from the profile mapped to the source channel, not from the webhook author... | MVP | bot/services/routing_service.py | Phase 5: server identity from profile not webhook name | Unit: tests/test_routing_service.py::test_resolve_route_disabled_network |
| REQ-056 | Invalid or failed profile sync for one server must not interrupt relay processing for other servers. | MVP | bot/services/profile_sync.py | Phase 7: core mechanic routing safety persistence rule 20 | Integration: tests/test_profile_sync.py::test_invalid_profile_does_not_block_other_relays |
| REQ-057 | The bot must acquire a per-source-message lock (`relay:<source_message_id>`) before relay processing to prevent dupli... | MVP | bot/services/relay_service.py | Phase 7: core mechanic routing safety persistence rule 21 | Integration: tests/test_relay_service.py::test_per_message_lock_prevents_concurrent_duplicate |
| REQ-058 | The bot must create a RelayRecord in `pending` state before sending the recreated message. | MVP | bot/services/relay_service.py | Phase 7: core mechanic routing safety persistence rule 22 | Integration: tests/test_relay_service.py::test_create_pending_record_before_send |
| REQ-059 | Duplicate Discord events for an already-recorded source message must be ignored at debug log level without resending. | MVP | bot/services/relay_service.py | Phase 7: core mechanic routing safety persistence rule 23 | Integration: tests/test_relay_service.py::test_duplicate_event_debug_ignored |
| REQ-060 | The bot must send relayed messages with `discord.AllowedMentions.none()` to suppress all live mentions. | MVP | bot/services/relay_service.py | Phase 5: AllowedMentions.none() on relay sends | Integration: tests/test_relay_service.py::test_allowed_mentions_none |
| REQ-061 | The bot must not relay `@everyone`, `@here`, user mentions, or role mentions as active mentions. | MVP | bot/services/relay_service.py | Phase 5: suppress @everyone @here user role mentions | Integration: tests/test_relay_service.py::test_end_to_end_webhook_relay |
| REQ-062 | The bot must sanitize the author name in the relay header to prevent mention injection. | MVP | bot/services/message_formatter.py | Phase 5: sanitize author name prevent mention injection | Unit: tests/test_message_formatter.py::test_sanitize_author_mention_injection |
| REQ-063 | The bot token must be stored only in environment variables and must never appear in logs. | MVP | bot/config.py | Phase 7: core mechanic routing safety persistence rule 27 | Unit: tests/test_config.py::test_settings_validation |
| REQ-064 | The bot must validate all Discord IDs against the central guild for admin operations. | MVP | bot/cogs/admin.py | Phase 7: core mechanic routing safety persistence rule 28 | Integration: tests/test_cogs.py::test_slash_command_handlers |
| REQ-065 | The bot must not execute content from profile messages or expose stack traces in public channels. | MVP | bot/cogs/profiles.py | Phase 7: core mechanic routing safety persistence rule 29 | Integration: tests/test_cogs.py::test_slash_command_handlers |
| REQ-066 | The bot must validate `DISCORD_TOKEN` and `GUILD_ID` at startup. | MVP | bot/config.py | Phase 1: validate DISCORD_TOKEN and GUILD_ID at startup | Unit: tests/test_config.py::test_settings_validation |
| REQ-067 | Network routes must not be hardcoded in application source files. | MVP | bot/db/repositories.py | Phase 2: no hardcoded network routes in source | Integration: tests/test_repositories.py::test_crud_operations |
| REQ-068 | Channel IDs for networks, profiles, and routes must be stored in SQLite and managed through slash commands. | MVP | bot/db/repositories.py | Phase 2: channel IDs in SQLite via slash commands | Integration: tests/test_repositories.py::test_crud_operations |
| REQ-069 | The bot must persist all network, profile, relay, and settings data in SQLite via aiosqlite. | MVP | bot/db/connection.py | Phase 1: aiosqlite persistence for all entities | Integration: tests/test_repositories.py::test_crud_operations |
| REQ-070 | Discord IDs must be stored as integers in SQLite, never inferred from channel or role names. | MVP | bot/db/models.py | Phase 1: store Discord IDs as integers in SQLite | Integration: tests/test_repositories.py::test_crud_operations |
| REQ-071 | The image pipeline must support PNG, JPEG, WEBP, and GIF formats; animated GIFs must use the first frame converted to... | MVP | bot/services/image_service.py | Phase 4: PNG JPEG WEBP GIF first-frame pipeline | Unit: tests/test_image_service.py::test_normalize_png_128 |
| REQ-072 | The image pipeline must reject SVG, undecodable files, and excessively large downloads. | MVP | bot/services/image_service.py | Phase 4: reject SVG undecodable oversized | Unit: tests/test_image_service.py::test_normalize_png_128 |
| REQ-073 | Image downloads must use timeouts and a maximum download size limit. | MVP | bot/services/image_service.py | Phase 4: download timeouts and max size limit | Unit: tests/test_image_service.py::test_normalize_png_128 |
| REQ-074 | The bot must recognize a followed webhook announcement in a configured source channel with an enabled profile and ena... | MVP | bot/services/relay_service.py | Phase 5: relay pipeline filter transform send publish step 1 | Integration: tests/test_relay_service.py::test_webhook_announcement_initiates_relay |
| REQ-075 | The bot must transform eligible messages into recreated content with header `**Original Username** <server emoji>` pl... | MVP | bot/services/message_formatter.py | Phase 5: relay pipeline filter transform send publish step 2 | Integration: tests/test_relay_service.py::test_transform_header_and_content |
| REQ-076 | The bot must send recreated message(s) to the network's configured output announcement channel. | MVP | bot/services/relay_service.py | Phase 5: relay pipeline filter transform send publish step 3 | Integration: tests/test_relay_service.py::test_send_to_output_channel |
| REQ-077 | The bot must publish each sent message in the output announcement channel via Discord's crosspost/publish action. | MVP | bot/services/relay_service.py | Phase 5: relay pipeline filter transform send publish step 4 | Integration: tests/test_relay_service.py::test_publish_after_send |
| REQ-078 | Downstream communities following the output announcement channel must receive the published announcement through Disc... | MVP | bot/services/relay_service.py | Phase 5: relay pipeline filter transform send publish step 5 | Manual Discord: downstream server receives published announcement via Channel Follow; acceptance #11 |
| REQ-079 | The bot must persist the RelayRecord with final status after send, publish, and optional audit steps complete. | MVP | bot/services/relay_service.py | Phase 5: relay pipeline filter transform send publish step 6 | Integration: tests/test_relay_service.py::test_end_to_end_webhook_relay |
| REQ-080 | Messages outside the configured guild must be ignored. | MVP | bot/cogs/relay.py | Phase 5: relay pipeline filter transform send publish step 7 | Integration: tests/test_relay_service.py::test_end_to_end_webhook_relay |
| REQ-081 | Messages in source channels without a mapped profile must be ignored. | MVP | bot/services/routing_service.py | Phase 5: relay pipeline filter transform send publish step 8 | Unit: tests/test_routing_service.py::test_resolve_route_disabled_network |
| REQ-082 | Messages for disabled profiles or disabled networks must be ignored without error propagation to other relays. | MVP | bot/services/relay_service.py | Phase 5: relay pipeline filter transform send publish step 9 | Integration: tests/test_relay_service.py::test_disabled_profile_network_ignored |
| REQ-083 | Messages already present in `relay_records` must be ignored without resending. | MVP | bot/services/relay_service.py | Phase 5: relay pipeline filter transform send publish step 10 | Integration: tests/test_relay_service.py::test_duplicate_source_ignored |
| REQ-084 | Messages from the relay bot itself must be ignored. | MVP | bot/cogs/relay.py | Phase 5: relay pipeline filter transform send publish step 11 | Integration: tests/test_relay_service.py::test_end_to_end_webhook_relay |
| REQ-085 | Non-webhook messages must be ignored when `MANUAL_RELAY_ENABLED` is false. | MVP | bot/services/relay_service.py | Phase 5: relay pipeline filter transform send publish step 12 | Integration: tests/test_relay_service.py::test_non_webhook_ignored_when_manual_disabled |
| REQ-086 | The bot must preserve message text, attachments, embeds, URLs, basic markdown, original author name, and profile emoj... | MVP | bot/services/message_formatter.py | Phase 6: media relay attachment embed sticker poll handling 13 | Unit: tests/test_message_formatter.py::test_build_relay_content |
| REQ-087 | Empty-content messages must be relayed only when attachments, embeds, stickers, or other supported content exist. | MVP | bot/services/relay_service.py | Phase 6: media relay attachment embed sticker poll handling 14 | Integration: tests/test_relay_service.py::test_end_to_end_webhook_relay |
| REQ-088 | The bot must download and re-upload attachments to the destination message, preserving original filenames when safe. | MVP | bot/services/attachment_service.py | Phase 6: media relay attachment embed sticker poll handling 15 | Integration: tests/test_attachment_service.py::test_prepare_attachments_size_limit |
| REQ-089 | The bot must copy up to Discord's embed limit, preserving titles, descriptions, fields, footer text, and image/thumbn... | MVP | bot/services/relay_service.py | Phase 6: media relay attachment embed sticker poll handling 16 | Integration: tests/test_relay_service.py::test_end_to_end_webhook_relay |
| REQ-090 | When an embed cannot be sent, the bot must fall back to a plain-text summary rather than failing the entire relay. | MVP | bot/services/relay_service.py | Phase 6: media relay attachment embed sticker poll handling 17 | Integration: tests/test_relay_service.py::test_end_to_end_webhook_relay |
| REQ-091 | Stickers must be appended as plain text with name and URL when available. | MVP | bot/services/relay_service.py | Phase 6: media relay attachment embed sticker poll handling 18 | Integration: tests/test_relay_service.py::test_end_to_end_webhook_relay |
| REQ-092 | Polls must be appended as a plain-text summary when available. | MVP | bot/services/relay_service.py | Phase 6: media relay attachment embed sticker poll handling 19 | Integration: tests/test_relay_service.py::test_end_to_end_webhook_relay |
| REQ-093 | Interactive components (buttons, menus) must not be recreated on relayed messages. | MVP | bot/services/relay_service.py | Phase 6: media relay attachment embed sticker poll handling 20 | Integration: tests/test_relay_service.py::test_end_to_end_webhook_relay |
| REQ-094 | The bot must avoid copying Discord-generated embeds that duplicate a URL already present in message content when doin... | MVP | bot/services/relay_service.py | Phase 6: media relay attachment embed sticker poll handling 22 | Integration: tests/test_relay_service.py::test_end_to_end_webhook_relay |
| REQ-095 | The bot must verify the destination channel is an announcement channel before sending. | MVP | bot/services/relay_service.py | Phase 5: relay pipeline filter transform send publish step 23 | Integration: tests/test_relay_service.py::test_end_to_end_webhook_relay |
| REQ-096 | The bot must retry transient publish failures (rate limits, temporary network errors, Discord server errors) with exp... | MVP | bot/utils/retry.py | Phase 8: retry transient publish failures exponential backoff | Unit: tests/test_retry.py::test_exponential_backoff_max_three |
| REQ-097 | The bot must not retry permanent permission failures, invalid channel types, or deleted channels indefinitely. | MVP | bot/utils/retry.py | Phase 8: no retry permanent permission channel errors | Unit: tests/test_retry.py::test_exponential_backoff_max_three |
| REQ-098 | Publish failures must be logged to structured logs and the relay log channel. | MVP | bot/services/audit_service.py | Phase 5: relay pipeline filter transform send publish step 26 | Integration: tests/test_audit_service.py::test_log_relay_and_concat_mirror |
| REQ-099 | The bot must hold appropriate permissions in the output channel: view, send messages, embed links, attach files, and ... | MVP | bot/cogs/admin.py | Phase 5: relay pipeline filter transform send publish step 27 | Integration: tests/test_cogs.py::test_slash_command_handlers |
| REQ-100 | The bot must not silently truncate transformed content that exceeds Discord's message length limit. | MVP | bot/utils/text_splitter.py | Phase 6: no silent truncation on length overflow | Unit: tests/test_text_splitter.py::test_split_content_paragraphs |
| REQ-101 | When content exceeds the limit, the bot must send the header in the first message and split remaining content at para... | MVP | bot/utils/text_splitter.py | Phase 6: split at paragraph newline into continuations | Unit: tests/test_text_splitter.py::test_split_content_paragraphs |
| REQ-102 | Attachments must remain on the first message unless Discord upload constraints require distribution across continuati... | MVP | bot/services/attachment_service.py | Phase 6: attachments on first message unless upload constraints | Integration: tests/test_attachment_service.py::test_prepare_attachments_size_limit |
| REQ-103 | When combined attachment size exceeds Discord limits, the bot must distribute attachments across continuation message... | MVP | bot/services/attachment_service.py | Phase 6: distribute oversized attachments across continuations | Integration: tests/test_attachment_service.py::test_prepare_attachments_size_limit |
| REQ-104 | When a concat channel is configured, the bot must write a plain-text audit copy of what was sent to the output channel. | MVP | bot/services/audit_service.py | Phase 7: audit concat logging failure states step 32 | Integration: tests/test_audit_service.py::test_log_relay_and_concat_mirror |
| REQ-105 | The concat channel must function as an audit stream only; the bot must not treat concat as a second event-driven rela... | MVP | bot/services/audit_service.py | Phase 7: audit concat logging failure states step 33 | Integration: tests/test_audit_service.py::test_log_relay_and_concat_mirror |
| REQ-106 | Production relay must use direct mode (source → transform → output → publish); concat mirroring must not trigger a se... | MVP | bot/services/audit_service.py | Phase 7: audit concat logging failure states step 34 | Integration: tests/test_audit_service.py::test_log_relay_and_concat_mirror |
| REQ-107 | Relay failures must set RelayRecord status to `failed_send`, `failed_publish`, or `partial` as appropriate. | MVP | bot/services/relay_service.py | Phase 7: audit concat logging failure states step 35 | Integration: tests/test_relay_service.py::test_failed_publish_status |
| REQ-108 | Structured relay log entries must include event name, source message ID, channel IDs, profile ID, network ID, destina... | MVP | bot/services/audit_service.py | Phase 7: audit concat logging failure states step 36 | Integration: tests/test_audit_service.py::test_log_relay_and_concat_mirror |
| REQ-109 | Source message edits in v1 must not automatically edit published relay messages; the bot must log that the source was... | MVP | bot/cogs/relay.py | Phase 7: audit concat logging failure states step 37 | Integration: tests/test_relay_service.py::test_end_to_end_webhook_relay |
| REQ-110 | Source message deletions in v1 must not automatically delete published announcements; the bot must log the deletion a... | MVP | bot/cogs/relay.py | Phase 7: audit concat logging failure states step 38 | Integration: tests/test_relay_service.py::test_end_to_end_webhook_relay |
| REQ-111 | On profile sync, the bot must parse the forum thread, validate the source channel, resolve the network, normalize the... | MVP | bot/services/profile_sync.py | Phase 3: profile sync parse validate emoji save report warnings | Integration: tests/test_profile_sync.py::test_sync_profile_success |
| REQ-112 | `/profile sync-all` must enumerate all threads in the configured profile forum and synchronize each, returning a summ... | MVP | bot/cogs/profiles.py | Phase 3: /profile sync-all enumerate forum threads | Integration: tests/test_cogs.py::test_slash_command_handlers |
| REQ-113 | When a profile image hash changes, the bot must create a new custom emoji before updating the stored profile record. | MVP | bot/services/emoji_service.py | Phase 4: create new emoji before profile update on hash change | Unit: tests/test_emoji_service.py::test_hash_change_creates_new_emoji |
| REQ-114 | The bot must delete the old custom emoji only after the replacement emoji is successfully created and persisted. | MVP | bot/services/emoji_service.py | Phase 4: delete old emoji after successful replace | Unit: tests/test_emoji_service.py::test_create_before_delete_order |
| REQ-115 | When the profile image hash is unchanged, the bot must skip emoji recreation. | MVP | bot/services/emoji_service.py | Phase 4: skip emoji recreation when hash unchanged | Unit: tests/test_emoji_service.py::test_skip_recreation_unchanged_hash |
| REQ-116 | When a profile is deleted or disabled, the bot must retain the associated emoji by default. | MVP | bot/services/emoji_service.py | Phase 4: retain emoji on profile delete disable | Unit: tests/test_emoji_service.py::test_degrade_on_guild_cap |
| REQ-117 | `/profile repair-emoji` must attempt to recreate a missing emoji for a profile when explicitly invoked. | MVP | bot/cogs/profiles.py | Phase 4: /profile repair-emoji recreate missing | Integration: tests/test_cogs.py::test_slash_command_handlers |
| REQ-118 | Emoji creation failure due to guild limits must mark the profile degraded with reason and use `◈` fallback without bl... | MVP | bot/services/emoji_service.py | Phase 4: emoji limit degrade ◈ fallback | Unit: tests/test_emoji_service.py::test_degrade_on_guild_cap |
| REQ-119 | The bot must update RelayRecord status from `pending` to `sent` after successful send and to `published` after succes... | MVP | bot/services/relay_service.py | Phase 7: RelayRecord pending to sent to published | Integration: tests/test_relay_service.py::test_status_pending_sent_published |
| REQ-120 | Relay failures must be logged with sufficient context for administrators to diagnose the issue within minutes. | MVP | bot/services/audit_service.py | Phase 7: log relay failures with diagnostic context | Integration: tests/test_audit_service.py::test_log_relay_and_concat_mirror |
| REQ-121 | `/relay retry` must attempt recovery of incomplete or failed relays without creating duplicate downstream published m... | MVP | bot/cogs/relay.py | Phase 7: /relay retry recovery without duplicate publish | Integration: tests/test_relay_service.py::test_retry_without_duplicate_publish |
| REQ-122 | `/relay recent` must list recent relay activity for administrator inspection. | MVP | bot/cogs/relay.py | Phase 7: /relay recent list activity | Integration: tests/test_relay_service.py::test_end_to_end_webhook_relay |
| REQ-123 | `/relay status` must report relay status for a specified source message or recent activity. | MVP | bot/cogs/relay.py | Phase 7: /relay status query by source message | Integration: tests/test_relay_service.py::test_end_to_end_webhook_relay |
| REQ-124 | `/maintenance rebuild-cache` must reload networks and profiles into in-memory caches from SQLite. | MVP | bot/cogs/admin.py | Phase 7: /maintenance rebuild-cache reload caches | Integration: tests/test_cogs.py::test_slash_command_handlers |
| REQ-125 | `/maintenance validate` must check configuration consistency and report issues. | MVP | bot/cogs/admin.py | Phase 7: /maintenance validate configuration consistency | Integration: tests/test_cogs.py::test_slash_command_handlers |
| REQ-126 | Startup must validate channel permissions and log startup status without rebuilding all emojis automatically. | MVP | bot/client.py | Phase 1: startup permission validation log status no emoji rebuild | Manual Discord: bot restart in test guild; /status reports permission warnings |
| REQ-127 | Transformed message content must respect Discord's per-message character limit; overflow must trigger continuation sp... | MVP | bot/utils/text_splitter.py | Phase 6: character limit triggers continuation not truncation | Unit: tests/test_text_splitter.py::test_no_silent_truncation |
| REQ-128 | Continuation messages must use the `↳ continued` prefix to signal split content to readers. | MVP | bot/utils/text_splitter.py | Phase 6: ↳ continued prefix on continuation messages | Unit: tests/test_text_splitter.py::test_continued_prefix |
| REQ-129 | Attachment downloads must enforce a maximum file size and timeout; oversized or timed-out attachments must be skipped... | MVP | bot/services/attachment_service.py | Phase 6: attachment download size timeout skip with audit | Integration: tests/test_attachment_service.py::test_prepare_attachments_size_limit |
| REQ-130 | The bot must not persist attachment bytes to disk longer than necessary; in-memory buffers are preferred. | MVP | bot/services/attachment_service.py | Phase 6: in-memory attachment buffers no disk persist | Integration: tests/test_attachment_service.py::test_prepare_attachments_size_limit |
| REQ-131 | Embed copying must respect Discord's embed count and field limits per message. | MVP | bot/services/relay_service.py | Phase 6: embed count field limits per message | Integration: tests/test_relay_service.py::test_end_to_end_webhook_relay |
| REQ-132 | When the central guild reaches its custom emoji limit, the bot must degrade gracefully with `◈` fallback rather than ... | MVP | bot/services/emoji_service.py | Phase 4: graceful ◈ fallback at guild emoji cap | Unit: tests/test_emoji_service.py::test_degrade_on_guild_cap |
| REQ-133 | `/maintenance cleanup-emojis` must provide administrative cleanup of unused emojis; exact "unused" criteria are TBD (... | MVP | bot/services/emoji_service.py | Phase 8: /maintenance cleanup-emojis unused criteria TBD | Unit: tests/test_emoji_service.py::test_degrade_on_guild_cap |
| REQ-134 | The bot must retry transient Discord API errors with exponential backoff and jitter. | MVP | bot/utils/retry.py | Phase 8: retry transient Discord API errors backoff jitter | Unit: tests/test_retry.py::test_exponential_backoff_max_three |
| REQ-135 | Maximum automatic retries for transient failures must be 3. | MVP | bot/utils/retry.py | Phase 8: max 3 automatic retries transient failures | Unit: tests/test_retry.py::test_exponential_backoff_max_three |
| REQ-136 | The bot must not retry missing permissions, invalid channel types, deleted channels, invalid profiles, or emoji capac... | MVP | bot/utils/retry.py | Phase 8: no retry missing permissions invalid channel emoji cap | Unit: tests/test_retry.py::test_exponential_backoff_max_three |
| REQ-137 | The bot must operate in exactly one central guild in v1. | MVP | bot/client.py | Phase 8: single central guild v1 scope | Integration: tests/test_client.py::test_startup_sequence |
| REQ-138 | The bot must run as a single process without persistent job queues or horizontal scaling in v1. | MVP | bot/main.py | Phase 8: single process no job queues | Integration: tests/test_client.py::test_startup_sequence |
| REQ-139 | SQLite must be the sole database for v1; no external database connections are permitted. | MVP | bot/db/connection.py | Phase 8: SQLite sole database no external connections | Integration: tests/test_repositories.py::test_crud_operations |
| REQ-140 | Docker deployment support is optional but recommended for phase 8 hardening. | MVP | Dockerfile | Phase 8: Docker deployment support phase 8 hardening | Manual Discord: Docker build and container startup smoke test |
| REQ-141 | `/network create` must accept `key`, `display_name`, `feed_category`, `output_channel`, and optional `concat_channel`... | MVP | bot/cogs/admin.py | Phase 2: /network create parameters | Integration: tests/test_cogs.py::test_slash_command_handlers |
| REQ-142 | `/network create` must validate that the feed category belongs to the central guild and the output channel is an anno... | MVP | bot/cogs/admin.py | Phase 2: validate feed category and announcement channel | Integration: tests/test_cogs.py::test_slash_command_handlers |
| REQ-143 | `/network create` must validate that the concat channel, when provided, is a text channel and the bot has required pe... | MVP | bot/cogs/admin.py | Phase 2: validate concat channel permissions | Integration: tests/test_cogs.py::test_slash_command_handlers |
| REQ-144 | `/network list` must display all configured networks with their key, display name, and enabled state. | MVP | bot/cogs/admin.py | Phase 2: /network list display | Integration: tests/test_cogs.py::test_slash_command_handlers |
| REQ-145 | `/network disable` and `/network enable` must toggle network enabled state without deleting configuration. | MVP | bot/cogs/admin.py | Phase 2: /network disable enable toggle | Integration: tests/test_cogs.py::test_slash_command_handlers |
| REQ-146 | `/network validate` must check network configuration consistency and report errors. | MVP | bot/cogs/admin.py | Phase 2: /network validate consistency | Integration: tests/test_cogs.py::test_slash_command_handlers |
| REQ-147 | `/network delete` must remove a network record from the database. | MVP | bot/cogs/admin.py | Phase 2: /network delete remove record | Integration: tests/test_cogs.py::test_slash_command_handlers |
| REQ-148 | `/profile sync` must accept a `profile_thread` parameter and perform full parse, validate, emoji sync, and save. | MVP | bot/cogs/profiles.py | Phase 3: /profile sync full parse validate emoji save | Integration: tests/test_cogs.py::test_slash_command_handlers |
| REQ-149 | `/profile show` must display the stored profile fields including source channel, network, emoji state, and degraded r... | MVP | bot/cogs/profiles.py | Phase 3: /profile show stored fields | Integration: tests/test_cogs.py::test_slash_command_handlers |
| REQ-150 | `/profile disable` and `/profile enable` must toggle profile relay eligibility. | MVP | bot/cogs/profiles.py | Phase 3: /profile disable enable toggle | Integration: tests/test_cogs.py::test_slash_command_handlers |
| REQ-151 | `/profile delete` must remove the profile record; emoji retention policy applies per REQ-ADV-006. | MVP | bot/cogs/profiles.py | Phase 3: /profile delete remove record emoji retained | Integration: tests/test_cogs.py::test_slash_command_handlers |
| REQ-152 | `/relay test` must accept `source_channel` and `text` parameters, simulate message transformation, and send a test me... | MVP | bot/cogs/relay.py | Phase 5: /relay test simulate transform optional send | Integration: tests/test_relay_service.py::test_end_to_end_webhook_relay |
| REQ-153 | `/relay test` must not publish the test message unless `publish=true` is specified. | MVP | bot/cogs/relay.py | Phase 5: /relay test no publish unless flag | Integration: tests/test_relay_service.py::test_end_to_end_webhook_relay |
| REQ-154 | `/relay retry` must reattempt send and/or publish for a failed relay record. | MVP | bot/cogs/relay.py | Phase 5: /relay retry reattempt failed relay | Integration: tests/test_relay_service.py::test_end_to_end_webhook_relay |
| REQ-155 | `/relay recent` must list recent relay records with status and error summary. | MVP | bot/cogs/relay.py | Phase 7: /relay recent status error summary | Integration: tests/test_relay_service.py::test_end_to_end_webhook_relay |
| REQ-156 | `/maintenance permissions` must validate bot permissions for profile forum, feed source channels, concat channel, out... | MVP | bot/cogs/admin.py | Phase 7: /maintenance permissions validate bot perms | Integration: tests/test_cogs.py::test_slash_command_handlers |
| REQ-157 | `/maintenance rebuild-cache` must reload network and profile caches from SQLite. | MVP | bot/cogs/admin.py | Phase 7: /maintenance rebuild-cache reload from SQLite | Integration: tests/test_cogs.py::test_slash_command_handlers |
| REQ-158 | `/maintenance cleanup-emojis` must provide administrative emoji cleanup per TBD unused criteria. | MVP | bot/cogs/admin.py | Phase 7: /maintenance cleanup-emojis admin cleanup | Integration: tests/test_cogs.py::test_slash_command_handlers |
| REQ-159 | `/status` must report bot connectivity, guild validation, database status, and loaded network/profile counts. | MVP | bot/cogs/admin.py | Phase 1: /status connectivity guild DB cache counts | Integration: tests/test_cogs.py::test_slash_command_handlers |
| REQ-160 | Forum profile threads must use structured key-value configuration in the starter message body as the authoritative pr... | MVP | bot/services/profile_parser.py | Phase 3: forum starter body structured key-value config | Unit: tests/test_profile_parser.py::test_parse_profile_valid |
| REQ-161 | The first valid image attached to the forum starter message must be used as the profile image for emoji generation. | MVP | bot/services/image_service.py | Phase 3: first valid starter image for emoji | Unit: tests/test_image_service.py::test_normalize_png_128 |
| REQ-162 | Profile parse errors must be reported in the forum thread and logged in full to the relay log channel. | MVP | bot/services/profile_sync.py | Phase 3: parse errors in thread and relay log channel | Integration: tests/test_profile_sync.py::test_sync_profile_success |
| REQ-163 | The relay log channel must receive concise human-readable messages for relay completions, failures, profile sync resu... | MVP | bot/services/audit_service.py | Phase 7: relay log channel concise human-readable events | Integration: tests/test_audit_service.py::test_log_relay_and_concat_mirror |
| REQ-164 | The bot must validate permissions at startup and via `/maintenance permissions` using permission names from the insta... | MVP | bot/cogs/admin.py | Phase 7: validate permissions at startup and /maintenance permissions | Manual Discord: startup and /maintenance permissions validate discord.py permission flags |
| REQ-165 | All `/network`, `/profile`, `/relay`, and `/maintenance` commands must be restricted to users with `Manage Guild` or ... | MVP | bot/cogs/_checks.py | Phase 1: restrict admin commands to Manage Guild or moderator role | Manual Discord: Manage Guild or moderator role required for /network /profile /relay /maintenance |

## Acceptance criteria cross-reference

| # | Criterion | Matrix REQ-ID(s) | Design-spec REQ-ID(s) | Validation |
|---|-----------|------------------|----------------------|------------|
| 1 | External announcement published | REQ-074 | REQ-REL-001 | Integration: tests/test_relay_service.py::test_webhook_announcement_initiates_relay |
| 2 | Discord delivers to dedicated source channel | REQ-039 | REQ-COR-003 | Manual Discord: Channel Follow delivers to source channel; acceptance #2 |
| 3 | Bot recognizes source channel | REQ-040 | REQ-COR-004 | Unit: tests/test_routing_service.py::test_resolve_route_by_category |
| 4 | Bot loads correct server profile | REQ-041 | REQ-COR-005 | Unit: tests/test_routing_service.py::test_resolve_route_by_category |
| 5 | Header format plus content | REQ-075 | REQ-REL-002 | Unit: tests/test_message_formatter.py::test_relay_header_format |
| 6 | Attachments copied | REQ-088 | REQ-REL-015 | Integration: tests/test_attachment_service.py::test_prepare_attachments_size_limit |
| 7 | Supported embeds copied | REQ-089 | REQ-REL-016 | Integration: tests/test_relay_service.py::test_embed_copy_limit |
| 8 | Live mentions suppressed | REQ-060, REQ-061 | REQ-COR-024, REQ-COR-025 | Integration: tests/test_relay_service.py::test_allowed_mentions_none |
| 9 | Recreated message sent to output channel | REQ-076 | REQ-REL-003 | Integration: tests/test_relay_service.py::test_send_to_output_channel |
| 10 | Recreated message published | REQ-077 | REQ-REL-004 | Integration: tests/test_relay_service.py::test_publish_after_send |
| 11 | Receiving server obtains published announcement | REQ-078 | REQ-REL-005 | Manual Discord: downstream server receives via Channel Follow; acceptance #11 |
| 12 | Duplicate source events no duplicate messages | REQ-037 | REQ-COR-001 | Integration: tests/test_relay_service.py::test_duplicate_source_ignored |
| 13 | Profile image update creates new emoji | REQ-113 | REQ-ADV-003 | Unit: tests/test_emoji_service.py::test_hash_change_creates_new_emoji |
| 14 | Old emoji deleted only after successful replacement | REQ-114 | REQ-ADV-004 | Unit: tests/test_emoji_service.py::test_create_before_delete_order |
| 15 | Invalid profiles do not interrupt other relays | REQ-056 | REQ-COR-020 | Integration: tests/test_profile_sync.py::test_invalid_profile_does_not_block_other_relays |
| 16 | Relay failures logged and retriable | REQ-120, REQ-121 | REQ-ADV-010, REQ-ADV-011 | Integration: tests/test_relay_service.py::test_retry_without_duplicate_publish |

## Coverage summary

- **MVP rows:** 165
- **Validation — Unit:** 47 (28%)
- **Validation — Integration:** 108 (65%)
- **Validation — Manual Discord:** 10 (6%)
- **Automated (Unit + Integration):** 155 (94%)

**By implementation phase:**
- Phase 1: 17 requirements
- Phase 2: 15 requirements
- Phase 3: 21 requirements
- Phase 4: 13 requirements
- Phase 5: 40 requirements
- Phase 6: 20 requirements
- Phase 7: 29 requirements
- Phase 8: 10 requirements

## Deferred requirements (non-MVP)

| REQ-ID | Description | Scope | Owner | Implementation Tasks | Automated Validations |
|--------|-------------|-------|-------|----------------------|----------------------|
| REQ-REL-021 | Reply references may optionally include a short quoted reply; default v1 behavior is TBD (see Open Questions). | post-MVP | deferred | post-MVP: deferred beyond phases 1–8 | Manual Discord: deferred feature validation TBD |
| REQ-ADV-017 | `/relay refresh <message_link>` for edit synchronization is deferred beyond v1. | post-MVP | deferred | post-MVP: deferred beyond phases 1–8 | Manual Discord: deferred feature validation TBD |
| REQ-PWR-008 | Proactive emoji budget guidance before deployment is not defined in v1. | post-MVP | deferred | post-MVP: deferred beyond phases 1–8 | Manual Discord: deferred feature validation TBD |
| REQ-UI-024 | Structured JSON logging should be supported for operational monitoring. | post-MVP | deferred | post-MVP: deferred beyond phases 1–8 | Manual Discord: deferred feature validation TBD |
| REQ-OOS-001 | Automatic synchronization of source message edits to already-published relay messages must not be implemented in v1. | out-of-scope | — | out-of-scope: not planned for v1 | Manual Discord: out-of-scope verification N/A |
| REQ-OOS-002 | Automatic deletion of relayed messages when source messages are deleted must not be implemented in v1. | out-of-scope | — | out-of-scope: not planned for v1 | Manual Discord: out-of-scope verification N/A |
| REQ-OOS-003 | Multiple central guilds must not be supported in v1; the bot operates in one guild only. | out-of-scope | — | out-of-scope: not planned for v1 | Manual Discord: out-of-scope verification N/A |
| REQ-OOS-004 | A web dashboard or external admin UI must not be included in v1. | out-of-scope | — | out-of-scope: not planned for v1 | Manual Discord: out-of-scope verification N/A |
| REQ-OOS-005 | Arbitrary external image URLs for profile images must not be accepted in v1; only Discord-hosted attachments are supp... | out-of-scope | — | out-of-scope: not planned for v1 | Manual Discord: out-of-scope verification N/A |
| REQ-OOS-006 | Interactive component recreation (buttons, select menus, etc.) must not be implemented in v1. | out-of-scope | — | out-of-scope: not planned for v1 | Manual Discord: out-of-scope verification N/A |
| REQ-OOS-007 | Per-message moderator approval before relay must not be implemented in v1. | out-of-scope | — | out-of-scope: not planned for v1 | Manual Discord: out-of-scope verification N/A |
| REQ-OOS-008 | Cross-network message fan-out from a single source event must not be implemented in v1. | out-of-scope | — | out-of-scope: not planned for v1 | Manual Discord: out-of-scope verification N/A |
| REQ-OOS-009 | Per-server filtering rules beyond configured routing and ignore rules must not be implemented in v1. | out-of-scope | — | out-of-scope: not planned for v1 | Manual Discord: out-of-scope verification N/A |
| REQ-OOS-010 | Persistent job queues or background workers beyond the single bot process must not be implemented in v1. | out-of-scope | — | out-of-scope: not planned for v1 | Manual Discord: out-of-scope verification N/A |
| REQ-OOS-011 | External database systems must not replace SQLite in v1. | out-of-scope | — | out-of-scope: not planned for v1 | Manual Discord: out-of-scope verification N/A |
| REQ-OOS-012 | Horizontal scaling or multi-instance deployment must not be supported in v1. | out-of-scope | — | out-of-scope: not planned for v1 | Manual Discord: out-of-scope verification N/A |

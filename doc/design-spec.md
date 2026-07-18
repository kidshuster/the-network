# The Network — Design Specification

## Document Status

| Field | Value |
|-------|-------|
| **Product** | The Network (*Discord Announcement Network Relay*) |
| **Status** | Draft — spec phase |
| **MVP boundary** | Implementation phases 1–8 (`doc/plan.md` §22) |
| **Sources** | `doc/product-brief.md`, `doc/intake-summary.md`, `doc/plan.md` |
| **Naming note** | Section headings `Combat System` et al. are coordinator template labels; content describes the Discord relay bot only. |

This document specifies *what* The Network must do. Implementation structure, class names, and file layout belong to the architecture phase; see `doc/plan.md` §4 for reference only.

---

## Overview

The Network is a Python discord.py bot installed in a single central Discord guild. Partner communities publish announcements on their own servers; Discord delivers those posts into dedicated feed channels via Channel Follow. The bot listens for webhook-delivered followed announcements in configured source channels, loads the ServerProfile mapped to each source channel, transforms content with author attribution and a server-specific custom emoji, sends recreated message(s) to a network output announcement channel, publishes them for downstream Channel Follow, optionally mirrors a plain-text audit copy to a concat channel, and persists RelayRecords for idempotency and admin recovery.

### End-to-end relay workflow

```text
External server announcement channel
    -> Discord Channel Follow
    -> Dedicated source channel inside a feed category
    -> Bot transforms the message
    -> Optional concat/audit channel (mirror only)
    -> Network announcement channel
    -> Bot publishes the message
    -> Other servers receive it through Discord Channel Following
```

Example:

```text
External Server A #announcements
    -> Central Server / Stingers Feed / #server-a
    -> Bot
    -> **Original Username** <Server A Emoji>
       Original message
    -> Central Server / The Network / #stingers
    -> Published announcement
    -> Downstream servers following #stingers receive the update
```

### Technology stack

| Component | Requirement |
|-----------|-------------|
| Runtime | Python 3.12 or newer |
| Discord API | discord.py 2.x |
| Database | aiosqlite (SQLite) |
| Images | Pillow |
| Configuration | pydantic-settings, python-dotenv (local dev) |
| Quality | pytest, pytest-asyncio, ruff, mypy |
| Optional | Docker, structured JSON logging, Sentry |

The bot shall run as a single process in one central guild; SQLite is sufficient for v1 message volume. [MVP]

### MVP implementation phases

| Phase | Focus | Deliverable |
|-------|-------|-------------|
| 1 — Bootstrap | Project setup, bot connection, SQLite, logging, slash sync | Bot starts, connects, initializes DB, responds to `/status` |
| 2 — Network routing | Network persistence, create/list, validation, route cache | Bot maps feed category to output announcement channel |
| 3 — Profiles | Forum profile parser, sync, storage, source-channel mapping | Forum thread configures one source server profile |
| 4 — Emoji sync | Image download, normalize, hash, custom emoji create/replace, fallback | Each profile owns server-specific emoji from its image |
| 5 — Basic relay | Feed listener, webhook filter, formatter, mention suppression, send, publish, records | Plain-text followed announcements relay end to end |
| 6 — Media support | Attachments, embeds, empty-content media, text splitting, continuations | Typical Discord announcements retain useful media |
| 7 — Audit & recovery | Concat mirror, relay log, recent/retry, permission validation, cache rebuild | Administrators diagnose and recover failed relays |
| 8 — Hardening | Full tests, Docker, rate-limit retries, cleanup commands, docs, SQLite backup | Bot ready for long-running deployment |

Phases 1–8 define the MVP release boundary. Requirements tagged `[MVP]` trace to this table and the acceptance checklist below.

### Acceptance criteria traceability

The first release is complete when all acceptance criteria from `doc/plan.md` §21 are satisfied. Each maps to tagged requirements in this spec:

| # | Criterion | Primary REQ IDs |
|---|-----------|-----------------|
| 1 | External announcement published | REQ-REL-001 |
| 2 | Discord delivers to dedicated source channel | REQ-COR-003 |
| 3 | Bot recognizes source channel | REQ-COR-004 |
| 4 | Bot loads correct server profile | REQ-COR-005 |
| 5 | Header format `**Original Username** <server emoji>` plus content | REQ-REL-002 |
| 6 | Attachments copied | REQ-REL-015 |
| 7 | Supported embeds copied | REQ-REL-016 |
| 8 | Live mentions suppressed | REQ-COR-024, REQ-COR-025 |
| 9 | Recreated message sent to output announcement channel | REQ-REL-003 |
| 10 | Recreated message published | REQ-REL-004 |
| 11 | Receiving server obtains published announcement | REQ-REL-005 |
| 12 | Duplicate source events do not create duplicate messages | REQ-COR-001 |
| 13 | Profile image update creates new emoji | REQ-ADV-003 |
| 14 | Old emoji deleted only after successful replacement | REQ-ADV-004 |
| 15 | Invalid profiles do not interrupt other relays | REQ-COR-020 |
| 16 | Relay failures logged and retriable | REQ-ADV-010, REQ-ADV-011 |

### Overview requirements

- REQ-OVR-001: The bot must be installed and operate only in the single central Discord guild identified by `GUILD_ID`. [MVP]
- REQ-OVR-002: The bot must relay followed webhook announcements from configured source channels through transformed, published messages on one or more network output announcement channels. [MVP]
- REQ-OVR-003: The MVP release must implement all functionality through implementation phases 1–8 as defined in `doc/plan.md` §22. [MVP]
- REQ-OVR-004: The bot must use Python 3.12+, discord.py 2.x, aiosqlite, and Pillow as the required runtime stack. [MVP]
- REQ-OVR-005: Network routes and profile data must be stored in SQLite; the bot must not require an external database for v1. [MVP]

### Open Questions

The following items remain unresolved; this spec documents them without encoding defaults as MVP requirements:

1. **Product naming** — Repository name *The Network*, plan title *Discord Announcement Network Relay*, and example network key `stingers` coexist. Canonical product and network naming for documentation and emoji slug prefix (`net_<slug>_…`) is TBD.
2. **Moderator role** — Admin commands require `Manage Guild` or a configured moderator role; the env var or database setting for that role is undefined.
3. **Manual relay flag** — `MANUAL_RELAY_ENABLED` exists; operational policy for when administrators enable non-webhook relay is unspecified.
4. **Reply reference behavior** — Optional quoted reply on relayed messages; no v1 default chosen.
5. **Emoji cleanup policy** — Criteria for "unused" in `/maintenance cleanup-emojis` are not fully specified.
6. **Rate limits and emoji cap** — Proactive emoji budget guidance before deployment is undefined.
7. **Test Discord environment** — No documented test guild or token strategy for ongoing validation.

---

## Actor Types

Actor types are persistent entities and roles that participate in relay operations. Discord snowflake IDs are the authoritative identity keys; human-readable names are display metadata only.

### Bot (Relay Client)

The bot is a single-process discord.py client authenticated via `DISCORD_TOKEN` and scoped to one central guild.

- REQ-ACT-001: The bot must connect to Discord on startup, initialize the SQLite database, run migrations, and validate the configured guild. [MVP]
- REQ-ACT-002: The bot must load networks and profiles into in-memory caches after startup without automatically rebuilding every emoji on each restart. [MVP]
- REQ-ACT-003: The bot must sync application slash commands to the central guild on startup. [MVP]
- REQ-ACT-004: The bot must ignore messages sent by itself to prevent self-relay loops. [MVP]

### Network

A Network groups one feed category, one output announcement channel, an optional concat audit channel, and the profile forum threads whose source channels belong to that feed.

| Field | Purpose |
|-------|---------|
| `key` | Unique slug (e.g. `stingers`) |
| `display_name` | Human-readable label |
| `feed_category_id` | Category containing source and concat channels |
| `output_channel_id` | Destination announcement channel |
| `concat_channel_id` | Optional audit mirror channel |
| `enabled` | Active/inactive routing |

- REQ-ACT-005: Each network must have exactly one output announcement channel and one feed category. [MVP]
- REQ-ACT-006: Each network must support zero or more source channels inside its feed category. [MVP]
- REQ-ACT-007: Network routes must be persisted in the `networks` SQLite table and managed via slash commands, not hardcoded in source files. [MVP]
- REQ-ACT-008: A disabled network must cause the bot to ignore messages from its source channels without affecting other networks. [MVP]

### ServerProfile

A ServerProfile maps one participating server to one dedicated source feed channel via a forum thread configuration record.

| Field | Purpose |
|-------|---------|
| `source_channel_id` | Unique authoritative server identity |
| `profile_thread_id` | Forum thread holding configuration |
| `network_id` | Target network (with optional override in thread body) |
| `server_name`, `display_name` | Display metadata |
| `emoji_id`, `emoji_name` | Guild custom emoji for relay header |
| `image_hash` | Change detection for emoji sync |
| `degraded_reason` | Fallback state when emoji creation fails |
| `enabled` | Active/inactive relay for this server |

- REQ-ACT-009: Each ServerProfile must correspond to exactly one forum thread and one unique source channel ID. [MVP]
- REQ-ACT-010: The source channel ID must be the authoritative identity for a participating server, not the webhook author name or display name. [MVP]
- REQ-ACT-011: A disabled profile must cause the bot to ignore messages from its source channel without blocking relays for other profiles. [MVP]
- REQ-ACT-012: Forum profile threads must be treated as configuration records, not free-form discussion threads. [MVP]

### RelayRecord

A RelayRecord tracks the relay lifecycle for one source Discord message.

| Field | Purpose |
|-------|---------|
| `source_message_id` | Unique idempotency key |
| `source_channel_id` | Origin feed channel |
| `profile_id`, `network_id` | Routing context |
| `destination_channel_id` | Output announcement channel |
| `destination_message_ids` | JSON array of sent message IDs (including continuations) |
| `status` | Lifecycle state |
| `error_message` | Failure detail when applicable |

- REQ-ACT-013: Each relayed source message must have at most one RelayRecord keyed by `source_message_id`. [MVP]
- REQ-ACT-014: RelayRecord status must progress through defined states: `pending`, `sent`, `published`, or failure states `failed_send`, `failed_publish`, `partial`. [MVP]

### Settings

The Settings entity is a key-value store in the `settings` SQLite table for bot-wide configuration not stored in environment variables.

- REQ-ACT-015: The bot must persist runtime settings in the `settings` table with string keys and values. [MVP]

### Human Roles

Three human role types interact with the system:

**Central guild administrator** — Installs and operates the bot, defines networks, maintains the profile forum, grants permissions, diagnoses failures, and retries stuck relays.

**Participating server operator** — Configures Channel Follow from their announcement channel into a dedicated source channel and maintains their profile thread (display name, source channel, profile image).

**Downstream follower (passive)** — Communities that follow the network output announcement channel via Discord Channel Follow; they receive published crossposts without configuring the bot directly.

- REQ-ACT-016: All administrative slash commands must require `Manage Guild` permission or a configured moderator role (moderator role configuration TBD). [MVP]
- REQ-ACT-017: Downstream followers must receive announcements only through Discord's published crosspost mechanism from the output announcement channel; they must not interact with bot commands in v1. [MVP]

---

## Item Types

Item types are message payloads, media artifacts, and configuration records processed during relay and admin operations.

### FollowedAnnouncementMessage

The inbound message delivered by Discord Channel Follow into a configured source channel. Typically webhook-delivered with an original author name from the upstream server.

- REQ-ITM-001: A FollowedAnnouncementMessage must be identified by its Discord `source_message_id` and `source_channel_id`. [MVP]
- REQ-ITM-002: By default, only webhook-delivered followed announcements (non-null `webhook_id`) must be eligible for relay unless `MANUAL_RELAY_ENABLED` is true. [MVP]

### RelayedMessage

The outbound recreated message sent to the output announcement channel, including header, preserved content, attachments, and embeds.

- REQ-ITM-003: A RelayedMessage must include a header formatted as `**Original Username** <server emoji>` followed by preserved source content. [MVP]
- REQ-ITM-004: RelayedMessages must be new Discord messages (recreated), not forwards of the source message. [MVP]
- REQ-ITM-005: Each published RelayedMessage must originate from the configured output announcement channel of the source message's network. [MVP]

### ContinuationMessage

Additional messages sent when transformed content exceeds Discord's message length limit.

- REQ-ITM-006: ContinuationMessages must be prefixed with `↳ continued` and linked to the same source message in the relay database. [MVP]
- REQ-ITM-007: All ContinuationMessages for one source event must be published individually for downstream Channel Follow. [MVP]

### ProfileImage

The first valid image attachment on a profile forum thread's starter message, used to generate the server-specific custom emoji.

- REQ-ITM-008: ProfileImage must be sourced only from Discord-hosted attachments on the forum starter message in v1; arbitrary external URLs must not be accepted. [MVP]
- REQ-ITM-009: ProfileImage must be normalized to PNG, center-cropped to square, resized to 128×128, and hashed with SHA-256 for change detection. [MVP]

### CustomEmoji

A guild custom emoji created from a ProfileImage with deterministic naming.

- REQ-ITM-010: CustomEmoji names must follow the pattern `net_<slug>_<short_channel_id>` (e.g. `net_vanguard_345678`); rendering must use emoji ID, not name. [MVP]
- REQ-ITM-011: When emoji creation fails due to guild emoji limits, the system must use fallback symbol `◈` and record a degraded reason on the profile. [MVP]

### NetworkRoute

The resolved routing context for a source channel: enabled profile, enabled network, output channel, and optional concat channel.

- REQ-ITM-012: NetworkRoute resolution must map a source channel to its parent feed category's network output channel. [MVP]

### AuditLogEntry

Human-readable and structured log records for relay and admin events.

- REQ-ITM-013: AuditLogEntry must include source message ID, source channel ID, profile ID, network ID, destination channel ID, destination message IDs, status, error class, and duration where applicable. [MVP]
- REQ-ITM-014: Concise human-readable audit messages must be written to the configured relay log channel (`RELAY_LOG_CHANNEL_ID`). [MVP]

---

## Core Mechanics

Core mechanics define routing rules, configuration, safety constraints, and persistence behavior.

### Architectural principles

1. Source channel ID is authoritative server identity.
2. Forum profiles are configuration records.
3. Network routing is based on feed category.
4. Concat is an audit mirror, not a second relay hop.
5. Messages are recreated, not forwarded.
6. New messages are published from the output announcement channel.
7. Emoji replacement is transactional.
8. Source message ID provides idempotency.
9. SQLite is the initial source of truth.
10. Discord IDs are stored as integers and never inferred from names.

### Network routing

- REQ-COR-001: The bot must reject duplicate relay attempts for the same `source_message_id` by checking `relay_records` before processing. [MVP]
- REQ-COR-002: Messages in any configured source channel must be routed to the output announcement channel associated with that channel's network feed category. [MVP]
- REQ-COR-003: The bot must accept followed announcements delivered by Discord Channel Follow into dedicated source channels inside a configured feed category. [MVP]
- REQ-COR-004: The bot must recognize when an incoming message is in a configured source channel with a mapped ServerProfile. [MVP]
- REQ-COR-005: The bot must load the ServerProfile whose `source_channel_id` matches the message's channel. [MVP]
- REQ-COR-006: The bot must ignore messages outside configured feed categories. [MVP]
- REQ-COR-007: The bot must ignore messages posted in the concat channel. [MVP]
- REQ-COR-008: The bot must ignore message updates generated by Discord after a message has already been relayed. [MVP]
- REQ-COR-009: When `MANUAL_RELAY_ENABLED` is false, the bot must ignore non-webhook messages in source channels. [MVP]
- REQ-COR-010: When `MANUAL_RELAY_ENABLED` is true, the bot must accept non-webhook messages in source channels for relay. [MVP]

### Profile configuration

- REQ-COR-011: Profile forum threads must define server display name, source feed channel, enabled state, optional network override, optional display label, and profile image. [MVP]
- REQ-COR-012: The profile parser must accept YAML-like key-value bodies with case-insensitive keys, ignoring blank lines and `#` comments. [MVP]
- REQ-COR-013: The profile parser must accept source channel as raw ID or `<#channel_id>` mention format. [MVP]
- REQ-COR-014: The profile parser must fall back to thread title for `server_name` and to `server_name` for `display_name` when omitted. [MVP]
- REQ-COR-015: The profile parser must resolve `network` by key or infer network from the source channel's parent category when absent. [MVP]
- REQ-COR-016: When profile parsing fails, the bot must not overwrite a previously valid profile and must reply in the forum thread with a concise error. [MVP]
- REQ-COR-017: Profile synchronization must run on forum thread create, starter message edit, thread title change, attachment add/replace, and `/profile sync`. [MVP]

### Source-channel identity

- REQ-COR-018: The bot must use the webhook author name from the followed announcement for the relay header username. [MVP]
- REQ-COR-019: The bot must derive source server identity from the profile mapped to the source channel, not from the webhook author name. [MVP]

### Deduplication and idempotency

- REQ-COR-020: Invalid or failed profile sync for one server must not interrupt relay processing for other servers. [MVP]
- REQ-COR-021: The bot must acquire a per-source-message lock (`relay:<source_message_id>`) before relay processing to prevent duplicate concurrent handling. [MVP]
- REQ-COR-022: The bot must create a RelayRecord in `pending` state before sending the recreated message. [MVP]
- REQ-COR-023: Duplicate Discord events for an already-recorded source message must be ignored at debug log level without resending. [MVP]

### Mention suppression and content safety

- REQ-COR-024: The bot must send relayed messages with `discord.AllowedMentions.none()` to suppress all live mentions. [MVP]
- REQ-COR-025: The bot must not relay `@everyone`, `@here`, user mentions, or role mentions as active mentions. [MVP]
- REQ-COR-026: The bot must sanitize the author name in the relay header to prevent mention injection. [MVP]
- REQ-COR-027: The bot token must be stored only in environment variables and must never appear in logs. [MVP]
- REQ-COR-028: The bot must validate all Discord IDs against the central guild for admin operations. [MVP]
- REQ-COR-029: The bot must not execute content from profile messages or expose stack traces in public channels. [MVP]

### Configuration bootstrap

Environment variables (secrets and bootstrap only):

| Variable | Purpose |
|----------|---------|
| `DISCORD_TOKEN` | Bot authentication |
| `GUILD_ID` | Central guild snowflake |
| `DATABASE_PATH` | SQLite file path (default `./data/relay.db`) |
| `LOG_LEVEL` | Logging verbosity |
| `PROFILE_FORUM_CHANNEL_ID` | Profile forum channel |
| `RELAY_LOG_CHANNEL_ID` | Human-readable relay log |
| `MANUAL_RELAY_ENABLED` | Allow non-webhook relay (default `false`) |

- REQ-COR-030: The bot must validate `DISCORD_TOKEN` and `GUILD_ID` at startup. [MVP]
- REQ-COR-031: Network routes must not be hardcoded in application source files. [MVP]
- REQ-COR-032: Channel IDs for networks, profiles, and routes must be stored in SQLite and managed through slash commands. [MVP]

### Persistence model

SQLite tables:

**`networks`** — `id`, `guild_id`, `key` (unique), `display_name`, `feed_category_id` (unique), `output_channel_id` (unique), `concat_channel_id`, `enabled`, timestamps.

**`profiles`** — `id`, `guild_id`, `profile_thread_id` (unique), `profile_starter_message_id` (unique), `source_channel_id` (unique), `network_id`, `server_name`, `display_name`, `enabled`, `emoji_id`, `emoji_name`, `image_hash`, `image_source_url`, `degraded_reason`, timestamps.

**`relay_records`** — `id`, `source_message_id` (unique), `source_channel_id`, `source_webhook_id`, `profile_id`, `network_id`, `destination_channel_id`, `destination_message_ids` (JSON array), `status`, `error_message`, timestamps.

**`settings`** — `key` (primary), `value`, `updated_at`.

- REQ-COR-033: The bot must persist all network, profile, relay, and settings data in SQLite via aiosqlite. [MVP]
- REQ-COR-034: Discord IDs must be stored as integers in SQLite, never inferred from channel or role names. [MVP]

### Image processing

- REQ-COR-035: The image pipeline must support PNG, JPEG, WEBP, and GIF formats; animated GIFs must use the first frame converted to static PNG. [MVP]
- REQ-COR-036: The image pipeline must reject SVG, undecodable files, and excessively large downloads. [MVP]
- REQ-COR-037: Image downloads must use timeouts and a maximum download size limit. [MVP]

---

## Combat System

The Combat System section specifies the relay pipeline: end-to-end message processing from inbound feed event through publish and audit persistence. (The section title is a coordinator template label; no game combat mechanics apply.)

### End-to-end flow

Processing order for each `on_message` event in a feed source channel:

```text
1. Is the message in the configured guild?
2. Is the message in a configured source channel?
3. Is the profile enabled?
4. Is the network enabled?
5. Is the message already present in relay_records?
6. Is the message from the relay bot?
7. Is it a webhook message (or manual relay enabled)?
8. Transform the message.
9. Send to the output announcement channel.
10. Publish the message(s).
11. Write audit copy to concat, if configured.
12. Persist relay_records.
```

- REQ-REL-001: The bot must recognize a followed webhook announcement in a configured source channel with an enabled profile and enabled network and initiate relay processing. [MVP]
- REQ-REL-002: The bot must transform eligible messages into recreated content with header `**Original Username** <server emoji>` plus preserved source text and media. [MVP]
- REQ-REL-003: The bot must send recreated message(s) to the network's configured output announcement channel. [MVP]
- REQ-REL-004: The bot must publish each sent message in the output announcement channel via Discord's crosspost/publish action. [MVP]
- REQ-REL-005: Downstream communities following the output announcement channel must receive the published announcement through Discord Channel Follow without additional bot action. [MVP]
- REQ-REL-006: The bot must persist the RelayRecord with final status after send, publish, and optional audit steps complete. [MVP]

### Incoming message filter chain

- REQ-REL-007: Messages outside the configured guild must be ignored. [MVP]
- REQ-REL-008: Messages in source channels without a mapped profile must be ignored. [MVP]
- REQ-REL-009: Messages for disabled profiles or disabled networks must be ignored without error propagation to other relays. [MVP]
- REQ-REL-010: Messages already present in `relay_records` must be ignored without resending. [MVP]
- REQ-REL-011: Messages from the relay bot itself must be ignored. [MVP]
- REQ-REL-012: Non-webhook messages must be ignored when `MANUAL_RELAY_ENABLED` is false. [MVP]

### Message transformation

- REQ-REL-013: The bot must preserve message text, attachments, embeds, URLs, basic markdown, original author name, and profile emoji where Discord API permits. [MVP]
- REQ-REL-014: Empty-content messages must be relayed only when attachments, embeds, stickers, or other supported content exist. [MVP]
- REQ-REL-015: The bot must download and re-upload attachments to the destination message, preserving original filenames when safe. [MVP]
- REQ-REL-016: The bot must copy up to Discord's embed limit, preserving titles, descriptions, fields, footer text, and image/thumbnail URLs where permitted. [MVP]
- REQ-REL-017: When an embed cannot be sent, the bot must fall back to a plain-text summary rather than failing the entire relay. [MVP]
- REQ-REL-018: Stickers must be appended as plain text with name and URL when available. [MVP]
- REQ-REL-019: Polls must be appended as a plain-text summary when available. [MVP]
- REQ-REL-020: Interactive components (buttons, menus) must not be recreated on relayed messages. [MVP]
- REQ-REL-021: Reply references may optionally include a short quoted reply; default v1 behavior is TBD (see Open Questions). [post-MVP]
- REQ-REL-022: The bot must avoid copying Discord-generated embeds that duplicate a URL already present in message content when doing so would create visible duplication. [MVP]

### Send and publish

- REQ-REL-023: The bot must verify the destination channel is an announcement channel before sending. [MVP]
- REQ-REL-024: The bot must retry transient publish failures (rate limits, temporary network errors, Discord server errors) with exponential backoff and jitter. [MVP]
- REQ-REL-025: The bot must not retry permanent permission failures, invalid channel types, or deleted channels indefinitely. [MVP]
- REQ-REL-026: Publish failures must be logged to structured logs and the relay log channel. [MVP]
- REQ-REL-027: The bot must hold appropriate permissions in the output channel: view, send messages, embed links, attach files, and publish messages. [MVP]

### Message length and continuations

- REQ-REL-028: The bot must not silently truncate transformed content that exceeds Discord's message length limit. [MVP]
- REQ-REL-029: When content exceeds the limit, the bot must send the header in the first message and split remaining content at paragraph or newline boundaries into ContinuationMessages. [MVP]
- REQ-REL-030: Attachments must remain on the first message unless Discord upload constraints require distribution across continuation messages. [MVP]
- REQ-REL-031: When combined attachment size exceeds Discord limits, the bot must distribute attachments across continuation messages preserving order and log an audit warning. [MVP]

### Concat audit mirror

- REQ-REL-032: When a concat channel is configured, the bot must write a plain-text audit copy of what was sent to the output channel. [MVP]
- REQ-REL-033: The concat channel must function as an audit stream only; the bot must not treat concat as a second event-driven relay hop. [MVP]
- REQ-REL-034: Production relay must use direct mode (source → transform → output → publish); concat mirroring must not trigger a second relay cycle. [MVP]

### Failure states and logging

- REQ-REL-035: Relay failures must set RelayRecord status to `failed_send`, `failed_publish`, or `partial` as appropriate. [MVP]
- REQ-REL-036: Structured relay log entries must include event name, source message ID, channel IDs, profile ID, network ID, destination message IDs, status, error class, and duration in milliseconds. [MVP]
- REQ-REL-037: Source message edits in v1 must not automatically edit published relay messages; the bot must log that the source was edited. [MVP]
- REQ-REL-038: Source message deletions in v1 must not automatically delete published announcements; the bot must log the deletion and retain the relay record. [MVP]

---

## Advancement

Advancement covers lifecycle progression for profiles, emojis, relay states, and administrative recovery operations.

### Profile sync lifecycle

- REQ-ADV-001: On profile sync, the bot must parse the forum thread, validate the source channel, resolve the network, normalize the image, create or replace the emoji, save the profile, and report warnings. [MVP]
- REQ-ADV-002: `/profile sync-all` must enumerate all threads in the configured profile forum and synchronize each, returning a summary. [MVP]
- REQ-ADV-003: When a profile image hash changes, the bot must create a new custom emoji before updating the stored profile record. [MVP]

### Emoji replacement lifecycle

- REQ-ADV-004: The bot must delete the old custom emoji only after the replacement emoji is successfully created and persisted. [MVP]
- REQ-ADV-005: When the profile image hash is unchanged, the bot must skip emoji recreation. [MVP]
- REQ-ADV-006: When a profile is deleted or disabled, the bot must retain the associated emoji by default. [MVP]
- REQ-ADV-007: `/profile repair-emoji` must attempt to recreate a missing emoji for a profile when explicitly invoked. [MVP]
- REQ-ADV-008: Emoji creation failure due to guild limits must mark the profile degraded with reason and use `◈` fallback without blocking profile existence. [MVP]

### Relay state progression

Relay state flow:

```text
pending -> sent -> published
```

Failure branches: `failed_send`, `failed_publish`, `partial`.

- REQ-ADV-009: The bot must update RelayRecord status from `pending` to `sent` after successful send and to `published` after successful publish. [MVP]
- REQ-ADV-010: Relay failures must be logged with sufficient context for administrators to diagnose the issue within minutes. [MVP]
- REQ-ADV-011: `/relay retry` must attempt recovery of incomplete or failed relays without creating duplicate downstream published messages. [MVP]

### Admin recovery and retry

- REQ-ADV-012: `/relay recent` must list recent relay activity for administrator inspection. [MVP]
- REQ-ADV-013: `/relay status` must report relay status for a specified source message or recent activity. [MVP]
- REQ-ADV-014: `/maintenance rebuild-cache` must reload networks and profiles into in-memory caches from SQLite. [MVP]
- REQ-ADV-015: `/maintenance validate` must check configuration consistency and report issues. [MVP]
- REQ-ADV-016: Startup must validate channel permissions and log startup status without rebuilding all emojis automatically. [MVP]
- REQ-ADV-017: `/relay refresh <message_link>` for edit synchronization is deferred beyond v1. [post-MVP]

---

## Power Budget

Power budget defines operational limits, degradation behavior, and resource constraints.

### Message and content limits

- REQ-PWR-001: Transformed message content must respect Discord's per-message character limit; overflow must trigger continuation splitting, not silent truncation. [MVP]
- REQ-PWR-002: Continuation messages must use the `↳ continued` prefix to signal split content to readers. [MVP]

### Attachment and embed limits

- REQ-PWR-003: Attachment downloads must enforce a maximum file size and timeout; oversized or timed-out attachments must be skipped with audit logging. [MVP]
- REQ-PWR-004: The bot must not persist attachment bytes to disk longer than necessary; in-memory buffers are preferred. [MVP]
- REQ-PWR-005: Embed copying must respect Discord's embed count and field limits per message. [MVP]

### Guild emoji capacity

- REQ-PWR-006: When the central guild reaches its custom emoji limit, the bot must degrade gracefully with `◈` fallback rather than blocking profile or relay operations. [MVP]
- REQ-PWR-007: `/maintenance cleanup-emojis` must provide administrative cleanup of unused emojis; exact "unused" criteria are TBD (see Open Questions). [MVP]
- REQ-PWR-008: Proactive emoji budget guidance before deployment is not defined in v1. [post-MVP]

### API rate limits and retry budget

- REQ-PWR-009: The bot must retry transient Discord API errors with exponential backoff and jitter. [MVP]
- REQ-PWR-010: Maximum automatic retries for transient failures must be 3. [MVP]
- REQ-PWR-011: The bot must not retry missing permissions, invalid channel types, deleted channels, invalid profiles, or emoji capacity errors. [MVP]

### Operational scope limits

- REQ-PWR-012: The bot must operate in exactly one central guild in v1. [MVP]
- REQ-PWR-013: The bot must run as a single process without persistent job queues or horizontal scaling in v1. [MVP]
- REQ-PWR-014: SQLite must be the sole database for v1; no external database connections are permitted. [MVP]
- REQ-PWR-015: Docker deployment support is optional but recommended for phase 8 hardening. [MVP]

---

## User Interface

The user interface comprises slash commands, forum profile format, relay log channel output, and permission gates. All admin commands require `Manage Guild` or a configured moderator role.

### Slash commands — /network

| Command | Purpose |
|---------|---------|
| `/network create` | Create network with key, display name, feed category, output channel, optional concat |
| `/network edit` | Modify network configuration |
| `/network list` | List all networks |
| `/network disable` | Disable a network |
| `/network enable` | Enable a network |
| `/network validate` | Validate network configuration |
| `/network delete` | Delete a network |

- REQ-UI-001: `/network create` must accept `key`, `display_name`, `feed_category`, `output_channel`, and optional `concat_channel` parameters. [MVP]
- REQ-UI-002: `/network create` must validate that the feed category belongs to the central guild and the output channel is an announcement channel. [MVP]
- REQ-UI-003: `/network create` must validate that the concat channel, when provided, is a text channel and the bot has required permissions. [MVP]
- REQ-UI-004: `/network list` must display all configured networks with their key, display name, and enabled state. [MVP]
- REQ-UI-005: `/network disable` and `/network enable` must toggle network enabled state without deleting configuration. [MVP]
- REQ-UI-006: `/network validate` must check network configuration consistency and report errors. [MVP]
- REQ-UI-007: `/network delete` must remove a network record from the database. [MVP]

### Slash commands — /profile

| Command | Purpose |
|---------|---------|
| `/profile sync` | Sync one forum profile thread |
| `/profile sync-all` | Sync all forum threads |
| `/profile show` | Display profile details |
| `/profile disable` | Disable a profile |
| `/profile enable` | Enable a profile |
| `/profile repair-emoji` | Recreate missing emoji |
| `/profile delete` | Delete a profile |

- REQ-UI-008: `/profile sync` must accept a `profile_thread` parameter and perform full parse, validate, emoji sync, and save. [MVP]
- REQ-UI-009: `/profile show` must display the stored profile fields including source channel, network, emoji state, and degraded reason if any. [MVP]
- REQ-UI-010: `/profile disable` and `/profile enable` must toggle profile relay eligibility. [MVP]
- REQ-UI-011: `/profile delete` must remove the profile record; emoji retention policy applies per REQ-ADV-006. [MVP]

### Slash commands — /relay

| Command | Purpose |
|---------|---------|
| `/relay test` | Simulate transformation and optionally send test message |
| `/relay retry` | Retry failed or incomplete relay |
| `/relay status` | Query relay status |
| `/relay recent` | List recent relay activity |

- REQ-UI-012: `/relay test` must accept `source_channel` and `text` parameters, simulate message transformation, and send a test message to the output channel. [MVP]
- REQ-UI-013: `/relay test` must not publish the test message unless `publish=true` is specified. [MVP]
- REQ-UI-014: `/relay retry` must reattempt send and/or publish for a failed relay record. [MVP]
- REQ-UI-015: `/relay recent` must list recent relay records with status and error summary. [MVP]

### Slash commands — /maintenance

| Command | Purpose |
|---------|---------|
| `/maintenance validate` | Validate overall configuration |
| `/maintenance cleanup-emojis` | Remove unused emojis |
| `/maintenance rebuild-cache` | Reload in-memory caches |
| `/maintenance permissions` | Validate bot permissions |

- REQ-UI-016: `/maintenance permissions` must validate bot permissions for profile forum, feed source channels, concat channel, output announcement channel, and guild emoji management. [MVP]
- REQ-UI-017: `/maintenance rebuild-cache` must reload network and profile caches from SQLite. [MVP]
- REQ-UI-018: `/maintenance cleanup-emojis` must provide administrative emoji cleanup per TBD unused criteria. [MVP]

### Slash commands — /status

- REQ-UI-019: `/status` must report bot connectivity, guild validation, database status, and loaded network/profile counts. [MVP]

### Forum profile thread format

Recommended body format:

```yaml
server_name: Vanguard
source_channel: <#123456789012345678>
enabled: true
network: stingers
display_name: Vanguard
```

Parsing rules: case-insensitive keys; reject duplicate keys; validate booleans and Discord IDs; fall back to thread title for server name.

- REQ-UI-020: Forum profile threads must use structured key-value configuration in the starter message body as the authoritative profile source. [MVP]
- REQ-UI-021: The first valid image attached to the forum starter message must be used as the profile image for emoji generation. [MVP]
- REQ-UI-022: Profile parse errors must be reported in the forum thread and logged in full to the relay log channel. [MVP]

### Relay log channel

- REQ-UI-023: The relay log channel must receive concise human-readable messages for relay completions, failures, profile sync results, and degraded emoji states. [MVP]
- REQ-UI-024: Structured JSON logging should be supported for operational monitoring. [post-MVP]

### Permission gates

Required permissions by surface:

| Surface | Permissions |
|---------|-------------|
| Profile forum | View Channel, Read Message History, Send Messages in Threads, Manage Threads (if bot posts status) |
| Feed source channels | View Channel, Read Message History |
| Concat channel | View Channel, Send Messages, Embed Links, Attach Files |
| Output announcement | View Channel, Send Messages, Embed Links, Attach Files, Publish Messages |
| Guild emoji | Create Expressions, Manage Expressions |

- REQ-UI-025: The bot must validate permissions at startup and via `/maintenance permissions` using permission names from the installed discord.py version. [MVP]
- REQ-UI-026: All `/network`, `/profile`, `/relay`, and `/maintenance` commands must be restricted to users with `Manage Guild` or a configured moderator role. [MVP]

---

## Out of Scope

The following capabilities are explicitly not planned for the first release. All items are deferred beyond MVP phases 1–8.

- REQ-OOS-001: Automatic synchronization of source message edits to already-published relay messages must not be implemented in v1. [out-of-scope]
- REQ-OOS-002: Automatic deletion of relayed messages when source messages are deleted must not be implemented in v1. [out-of-scope]
- REQ-OOS-003: Multiple central guilds must not be supported in v1; the bot operates in one guild only. [out-of-scope]
- REQ-OOS-004: A web dashboard or external admin UI must not be included in v1. [out-of-scope]
- REQ-OOS-005: Arbitrary external image URLs for profile images must not be accepted in v1; only Discord-hosted attachments are supported. [out-of-scope]
- REQ-OOS-006: Interactive component recreation (buttons, select menus, etc.) must not be implemented in v1. [out-of-scope]
- REQ-OOS-007: Per-message moderator approval before relay must not be implemented in v1. [out-of-scope]
- REQ-OOS-008: Cross-network message fan-out from a single source event must not be implemented in v1. [out-of-scope]
- REQ-OOS-009: Per-server filtering rules beyond configured routing and ignore rules must not be implemented in v1. [out-of-scope]
- REQ-OOS-010: Persistent job queues or background workers beyond the single bot process must not be implemented in v1. [out-of-scope]
- REQ-OOS-011: External database systems must not replace SQLite in v1. [out-of-scope]
- REQ-OOS-012: Horizontal scaling or multi-instance deployment must not be supported in v1. [out-of-scope]

---

## Related Documents

| Document | Purpose |
|----------|---------|
| [`doc/product-brief.md`](product-brief.md) | Stakeholder intent, MVP boundary, user roles, acceptance checklist |
| [`doc/intake-summary.md`](intake-summary.md) | Condensed requirements, schema summary, command inventory |
| [`doc/plan.md`](plan.md) | Full implementation plan: schema, events, commands, testing, phases |

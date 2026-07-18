# The Network — Product Brief

## Document status

**Status:** Draft for stakeholder review (product-brief phase)  
**Sources:** `doc/intake-summary.md` (primary), `doc/plan.md` (phases, acceptance, deferred scope), `work/flow.json` (project context)  
**Product name:** The Network (*Discord Announcement Network Relay* in implementation plan)  
**MVP boundary:** Implementation phases 1–8 only; deferred items remain out of scope for v1

---

## Elevator Pitch

The Network is a Discord bot installed in one central server. Partner communities publish announcements on their own servers; Discord delivers those posts into dedicated feed channels via Channel Follow. The bot rewrites each message with the original author name and a server-specific emoji, publishes the result to a network announcement channel, and downstream communities receive updates through Channel Follow—without manual copy-paste, inconsistent branding, or fragile cross-posting workflows. Administrators configure networks and participating servers using forum threads and slash commands inside Discord; there is no separate dashboard in the first release. The goal is reliable, branded announcement relay for multi-server communities that share a central hub.

---

## Target Audience & Users

### Central guild administrators

Guild operators who own the central hub server install and operate The Network. They define one or more **networks** (each with a feed category, output announcement channel, and optional audit channel), maintain the profile forum, and grant the bot permissions to read feeds, send and publish announcements, and manage custom emojis. They need clear diagnostics when relays fail, tools to retry stuck messages, and confidence that misconfigured profiles will not break relays for other servers. Typical experience: comfortable with Discord channel structure, categories, announcement channels, and Channel Follow—not necessarily developers.

### Participating server operators

Operators of external Discord servers that publish into the network configure Channel Follow from their announcement channel into a dedicated source channel in the central feed category. They create or maintain a **profile thread** in the central forum that maps their source channel to a display name and profile image (which becomes their server emoji on relayed messages). They care that their community’s voice is attributed correctly and that announcements reach downstream followers promptly. They interact with the central admins when onboarding a new server or updating branding.

### Downstream receiving communities

Servers that follow the central network announcement channel receive **published** crossposts automatically through Discord’s Channel Follow. These communities are passive recipients in v1—they do not configure the bot directly. Their success criterion is timely, readable announcements with clear source attribution (author + server emoji) and without dangerous live mentions (`@everyone`, roles, etc.) leaking from upstream messages.

---

## Problem & Context

Multi-server Discord communities often share announcements through manual copy-paste, webhook hacks, or informal moderator relays. That approach breaks down as participation grows: branding is inconsistent, attribution is lost, mentions can misfire across guild boundaries, and there is no single audit trail when something fails silently. Discord’s Channel Follow solves delivery into a central feed, but raw followed messages do not identify which participating server spoke, do not carry a consistent visual identity, and are not automatically republished for downstream followers.

The Network sits in the central guild as the transformation and publishing layer between “followed feed” and “network announcement channel.” It treats each participating server as a configured profile (forum thread + source channel mapping), applies a deterministic header format, suppresses live mentions for safety, recreates content (rather than forwarding), and publishes so downstream Channel Follow works as intended. Manual cross-posting and ad hoc bots cannot offer idempotent relay records, emoji sync from profile images, or admin recovery commands in one cohesive product.

---

## Core Workflow Loop

### End-to-end relay flow

```text
External server announcement channel
    -> Discord Channel Follow
    -> Dedicated source channel inside a feed category
    -> Bot transforms the message
    -> Optional concat/audit channel
    -> Network announcement channel
    -> Bot publishes the message
    -> Other servers receive it through Discord Channel Following
```

Each **network** groups: one output announcement channel, one feed category containing zero or more source channels (plus an optional concat audit channel), and a profile forum with one thread per participating server. Messages in any configured source channel route to that network’s output channel. The bot ignores messages outside configured feeds, messages in the concat channel, its own messages, non-webhook followed announcements (unless manual relay is explicitly enabled), post-relay edits, and duplicate source events.

### Example scenario

```text
External Server A #announcements
    -> Central Server / Stingers Feed / #server-a
    -> Bot
    -> [Original Author] [Server A Emoji]
       Original message
    -> Central Server / The Network / #stingers
    -> Published announcement
    -> Downstream servers following #stingers receive the update
```

Server A posts “Raid starts at 8 PM.” in its announcements channel. Discord follows that into `#server-a` in the central feed. The bot loads Server A’s profile (mapped to that source channel), formats the message as **Original Username** plus Server A’s custom emoji and the original text, sends it to `#stingers`, publishes it, optionally mirrors plain text to `#concat` for audit, and records the relay. Communities following `#stingers` receive the published announcement with consistent attribution.

### What the bot does on each message (high level)

1. Confirm the message is in a configured source channel for an enabled profile and network.
2. Skip if already relayed (idempotency by source message ID), from the bot itself, or not a followed webhook announcement (unless manual relay policy allows otherwise).
3. Transform content: header with webhook author name and profile emoji, preserve text/media where supported, suppress live mentions.
4. Send recreated message(s) to the output announcement channel; split long text at paragraph boundaries with clear continuations when needed.
5. Publish the announcement; retry transient failures; log permanent failures.
6. Optionally write an audit copy to the concat channel (mirror only—not a second relay hop).
7. Persist relay status for admin visibility and retry.

---

## Key Differentiators

- **Forum-thread profiles as configuration** — Participating servers are onboarded via forum threads in the central guild (display name, source channel, image, enable/disable). No external dashboard in v1; Discord-native admin workflow.
- **Deterministic per-server custom emoji** — Each profile image becomes a guild emoji with a stable naming scheme; emoji updates are transactional (create replacement before deleting the old one). Degraded fallback when guild emoji limits are hit.
- **Recreated and published messages, not forwards** — Relays are new messages with controlled formatting and mention suppression, then published from the announcement channel so downstream Channel Follow behaves predictably.
- **Concat channel as audit mirror** — Optional plain-text audit stream showing what was sent; not a second event-driven relay path (avoids loops and duplicates).
- **SQLite-backed idempotency and admin recovery** — Source message ID prevents duplicate relays; administrators can inspect recent activity, diagnose failures, and retry incomplete relays without re-architecting delivery.

---

## Product Principles

1. **Source channel ID is authoritative** — A participating server is identified by its dedicated feed channel, not by display names or webhook author strings alone.
2. **Profiles are configuration, not discussion** — Forum threads hold structured profile data; they are the system of record for server identity in the relay.
3. **Route by feed category** — Each network’s feed category determines which source channels map to which output announcement channel.
4. **Safety over fidelity for mentions** — Live `@everyone`, `@here`, user, and role mentions are never relayed as active mentions; content is preserved where possible without cross-guild ping risk.
5. **Recreate, then publish** — Delivery to downstream communities depends on published announcements from the output channel, not on forwarding raw followed messages.
6. **Fail isolated, recover visibly** — Invalid or disabled profiles must not stop other relays; failures are logged and retriable by administrators.
7. **Discord IDs over names** — Persistent identity uses Discord snowflake IDs; human-readable names are display metadata only.

---

## MVP Definition

### Release goal

Ship a single-guild, SQLite-backed Discord bot that reliably relays followed announcements from configured source channels through transformed, published messages on one or more network output channels, with forum-based profiles, server emojis, media support, audit tooling, and operational hardening through phase 8.

### Implementation phases (1–8)

| Phase | Focus | Deliverable |
|-------|-------|-------------|
| **1 — Bootstrap** | Project setup, bot connection, SQLite, logging, slash sync | Bot starts, connects, initializes DB, responds to `/status` |
| **2 — Network routing** | Network persistence, create/list, category/output validation, route cache | Bot maps feed category to output announcement channel |
| **3 — Profiles** | Forum profile parser, sync, storage, source-channel mapping | Forum thread configures one source server profile |
| **4 — Emoji sync** | Image download, normalize, hash, custom emoji create/replace, fallback | Each profile owns server-specific emoji from its image |
| **5 — Basic relay** | Feed listener, webhook filter, formatter, mention suppression, send, publish, records | Plain-text followed announcements relay end to end |
| **6 — Media support** | Attachments, embeds, empty-content media, text splitting, continuations | Typical Discord announcements retain useful media |
| **7 — Audit & recovery** | Concat mirror, relay log, recent/retry, permission validation, cache rebuild | Administrators diagnose and recover failed relays |
| **8 — Hardening** | Full tests, Docker, rate-limit retries, cleanup commands, docs, SQLite backup | Bot ready for long-running deployment |

### Acceptance criteria (release checklist)

First release is complete when all of the following work:

- [ ] An external announcement is published
- [ ] Discord delivers it to a dedicated source channel
- [ ] The bot recognizes the source channel
- [ ] The bot loads the correct server profile
- [ ] The bot formats `**Original Username** <server emoji>` plus original content
- [ ] Attachments are copied
- [ ] Supported embeds are copied
- [ ] Live mentions are suppressed
- [ ] The recreated message is sent to the output announcement channel
- [ ] The recreated message is published
- [ ] A receiving server obtains the published announcement
- [ ] Duplicate source events do not create duplicate messages
- [ ] Updating the profile image creates a new emoji
- [ ] The old emoji is deleted only after successful replacement
- [ ] Invalid profiles do not interrupt other relays
- [ ] Relay failures are logged and can be retried

### Admin surfaces in MVP (summary)

Administrators manage the product entirely inside the central Discord guild:

- **Networks** — Create and maintain networks (feed category, output announcement channel, optional concat channel, enable/disable, validate, delete) via `/network` commands. Routes live in the database, not hardcoded in source.
- **Forum profiles** — One forum thread per participating server defines name, source channel, optional network override, enable state, and profile image. Sync via forum events and `/profile` commands (sync, show, enable/disable, repair emoji, delete).
- **Relay diagnostics** — `/relay` commands for test transforms, status, recent activity, and retry of failed relays; relay log channel for human-readable events; optional concat channel as read-only audit mirror.
- **Maintenance** — Validate configuration, check permissions, rebuild caches, and clean up unused emojis via `/maintenance` commands. All admin commands require `Manage Guild` or a configured moderator role (exact configuration TBD—see Open Questions).

Detailed command specifications and schema belong in the downstream `spec` phase—not this brief.

---

## Out of Scope (Deferred v1)

The following are explicitly **not** in the first release:

- Automatic synchronization of source message edits
- Automatic deletion of relayed messages when source messages are deleted
- Multiple central guilds (single central guild only in v1)
- Web dashboard or external admin UI
- Arbitrary external image URLs for profile images (v1 uses Discord-hosted attachments only)
- Interactive component recreation (buttons, menus, etc.)
- Per-message moderator approval before relay
- Cross-network message fan-out from a single source event
- Per-server filtering rules beyond configured routing and ignore rules
- Persistent job queues or background workers beyond the single bot process
- External database (SQLite only for v1)
- Horizontal scaling or multi-instance deployment

These may be considered after the basic relay path is stable in production.

---

## Success Metrics

Operational signals for a healthy v1 deployment (qualitative targets; exact thresholds to be set at deployment):

- **Relay latency** — Followed announcements appear as published network messages within a short, predictable window under normal Discord API conditions.
- **Relay success rate** — Failed sends or publishes are rare; transient failures recover via automatic retry or admin `/relay retry` without duplicate downstream posts.
- **Profile sync reliability** — New or updated forum profiles sync to valid routing and emoji state without blocking unrelated relays.
- **Idempotency** — Duplicate Discord events for the same source message never produce duplicate published announcements.
- **Auditability** — Administrators can answer “what happened to this announcement?” using relay logs, recent relay commands, and optional concat mirror within minutes.
- **Safety** — No incidents of live cross-guild mentions from relayed content in standard configuration.
- **Operational readiness** — Bot survives restarts, documents cover deployment and SQLite backup, and test coverage supports confident changes post-launch.

---

## Open Questions

These items remain unresolved in intake and must not be assumed in this brief:

1. **Product naming** — Repository name *The Network*, plan title *Discord Announcement Network Relay*, and example network key `stingers` coexist. Confirm canonical product and network naming for documentation and emoji slug prefix (`net_<slug>_…`).

2. **Initial deployment target** — Docker is optional in the plan; no production hosting, process manager, or production guild details are specified.

3. **Moderator role** — Admin commands require `Manage Guild` or a configured moderator role; the env var or database setting for that role is not defined in bootstrap configuration.

4. **Manual relay flag** — `MANUAL_RELAY_ENABLED` exists; operational policy for when administrators should enable non-webhook relay is unspecified.

5. **Reply reference behavior** — Optional short quoted reply reference on relayed messages is noted; no v1 default behavior is chosen.

6. **Emoji cleanup policy** — Emojis are retained when profiles are disabled or deleted by default; criteria for “unused” in emoji cleanup commands are not fully specified.

7. **Rate limits and guild emoji cap** — Degraded fallback (`◈`) when emoji creation fails is defined; no proactive guidance on emoji budget or guild limits before deployment.

8. **Test Discord environment** — Manual end-to-end setup is described; no documented test guild or token strategy for ongoing validation.

---

## Related Documents

| Document | Purpose |
|----------|---------|
| [`doc/intake-summary.md`](intake-summary.md) | Condensed requirements, phases, acceptance, deferred scope, open questions |
| [`doc/plan.md`](plan.md) | Full implementation plan: schema, events, commands, testing, phases 1–8 |
| [`work/flow.json`](../work/flow.json) | Pipeline selection and project adaptation notes (Discord bot, not game tooling) |

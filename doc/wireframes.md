# Wireframes — The Network

Discord admin interaction flows for MVP: slash commands, embeds, forum thread replies, relay log channel messages, and output announcements. Covers central-guild administrator tooling and participating-server operator forum setup only — no game UI, Foundry sheets, HUD, or downstream follower slash commands.

---

## Admin slash commands

## Bot Status

**Surface:** `/status` → interaction response embed (public)

**Slash options:** _(none)_

**Layout:**

```
┌─ Discord client ─────────────────────────────────────────┐
│ /status                                                  │
├─ Interaction response ─────────────────────────────────┤
│ ┌─ Embed ──────────────────────────────────────────────┐ │
│ │ Title: [success] Bot Status                          │ │
│ │ ──────────────────────────────────────────────────── │ │
│ │ Field: Connectivity                                  │ │
│ │   Discord: connected | latency: 42ms                 │ │
│ │ Field: Guild                                         │ │
│ │   name: The Network | id: 123… | validation: OK    │ │
│ │ Field: Database                                      │ │
│ │   path: ./data/relay.db | status: OK | migrated: ✓  │ │
│ │ Field: Loaded counts                                 │ │
│ │   networks: 2 | profiles: 5 | enabled profiles: 4    │ │
│ │ Footer: uptime 3h 12m | commands synced              │ │
│ └──────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────┘
```

**Key fields:** Connectivity state, guild validation result, `DATABASE_PATH` status, network count, profile count, enabled profile count.

**Actions:** Administrator invokes `/status` to confirm bot health after deploy or incident.

---

## Admin Permission Denied

**Surface:** Any restricted admin command → ephemeral interaction response (visible only to invoker)

**Slash options:** _(example)_ `/network list`, `/profile sync`, `/relay test`, `/maintenance validate`

**Layout:**

```
┌─ Ephemeral response (only you) ──────────────────────────┐
│ ⛔ Permission denied                                     │
│                                                          │
│ You need Manage Guild or the configured moderator role   │
│ to run admin commands.                                   │
│                                                          │
│ Command attempted: /network list                         │
└──────────────────────────────────────────────────────────┘
```

**Key fields:** Error title, required permission names (`Manage Guild`, configured moderator role), attempted command name.

**Actions:** User gains permission or contacts guild admin; retries command after role assignment.

---

## Network Create Success

**Surface:** `/network create` → interaction response embed (public)

**Slash options:** `key`, `display_name`, `feed_category`, `output_channel`, `concat_channel` (optional)

**Layout:**

```
┌─ Discord client ─────────────────────────────────────────┐
│ /network create key:stingers display_name:Stingers       │
│   feed_category:Stingers Feed output_channel:#stingers   │
│   concat_channel:#concat                                 │
├─ Interaction response ───────────────────────────────────┤
│ ┌─ Embed ──────────────────────────────────────────────┐ │
│ │ Title: [success] Network Created                     │ │
│ │ ──────────────────────────────────────────────────── │ │
│ │ Field: key                                           │ │
│ │   stingers                                           │ │
│ │ Field: display_name                                  │ │
│ │   Stingers                                           │ │
│ │ Field: feed_category                                 │ │
│ │   Stingers Feed (id 9876543210)                      │ │
│ │ Field: output_channel                                │ │
│ │   #stingers (announcement)                           │ │
│ │ Field: concat_channel                                │ │
│ │   #concat (text)                                     │ │
│ │ Field: enabled                                       │ │
│ │   true (default)                                     │ │
│ └──────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────┘
```

**Key fields:** `key`, `display_name`, `feed_category` ID/name, `output_channel` ID/name, `concat_channel` ID/name (optional), default `enabled: true`.

**Actions:** Administrator registers a new network route; proceeds to add profiles or validate configuration.

---

## Network Create Validation Error

**Surface:** `/network create` → interaction response embed (ephemeral on error)

**Slash options:** `key`, `display_name`, `feed_category`, `output_channel`, `concat_channel` (optional)

**Layout:**

```
┌─ Discord client ─────────────────────────────────────────┐
│ /network create key:stingers …                           │
├─ Ephemeral response (only you) ──────────────────────────┤
│ ┌─ Embed ──────────────────────────────────────────────┐ │
│ │ Title: [error] Network Create Failed                 │ │
│ │ ──────────────────────────────────────────────────── │ │
│ │ Description: Validation failed — fix the issues below│ │
│ │ Field: feed_category                                 │ │
│ │   ✗ Category not found in central guild              │ │
│ │ Field: output_channel                                │ │
│ │   ✗ Channel must be an announcement channel          │ │
│ │ Field: concat_channel                                │ │
│ │   ✗ Channel must be a text channel                   │ │
│ │ Field: permissions                                   │ │
│ │   ✗ Missing Send Messages on #stingers               │ │
│ │   ✗ Missing Publish Messages on #stingers            │ │
│ └──────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────┘
```

**Key fields:** Per-field validation bullets (category guild membership, channel types, bot permissions per REQ-UI-002/003).

**Actions:** Administrator corrects category/channel selection or grants bot permissions; retries create.

---

## Network Edit

**Surface:** `/network edit` → interaction response embed (public)

**Slash options:** `key`, `display_name` (optional), `feed_category` (optional), `output_channel` (optional), `concat_channel` (optional)

**Layout:**

```
┌─ Discord client ─────────────────────────────────────────┐
│ /network edit key:stingers display_name:Stingers Network │
│   output_channel:#stingers-new                           │
├─ Interaction response ───────────────────────────────────┤
│ ┌─ Embed ──────────────────────────────────────────────┐ │
│ │ Title: [success] Network Updated                     │ │
│ │ ──────────────────────────────────────────────────── │ │
│ │ Field: key                                           │ │
│ │   stingers                                           │ │
│ │ Field: display_name                                  │ │
│ │   Stingers Network (was: Stingers)                   │ │
│ │ Field: feed_category                                 │ │
│ │   Stingers Feed (unchanged)                          │ │
│ │ Field: output_channel                                │ │
│ │   #stingers-new (was: #stingers)                     │ │
│ │ Field: concat_channel                                │ │
│ │   #concat (unchanged)                                │ │
│ │ Field: enabled                                       │ │
│ │   true                                               │ │
│ └──────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────┘
```

**Key fields:** `key` (required), updated fields with before/after where changed, current `enabled` state.

**Actions:** Administrator updates network routing configuration; may run `/network validate` afterward.

---

## Network List

**Surface:** `/network list` → interaction response embed (public)

**Slash options:** _(none)_

**Layout:**

```
┌─ Discord client ─────────────────────────────────────────┐
│ /network list                                            │
├─ Interaction response ───────────────────────────────────┤
│ ┌─ Embed ──────────────────────────────────────────────┐ │
│ │ Title: Configured Networks                           │ │
│ │ ──────────────────────────────────────────────────── │ │
│ │ Field: stingers                                      │ │
│ │   key: stingers | display: Stingers | enabled: ✓     │ │
│ │ Field: vanguard                                      │ │
│ │   key: vanguard | display: Vanguard | enabled: ✗     │ │
│ │ Footer: 2 networks loaded                            │ │
│ └──────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────┘
```

**Key fields:** Per-network `key`, `display_name`, `enabled` boolean per REQ-UI-004.

**Actions:** Administrator reviews all networks; invokes disable/enable/validate/delete on specific keys.

---

## Network Disable

**Surface:** `/network disable` → interaction response embed (public)

**Slash options:** `key`

**Layout:**

```
┌─ Discord client ─────────────────────────────────────────┐
│ /network disable key:vanguard                            │
├─ Interaction response ───────────────────────────────────┤
│ ┌─ Embed ──────────────────────────────────────────────┐ │
│ │ Title: [success] Network Disabled                    │ │
│ │ ──────────────────────────────────────────────────── │ │
│ │ Field: key                                           │ │
│ │   vanguard                                           │ │
│ │ Field: display_name                                  │ │
│ │   Vanguard                                           │ │
│ │ Field: enabled                                       │ │
│ │   false (routing paused)                             │ │
│ │ Description: Configuration retained; relays skipped  │ │
│ └──────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────┘
```

**Key fields:** `key`, `display_name`, `enabled: false` confirmation.

**Actions:** Administrator pauses routing without deleting configuration; re-enables with `/network enable`.

---

## Network Enable

**Surface:** `/network enable` → interaction response embed (public)

**Slash options:** `key`

**Layout:**

```
┌─ Discord client ─────────────────────────────────────────┐
│ /network enable key:vanguard                             │
├─ Interaction response ───────────────────────────────────┤
│ ┌─ Embed ──────────────────────────────────────────────┐ │
│ │ Title: [success] Network Enabled                     │ │
│ │ ──────────────────────────────────────────────────── │ │
│ │ Field: key                                           │ │
│ │   vanguard                                           │ │
│ │ Field: display_name                                  │ │
│ │   Vanguard                                           │ │
│ │ Field: enabled                                       │ │
│ │   true (routing active)                              │ │
│ └──────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────┘
```

**Key fields:** `key`, `display_name`, `enabled: true` confirmation.

**Actions:** Administrator resumes routing for a previously disabled network.

---

## Network Validate

**Surface:** `/network validate` → interaction response embed (public)

**Slash options:** `key`

**Layout:**

```
┌─ Discord client ─────────────────────────────────────────┐
│ /network validate key:stingers                           │
├─ Interaction response ───────────────────────────────────┤
│ ┌─ Embed ──────────────────────────────────────────────┐ │
│ │ Title: Network Validation — stingers                 │ │
│ │ ──────────────────────────────────────────────────── │ │
│ │ Field: Issues                                        │ │
│ │   ⚠ output_channel: missing Publish Messages         │ │
│ │   ⚠ feed_category: no source channels configured     │ │
│ │   ✓ concat_channel: permissions OK                   │ │
│ │ Footer: 2 issue(s) found                           │ │
│ └──────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────┘
```

**Key fields:** `key`, issue list (channel types, permissions, missing sources) or “no issues” when clean per REQ-UI-006.

**Actions:** Administrator fixes reported issues; re-runs validate until clean.

---

## Network Delete

**Surface:** `/network delete` → interaction response embed (public; direct delete, no confirm step)

**Slash options:** `key`

**Layout:**

```
┌─ Discord client ─────────────────────────────────────────┐
│ /network delete key:vanguard                             │
├─ Interaction response ───────────────────────────────────┤
│ ┌─ Embed ──────────────────────────────────────────────┐ │
│ │ Title: [success] Network Deleted                     │ │
│ │ ──────────────────────────────────────────────────── │ │
│ │ Field: key                                           │ │
│ │   vanguard (removed)                                 │ │
│ │ Description: Network record removed from database.   │ │
│ │   Associated profiles are not deleted automatically. │ │
│ └──────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────┘
```

**Key fields:** Deleted `key`, confirmation that DB record removed per REQ-UI-007.

**Actions:** Administrator removes network configuration; profiles may need manual reassignment.

---

## Profile Sync Success

**Surface:** `/profile sync` → interaction response embed (public)

**Slash options:** `profile_thread`

**Layout:**

```
┌─ Discord client ─────────────────────────────────────────┐
│ /profile sync profile_thread:<#thread-link>             │
├─ Interaction response ───────────────────────────────────┤
│ ┌─ Embed ──────────────────────────────────────────────┐ │
│ │ Title: [success] Profile Synced                      │ │
│ │ ──────────────────────────────────────────────────── │ │
│ │ Field: profile_thread                                │ │
│ │   Vanguard (thread id 1122334455)                  │ │
│ │ Field: server_name                                   │ │
│ │   Vanguard                                           │ │
│ │ Field: source_channel                                │ │
│ │   #vanguard-feed                                     │ │
│ │ Field: network                                       │ │
│ │   stingers                                           │ │
│ │ Field: enabled                                       │ │
│ │   true                                               │ │
│ │ Field: emoji                                         │ │
│ │   <:vanguard_abc123:998877665544332211>              │ │
│ │ Field: warnings                                      │ │
│ │   (none)                                             │ │
│ └──────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────┘
```

**Key fields:** `profile_thread`, parsed YAML fields (`server_name`, `source_channel`, `network`, `enabled`, `display_name`), emoji name/id, warning list per REQ-UI-008.

**Actions:** Administrator confirms manual sync completed; inspects warnings if any.

---

## Profile Sync Error

**Surface:** `/profile sync` → interaction response embed (ephemeral on error)

**Slash options:** `profile_thread`

**Layout:**

```
┌─ Discord client ─────────────────────────────────────────┐
│ /profile sync profile_thread:<#thread-link>             │
├─ Ephemeral response (only you) ──────────────────────────┤
│ ┌─ Embed ──────────────────────────────────────────────┐ │
│ │ Title: [error] Profile Sync Failed                   │ │
│ │ ──────────────────────────────────────────────────── │ │
│ │ Field: profile_thread                                │ │
│ │   Broken Profile (thread id 1122334455)              │ │
│ │ Field: error                                         │ │
│ │   ProfileParseError: duplicate key 'network'         │ │
│ │ Field: details                                       │ │
│ │   ✗ YAML parse failed at line 4                      │ │
│ │   ✗ source_channel not in configured feed category   │ │
│ │ Description: Previous valid profile not overwritten. │ │
│ └──────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────┘
```

**Key fields:** Parse/validation/channel-mapping failure class, field name, line hint; note that prior profile is preserved per §10.

**Actions:** Administrator fixes forum thread YAML or channel mapping; retries sync.

---

## Profile Sync All Summary

**Surface:** `/profile sync-all` → interaction response embed (public)

**Slash options:** _(none)_

**Layout:**

```
┌─ Discord client ─────────────────────────────────────────┐
│ /profile sync-all                                        │
├─ Interaction response ───────────────────────────────────┤
│ ┌─ Embed ──────────────────────────────────────────────┐ │
│ │ Title: Profile Sync All — Summary                    │ │
│ │ ──────────────────────────────────────────────────── │ │
│ │ Field: Totals                                          │ │
│ │   threads: 5 | success: 3 | error: 1 | warn: 1       │ │
│ │ Field: Per-thread outcomes                           │ │
│ │   ✓ Vanguard — synced                                │ │
│ │   ✓ Horizon — synced (1 warning)                     │ │
│ │   ✓ Nexus — synced                                   │ │
│ │   ✗ Broken — ProfileParseError: invalid boolean      │ │
│ │   ⚠ Legacy — emoji degraded (◈ fallback)             │ │
│ └──────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────┘
```

**Key fields:** Per-thread outcome lines (success/error/warn), aggregate counts per REQ-ADV-002.

**Actions:** Administrator triages failed threads individually via `/profile sync` or forum fixes.

---

## Profile Show

**Surface:** `/profile show` → interaction response embed (public)

**Slash options:** `profile_thread`

**Layout:**

```
┌─ Discord client ─────────────────────────────────────────┐
│ /profile show profile_thread:<#thread-link>               │
├─ Interaction response ───────────────────────────────────┤
│ ┌─ Embed ──────────────────────────────────────────────┐ │
│ │ Title: Profile — Vanguard                            │ │
│ │ ──────────────────────────────────────────────────── │ │
│ │ Field: profile_id                                    │ │
│ │   7                                                    │ │
│ │ Field: profile_thread                                │ │
│ │   Vanguard (1122334455)                              │ │
│ │ Field: server_name / display_name                    │ │
│ │   Vanguard / Vanguard                                │ │
│ │ Field: source_channel                                │ │
│ │   #vanguard-feed (4455667788)                        │ │
│ │ Field: network                                       │ │
│ │   stingers (id 2)                                    │ │
│ │ Field: enabled                                       │ │
│ │   true                                               │ │
│ │ Field: emoji                                         │ │
│ │   ◈ (degraded — guild emoji limit reached)           │ │
│ │ Field: degraded_reason                               │ │
│ │   EmojiSyncError: guild emoji capacity reached       │ │
│ └──────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────┘
```

**Key fields:** Stored profile fields, emoji state (`emoji_name`/`emoji_id` or `◈`), `degraded_reason` when applicable per REQ-UI-009/ADV-008.

**Actions:** Administrator inspects profile before enable/disable/repair operations.

---

## Profile Disable

**Surface:** `/profile disable` → interaction response embed (public)

**Slash options:** `profile_thread`

**Layout:**

```
┌─ Discord client ─────────────────────────────────────────┐
│ /profile disable profile_thread:<#thread-link>           │
├─ Interaction response ───────────────────────────────────┤
│ ┌─ Embed ──────────────────────────────────────────────┐ │
│ │ Title: [success] Profile Disabled                    │ │
│ │ ──────────────────────────────────────────────────── │ │
│ │ Field: profile_thread                                │ │
│ │   Vanguard (1122334455)                              │ │
│ │ Field: enabled                                       │ │
│ │   false (relay eligibility off)                      │ │
│ │ Description: Feed messages from this profile will be │ │
│ │   ignored until re-enabled.                          │ │
│ └──────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────┘
```

**Key fields:** `profile_thread`, `enabled: false`, relay eligibility status per REQ-UI-010.

**Actions:** Administrator stops relay for one server profile without deleting record.

---

## Profile Enable

**Surface:** `/profile enable` → interaction response embed (public)

**Slash options:** `profile_thread`

**Layout:**

```
┌─ Discord client ─────────────────────────────────────────┐
│ /profile enable profile_thread:<#thread-link>            │
├─ Interaction response ───────────────────────────────────┤
│ ┌─ Embed ──────────────────────────────────────────────┐ │
│ │ Title: [success] Profile Enabled                     │ │
│ │ ──────────────────────────────────────────────────── │ │
│ │ Field: profile_thread                                │ │
│ │   Vanguard (1122334455)                              │ │
│ │ Field: enabled                                       │ │
│ │   true (relay eligibility on)                        │ │
│ └──────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────┘
```

**Key fields:** `profile_thread`, `enabled: true` confirmation.

**Actions:** Administrator re-enables relay eligibility for a disabled profile.

---

## Profile Repair Emoji Success

**Surface:** `/profile repair-emoji` → interaction response embed (public)

**Slash options:** `profile_thread`

**Layout:**

```
┌─ Discord client ─────────────────────────────────────────┐
│ /profile repair-emoji profile_thread:<#thread-link>     │
├─ Interaction response ───────────────────────────────────┤
│ ┌─ Embed ──────────────────────────────────────────────┐ │
│ │ Title: [success] Emoji Repaired                      │ │
│ │ ──────────────────────────────────────────────────── │ │
│ │ Field: profile_thread                                │ │
│ │   Vanguard (1122334455)                              │ │
│ │ Field: emoji_name                                    │ │
│ │   vanguard_abc123                                    │ │
│ │ Field: emoji_id                                      │ │
│ │   998877665544332211                                 │ │
│ │ Field: emoji                                         │ │
│ │   <:vanguard_abc123:998877665544332211>              │ │
│ │ Field: degraded_reason                               │ │
│ │   (cleared)                                          │ │
│ └──────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────┘
```

**Key fields:** New `emoji_name`, `emoji_id`, rendered emoji mention, cleared `degraded_reason` per REQ-ADV-007.

**Actions:** Administrator recreates missing custom emoji from profile image.

---

## Profile Repair Emoji Degraded

**Surface:** `/profile repair-emoji` → interaction response embed (public)

**Slash options:** `profile_thread`

**Layout:**

```
┌─ Discord client ─────────────────────────────────────────┐
│ /profile repair-emoji profile_thread:<#thread-link>     │
├─ Interaction response ───────────────────────────────────┤
│ ┌─ Embed ──────────────────────────────────────────────┐ │
│ │ Title: [warning] Emoji Repair — Degraded             │ │
│ │ ──────────────────────────────────────────────────── │ │
│ │ Field: profile_thread                                │ │
│ │   Vanguard (1122334455)                              │ │
│ │ Field: emoji                                         │ │
│ │   ◈ (fallback active)                                │ │
│ │ Field: degraded_reason                               │ │
│ │   EmojiSyncError: guild emoji capacity reached       │ │
│ │ Field: guild limit                                   │ │
│ │   50/50 custom emoji slots used                      │ │
│ │ Description: Relay will use ◈ in output headers until│ │
│ │   capacity is freed or emoji is created manually.    │ │
│ └──────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────┘
```

**Key fields:** `◈` fallback indicator, `degraded_reason`, guild emoji limit note per REQ-ADV-008.

**Actions:** Administrator frees emoji slots or runs `/maintenance cleanup-emojis`; retries repair.

---

## Profile Delete

**Surface:** `/profile delete` → interaction response embed (public)

**Slash options:** `profile_thread`

**Layout:**

```
┌─ Discord client ─────────────────────────────────────────┐
│ /profile delete profile_thread:<#thread-link>            │
├─ Interaction response ───────────────────────────────────┤
│ ┌─ Embed ──────────────────────────────────────────────┐ │
│ │ Title: [success] Profile Deleted                     │ │
│ │ ──────────────────────────────────────────────────── │ │
│ │ Field: profile_thread                                │ │
│ │   Vanguard (1122334455)                              │ │
│ │ Field: profile_id                                    │ │
│ │   7 (removed from database)                          │ │
│ │ Field: emoji                                         │ │
│ │   <:vanguard_abc123:998877665544332211> (retained)   │ │
│ │ Description: Custom emoji kept in guild by default   │ │
│ │   per REQ-ADV-006. Forum thread unchanged.           │ │
│ └──────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────┘
```

**Key fields:** Removed `profile_id`, emoji retention note per REQ-UI-011/ADV-006.

**Actions:** Administrator removes profile record; emoji remains unless manually deleted.

---

## Forum profile setup

## Forum Profile Starter Template

**Surface:** Forum thread starter message — **reference layout only (not bot-generated)**

**Slash options:** _(none — operator-authored content)_

**Layout:**

```
┌─ Forum: Server Profiles ─────────────────────────────────┐
│ Thread title: Vanguard                                   │
├─ Starter message (operator-authored) ──────────────────┤
│ ┌─ YAML body zones ────────────────────────────────────┐ │
│ │ server_name: Vanguard                                │ │
│ │ source_channel: <#123456789012345678>                │ │
│ │ enabled: true                                        │ │
│ │ network: stingers                                    │ │
│ │ display_name: Vanguard                               │ │
│ └──────────────────────────────────────────────────────┘ │
│ ┌─ Attachment zone ────────────────────────────────────┐ │
│ │ [profile.png — first valid image used for emoji]     │ │
│ └──────────────────────────────────────────────────────┘ │
│ (Bot does not generate this message — operator template) │
└──────────────────────────────────────────────────────────┘
```

**Key fields:** YAML keys (`server_name`, `source_channel`, `enabled`, `network`, `display_name`), first image attachment per REQ-UI-020/021.

**Actions:** Participating server operator creates thread with YAML body and profile image; bot auto-syncs on create/update (screens 21–23).

---

## Forum Profile Auto Sync Success

**Surface:** Bot reply in profile forum thread (not slash-initiated)

**Slash options:** _(none — triggered by thread create/update)_

**Layout:**

```
┌─ Forum thread: "Vanguard" ───────────────────────────────┐
│ [Starter — operator-authored, see screen 20]             │
│   server_name: Vanguard                                  │
│   source_channel: <#123456789012345678>                  │
│   network: stingers                                      │
│   [attachment: profile.png]                              │
├─ Bot reply ──────────────────────────────────────────────┤
│ ✓ Profile synced                                         │
│   network: stingers | emoji: <:vanguard_abc123:…>        │
│   enabled: true | profile_id: 7                          │
│   warnings: (none)                                       │
└──────────────────────────────────────────────────────────┘
```

**Key fields:** Parsed YAML summary, emoji display, `enabled`, `profile_id`, warnings list per REQ-UI-022/ADV-001.

**Actions:** Operator confirms auto-sync succeeded; no admin action required unless warnings present.

---

## Forum Profile Auto Sync Parse Error

**Surface:** Bot reply in profile forum thread (not slash-initiated)

**Slash options:** _(none)_

**Layout:**

```
┌─ Forum thread: "Broken Profile" ─────────────────────────┐
│ [Starter — invalid YAML]                                 │
│   server_name: Vanguard                                  │
│   enabled: maybe                                         │
│   network: stingers                                      │
│   network: vanguard    ← duplicate key                   │
├─ Bot reply ──────────────────────────────────────────────┤
│ ✗ Profile sync failed                                    │
│   error: duplicate key 'network' (line 5)                │
│   fix the starter message and save to retry.             │
│   (full error logged to #relay-log)                      │
└──────────────────────────────────────────────────────────┘
```

**Key fields:** Concise parse error, field name, line number; reference to relay log for full detail per REQ-UI-022.

**Actions:** Operator fixes YAML in starter message; edit triggers re-sync.

---

## Forum Profile Emoji Degraded Notice

**Surface:** Bot reply in profile forum thread (not slash-initiated)

**Slash options:** _(none)_

**Layout:**

```
┌─ Forum thread: "Vanguard" ───────────────────────────────┐
│ [Starter — valid YAML + profile.png]                     │
├─ Bot reply ──────────────────────────────────────────────┤
│ ⚠ Profile synced with degraded emoji                     │
│   emoji: ◈ (fallback — guild emoji limit reached)        │
│   degraded_reason: EmojiSyncError: capacity reached      │
│   profile saved; relays will use ◈ in output headers.    │
└──────────────────────────────────────────────────────────┘
```

**Key fields:** `◈` fallback, `degraded_reason`, note that profile is saved in degraded state per REQ-ADV-008.

**Actions:** Operator notifies central admin to free emoji capacity or run cleanup; central admin may `/profile repair-emoji`.

---

## Relay diagnostics

## Relay Test Preview

**Surface:** `/relay test` → interaction response embed (public); unpublished test message in output channel

**Slash options:** `source_channel`, `text`, `publish` (optional, default `false`)

**Layout:**

```
┌─ Discord client ─────────────────────────────────────────┐
│ /relay test source_channel:#vanguard-feed                │
│   text:Test announcement body publish:false              │
├─ Interaction response ───────────────────────────────────┤
│ ┌─ Embed ──────────────────────────────────────────────┐ │
│ │ Title: [success] Relay Test Sent (unpublished)       │ │
│ │ ──────────────────────────────────────────────────── │ │
│ │ Field: source_channel                                │ │
│ │   #vanguard-feed                                     │ │
│ │ Field: profile                                       │ │
│ │   Vanguard (id 7)                                    │ │
│ │ Field: network                                       │ │
│ │   stingers → #stingers                               │ │
│ │ Field: publish                                       │ │
│ │   false                                              │ │
│ │ Field: destination_message                           │ │
│ │   link: https://discord.com/channels/…/111           │ │
│ │ Field: preview header                                │ │
│ │   **AuthorName** <:vanguard_abc123:…>                │ │
│ │   Test announcement body                             │ │
│ └──────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────┘
```

**Key fields:** `source_channel`, `text`, `publish=false`, transformed header preview, destination message link per REQ-UI-012/013.

**Actions:** Administrator verifies transformation without publishing; deletes test message if needed.

---

## Relay Test Published

**Surface:** `/relay test` → interaction response embed (public); published crosspost in output channel

**Slash options:** `source_channel`, `text`, `publish=true`

**Layout:**

```
┌─ Discord client ─────────────────────────────────────────┐
│ /relay test source_channel:#vanguard-feed                │
│   text:Published test publish:true                       │
├─ Interaction response ───────────────────────────────────┤
│ ┌─ Embed ──────────────────────────────────────────────┐ │
│ │ Title: [success] Relay Test Published                │ │
│ │ ──────────────────────────────────────────────────── │ │
│ │ Field: source_channel                                │ │
│ │   #vanguard-feed                                     │ │
│ │ Field: publish                                       │ │
│ │   true                                               │ │
│ │ Field: destination_message                           │ │
│ │   link: https://discord.com/channels/…/222           │ │
│ │ Field: status                                        │ │
│ │   published (crossposted)                            │ │
│ │ Field: preview header                                │ │
│ │   **AuthorName** <:vanguard_abc123:…>                │ │
│ │   Published test                                     │ │
│ └──────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────┘
```

**Key fields:** `publish=true`, crosspost/published state, destination message link.

**Actions:** Administrator confirms end-to-end publish path works for downstream followers.

---

## Relay Retry Success

**Surface:** `/relay retry` → interaction response embed (public)

**Slash options:** `source_message` (link or ID)

**Layout:**

```
┌─ Discord client ─────────────────────────────────────────┐
│ /relay retry source_message:<message-link>               │
├─ Interaction response ───────────────────────────────────┤
│ ┌─ Embed ──────────────────────────────────────────────┐ │
│ │ Title: [success] Relay Retry Succeeded               │ │
│ │ ──────────────────────────────────────────────────── │ │
│ │ Field: relay_record_id                               │ │
│ │   42                                                   │ │
│ │ Field: source_message                                │ │
│ │   #vanguard-feed msg 1234567890                      │ │
│ │ Field: previous_status                               │ │
│ │   failed_publish                                     │ │
│ │ Field: new_status                                    │ │
│ │   published                                          │ │
│ │ Field: destination_message_ids                       │ │
│ │   [111] (no duplicate publish created)               │ │
│ │ Field: duration                                      │ │
│ │   1.2s                                               │ │
│ └──────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────┘
```

**Key fields:** `relay_record_id`, source message ref, status transition, destination IDs without duplicate per REQ-UI-014/ADV-011.

**Actions:** Administrator confirms failed relay recovered without duplicate downstream posts.

---

## Relay Retry Failure

**Surface:** `/relay retry` → interaction response embed (ephemeral on unrecoverable error)

**Slash options:** `source_message` (link or ID)

**Layout:**

```
┌─ Discord client ─────────────────────────────────────────┐
│ /relay retry source_message:<message-link>               │
├─ Ephemeral response (only you) ──────────────────────────┤
│ ┌─ Embed ──────────────────────────────────────────────┐ │
│ │ Title: [error] Relay Retry Failed                    │ │
│ │ ──────────────────────────────────────────────────── │ │
│ │ Field: relay_record_id                               │ │
│ │   42                                                   │ │
│ │ Field: source_message                                │ │
│ │   #vanguard-feed msg 1234567890                      │ │
│ │ Field: status                                        │ │
│ │   failed_publish (unchanged)                         │ │
│ │ Field: error_class                                   │ │
│ │   PermissionValidationError                          │ │
│ │ Field: error_message                                 │ │
│ │   Missing Publish Messages on #stingers              │ │
│ │ Field: reattempts                                    │ │
│ │   1 manual retry (automatic retries exhausted)       │ │
│ └──────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────┘
```

**Key fields:** Unrecoverable `error_class`, `error_message`, unchanged status per REQ-UI-014/ADV-010.

**Actions:** Administrator fixes permissions or underlying issue; checks relay log; may not retry non-transient errors.

---

## Relay Status

**Surface:** `/relay status` → interaction response embed (public)

**Slash options:** `source_message` (link or ID)

**Layout:**

```
┌─ Discord client ─────────────────────────────────────────┐
│ /relay status source_message:<message-link>              │
├─ Interaction response ───────────────────────────────────┤
│ ┌─ Embed ──────────────────────────────────────────────┐ │
│ │ Title: Relay Status                                  │ │
│ │ ──────────────────────────────────────────────────── │ │
│ │ Field: relay_record_id                               │ │
│ │   42                                                   │ │
│ │ Field: source_message                                │ │
│ │   channel: 4455667788 | msg: 1234567890              │ │
│ │ Field: profile / network                           │ │
│ │   Vanguard (7) | stingers (2)                        │ │
│ │ Field: status                                        │ │
│ │   published                                          │ │
│ │ Field: destination                                   │ │
│ │   #stingers msg 111222333444555666                   │ │
│ │ Field: error_summary                                 │ │
│ │   (none)                                             │ │
│ │ Field: updated_at                                    │ │
│ │   2026-07-17T12:34:56Z                               │ │
│ └──────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────┘
```

**Key fields:** Source message ID/channel, status enum (`pending`, `sent`, `published`, `failed_send`, `failed_publish`, `partial`), error summary per REQ-ADV-013.

**Actions:** Administrator queries relay outcome for a specific source announcement.

---

## Relay Recent

**Surface:** `/relay recent` → interaction response embed (public)

**Slash options:** `limit` (optional, default 10)

**Layout:**

```
┌─ Discord client ─────────────────────────────────────────┐
│ /relay recent limit:10                                   │
├─ Interaction response ───────────────────────────────────┤
│ ┌─ Embed ──────────────────────────────────────────────┐ │
│ │ Title: Recent Relays                                 │ │
│ │ ──────────────────────────────────────────────────── │ │
│ │ Field: Records                                       │ │
│ │   1. msg …7890 | Vanguard | published | —            │ │
│ │   2. msg …7891 | Horizon  | failed_send | Missing… │ │
│ │   3. msg …7892 | Nexus    | partial | publish fail │ │
│ │   4. msg …7893 | Vanguard | published | —            │ │
│ │   … (up to limit)                                    │ │
│ │ Footer: showing 10 most recent                       │ │
│ └──────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────┘
```

**Key fields:** Per-record source msg ref, profile name, status enum, error summary per REQ-UI-015/ADV-012.

**Actions:** Administrator scans recent activity; drills into `/relay status` or `/relay retry` for failures.

---

## Maintenance

## Maintenance Validate Report

**Surface:** `/maintenance validate` → interaction response embed (public)

**Slash options:** _(none)_

**Layout:**

```
┌─ Discord client ─────────────────────────────────────────┐
│ /maintenance validate                                    │
├─ Interaction response ───────────────────────────────────┤
│ ┌─ Embed ──────────────────────────────────────────────┐ │
│ │ Title: Maintenance Validate Report                   │ │
│ │ ──────────────────────────────────────────────────── │ │
│ │ Field: Networks                                        │ │
│ │   stingers: 1 issue (missing source channels)        │ │
│ │   vanguard: OK                                       │ │
│ │ Field: Profiles                                        │ │
│ │   Vanguard: OK                                       │ │
│ │   Broken: parse error (duplicate key)                │ │
│ │   Legacy: degraded emoji (◈)                         │ │
│ │ Field: Summary                                       │ │
│ │   networks: 2 | profiles: 5 | issues: 3              │ │
│ └──────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────┘
```

**Key fields:** Cross-network and cross-profile issue lines, aggregate counts per REQ-ADV-015.

**Actions:** Administrator triages reported issues via targeted `/network validate` or `/profile sync`.

---

## Maintenance Cleanup Emojis Summary

**Surface:** `/maintenance cleanup-emojis` → interaction response embed (public)

**Slash options:** _(none — unused criteria TBD)_

**Layout:**

```
┌─ Discord client ─────────────────────────────────────────┐
│ /maintenance cleanup-emojis                              │
├─ Interaction response ───────────────────────────────────┤
│ ┌─ Embed ──────────────────────────────────────────────┐ │
│ │ Title: Emoji Cleanup Summary                         │ │
│ │ ──────────────────────────────────────────────────── │ │
│ │ Field: Criteria                                      │ │
│ │   unused profile emojis (definition TBD)             │ │
│ │ Field: Removed                                       │ │
│ │   3 emoji (orphaned, no profile reference)           │ │
│ │ Field: Retained                                      │ │
│ │   47 emoji (active profiles or manual)               │ │
│ │ Field: Skipped                                       │ │
│ │   0 (in use by enabled profiles)                     │ │
│ │ Footer: guild slots 47/50 after cleanup            │ │
│ └──────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────┘
```

**Key fields:** Removed vs retained counts, criteria placeholder note per REQ-UI-018.

**Actions:** Administrator reviews cleanup results; may retry `/profile repair-emoji` for degraded profiles.

---

## Maintenance Rebuild Cache

**Surface:** `/maintenance rebuild-cache` → interaction response embed (public)

**Slash options:** _(none)_

**Layout:**

```
┌─ Discord client ─────────────────────────────────────────┐
│ /maintenance rebuild-cache                               │
├─ Interaction response ───────────────────────────────────┤
│ ┌─ Embed ──────────────────────────────────────────────┐ │
│ │ Title: [success] Cache Rebuilt                       │ │
│ │ ──────────────────────────────────────────────────── │ │
│ │ Field: networks_reloaded                             │ │
│ │   2                                                    │ │
│ │ Field: profiles_reloaded                             │ │
│ │   5                                                    │ │
│ │ Field: source                                          │ │
│ │   ./data/relay.db                                      │ │
│ │ Field: duration                                        │ │
│ │   128ms                                                │ │
│ └──────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────┘
```

**Key fields:** Reload confirmation, network/profile counts reloaded from SQLite per REQ-UI-017/ADV-014.

**Actions:** Administrator reloads in-memory caches after manual DB edits or suspected drift.

---

## Maintenance Permissions Report

**Surface:** `/maintenance permissions` → interaction response embed (public)

**Slash options:** _(none)_

**Layout:**

```
┌─ Discord client ─────────────────────────────────────────┐
│ /maintenance permissions                                 │
├─ Interaction response ───────────────────────────────────┤
│ ┌─ Embed ──────────────────────────────────────────────┐ │
│ │ Title: Permissions Report                            │ │
│ │ ──────────────────────────────────────────────────── │ │
│ │ Field: Profile forum (Server Profiles)               │ │
│ │   ✓ View Channel  ✓ Read Message History             │ │
│ │   ✓ Send Messages in Threads  ✓ Manage Threads     │ │
│ │ Field: Feed source channels                          │ │
│ │   ✓ #vanguard-feed — View, Read History              │ │
│ │   ✗ #horizon-feed — missing View Channel             │ │
│ │ Field: Concat channel (#concat)                      │ │
│ │   ✓ View  ✓ Send  ✓ Embed Links  ✓ Attach Files      │ │
│ │ Field: Output announcement (#stingers)               │ │
│ │   ✓ View  ✓ Send  ✓ Embed  ✓ Attach  ✓ Publish      │ │
│ │ Field: Guild emoji management                        │ │
│ │   ✓ Create Expressions  ✓ Manage Expressions         │ │
│ │ Footer: 1 failure — fix before relaying              │ │
│ └──────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────┘
```

**Key fields:** Checklist per §18 surfaces (forum, feed, concat, output, emoji) using discord.py permission names per REQ-UI-016/025.

**Actions:** Administrator grants missing permissions; re-runs report until clean.

---

## Relay log channel

## Relay Log Relay Completed

**Surface:** Plain message in `RELAY_LOG_CHANNEL_ID` (#relay-log)

**Slash options:** _(none — bot-generated on relay success)_

**Layout:**

```
┌─ #relay-log ─────────────────────────────────────────────┐
│ [RELAY] relay_completed                                  │
│ source: #vanguard-feed (msg 1234567890)                  │
│ profile: Vanguard (id 7) | network: stingers (id 2)    │
│ dest: #stingers (msg 111222333444555666)                 │
│ status: published                                        │
│ duration: 842ms                                          │
└──────────────────────────────────────────────────────────┘
```

**Key fields:** Event tag `relay_completed`, source msg/channel IDs, profile/network IDs, destination channel/msg IDs, `status: published`, `duration_ms` per §17.

**Actions:** Administrator confirms successful send and publish in audit trail.

---

## Relay Log Failed Send

**Surface:** Plain message in #relay-log

**Slash options:** _(none)_

**Layout:**

```
┌─ #relay-log ─────────────────────────────────────────────┐
│ [RELAY] failed_send                                      │
│ source: #vanguard-feed (msg 1234567890)                  │
│ profile: Vanguard (id 7) | network: stingers (id 2)    │
│ dest: #stingers                                          │
│ error: MissingAccess — bot lacks Send Messages           │
│ duration: 842ms                                          │
└──────────────────────────────────────────────────────────┘
```

**Key fields:** Event tag `failed_send`, send failure `error_class` and message, full routing context per §17/ADV-010.

**Actions:** Administrator fixes output channel permissions; may `/relay retry`.

---

## Relay Log Failed Publish

**Surface:** Plain message in #relay-log

**Slash options:** _(none)_

**Layout:**

```
┌─ #relay-log ─────────────────────────────────────────────┐
│ [RELAY] failed_publish                                   │
│ source: #vanguard-feed (msg 1234567891)                  │
│ profile: Horizon (id 8) | network: stingers (id 2)     │
│ dest: #stingers (msg 111222333444555667 — sent, not pub)│
│ error: Forbidden — Publish Messages denied               │
│ duration: 1204ms                                         │
└──────────────────────────────────────────────────────────┘
```

**Key fields:** Event tag `failed_publish`, destination message sent but not published, publish error class.

**Actions:** Administrator grants Publish Messages; `/relay retry` to complete publish without duplicate send.

---

## Relay Log Partial Relay

**Surface:** Plain message in #relay-log

**Slash options:** _(none)_

**Layout:**

```
┌─ #relay-log ─────────────────────────────────────────────┐
│ [RELAY] partial                                          │
│ source: #nexus-feed (msg 1234567892)                     │
│ profile: Nexus (id 9) | network: stingers (id 2)       │
│ dest: #stingers (msg 111…668 sent | publish pending)     │
│ status: partial — sent but not published                 │
│ error: transient Discord 503 during publish              │
│ duration: 3100ms                                         │
└──────────────────────────────────────────────────────────┘
```

**Key fields:** Event tag `partial`, multi-step state (sent vs published), error summary for triage.

**Actions:** Administrator runs `/relay retry`; monitors for duplicate publish prevention.

---

## Relay Log Profile Sync

**Surface:** Plain message in #relay-log

**Slash options:** _(none)_

**Layout:**

```
┌─ #relay-log ─────────────────────────────────────────────┐
│ [RELAY] profile_sync                                     │
│ thread: Vanguard (1122334455)                            │
│ profile_id: 7 | network: stingers                        │
│ outcome: success                                         │
│ warnings: display_name fell back to server_name          │
│ duration: 456ms                                          │
└──────────────────────────────────────────────────────────┘
```

**Key fields:** Event tag `profile_sync`, thread ID, outcome (`success`/`failed`), warnings or full error context per §17/REQ-UI-022.

**Actions:** Administrator audits sync activity; cross-checks forum thread reply for operator-facing summary.

---

## Relay Log Degraded Emoji

**Surface:** Plain message in #relay-log

**Slash options:** _(none)_

**Layout:**

```
┌─ #relay-log ─────────────────────────────────────────────┐
│ [RELAY] degraded_emoji                                   │
│ profile: Legacy (id 10) | thread: 1122334466           │
│ emoji: ◈ (fallback active)                               │
│ degraded_reason: EmojiSyncError — guild limit 50/50      │
│ action: profile saved; relays use ◈ in headers         │
└──────────────────────────────────────────────────────────┘
```

**Key fields:** Event tag `degraded_emoji`, `◈` fallback, `degraded_reason`, guild capacity note per REQ-ADV-008.

**Actions:** Administrator frees emoji slots or runs cleanup; `/profile repair-emoji` when capacity available.

---

## Relay Log Source Message Edited

**Surface:** Plain message in #relay-log

**Slash options:** _(none)_

**Layout:**

```
┌─ #relay-log ─────────────────────────────────────────────┐
│ [RELAY] source_edited                                    │
│ source: #vanguard-feed (msg 1234567890)                  │
│ profile: Vanguard (id 7) | network: stingers             │
│ relay_record_id: 42 | dest msg: 111…666                  │
│ notice: v1 does NOT auto-edit downstream announcement    │
│ hint: use /relay refresh (post-MVP) if sync desired      │
└──────────────────────────────────────────────────────────┘
```

**Key fields:** Event tag `source_edited`, source msg ref, v1 no auto-edit notice per §8.4.

**Actions:** Administrator aware downstream announcement is stale; manual intervention if needed (v1 logs only).

---

## Relay Log Source Message Deleted

**Surface:** Plain message in #relay-log

**Slash options:** _(none)_

**Layout:**

```
┌─ #relay-log ─────────────────────────────────────────────┐
│ [RELAY] source_deleted                                   │
│ source: #vanguard-feed (msg 1234567890 — deleted)        │
│ profile: Vanguard (id 7) | network: stingers             │
│ relay_record_id: 42 | dest msg: 111…666 (still live)     │
│ notice: v1 does NOT auto-delete downstream announcement  │
└──────────────────────────────────────────────────────────┘
```

**Key fields:** Event tag `source_deleted`, source msg ref, v1 no auto-delete notice per §8.5.

**Actions:** Administrator manually removes stale downstream announcement if desired (v1 logs only).

---

## Error and degraded states

## Relay Output Degraded Header

**Surface:** Published announcement in network output channel (passive downstream view; not slash-initiated)

**Slash options:** _(none)_

**Layout:**

```
┌─ #stingers (published announcement) ─────────────────────┐
│ **AuthorName** ◈                                         │
│                                                          │
│ Original message body text from the source announcement… │
│                                                          │
│ (attachments/embeds relayed below header per §12–§14)    │
└──────────────────────────────────────────────────────────┘
```

**Key fields:** Sanitized author name, `◈` fallback instead of custom emoji when degraded, unchanged source body below header per §12/REQ-ADV-008.

**Actions:** Downstream followers read announcement; central admin resolves degraded emoji via profile repair.

---

## Slash Command Transient Error

**Surface:** Any admin slash command → ephemeral interaction response on transient Discord API failure

**Slash options:** _(example)_ `/relay retry source_message:<link>`

**Layout:**

```
┌─ Ephemeral response (only you) ──────────────────────────┐
│ ⚠ Transient error — please try again                     │
│                                                          │
│ Discord API returned HTTP 503 (Service Unavailable)    │
│ or rate limit (429).                                     │
│                                                          │
│ Automatic retries exhausted for this interaction.        │
│ Wait a moment and re-run the command.                    │
│                                                          │
│ Command: /relay retry                                    │
└──────────────────────────────────────────────────────────┘
```

**Key fields:** Transient error class (rate limit 429, server error 503), retry hint, attempted command per REQ-ADV-010.

**Actions:** Administrator waits and retries; checks `/status` if errors persist.

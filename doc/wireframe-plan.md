# Wireframe Plan — The Network

Discord admin interaction flows for MVP (phases 1–8): slash commands, embeds, forum thread replies, and relay log channel messages. Wireframes cover central-guild administrator tooling and participating-server operator forum setup — **not** game UI, Foundry sheets, or downstream follower slash commands.

## Admin slash commands

1. Bot Status
   - **Target user:** Central guild administrator
   - **Primary action:** Check bot connectivity, guild validation, database status, and loaded network/profile counts
   - **discord.py surface:** slash command, embed
   - **REQ trace:** REQ-UI-019

2. Admin Permission Denied
   - **Target user:** Non-admin user (lacks `Manage Guild` and configured moderator role, if any)
   - **Primary action:** Attempt a restricted admin command and receive a clear denial
   - **discord.py surface:** slash command (ephemeral error)
   - **REQ trace:** REQ-UI-026

3. Network Create Success
   - **Target user:** Central guild administrator
   - **Primary action:** Register a new network route with key, display name, feed category, output channel, and optional concat channel
   - **discord.py surface:** slash command, embed
   - **REQ trace:** REQ-UI-001, REQ-UI-002, REQ-UI-003

4. Network Create Validation Error
   - **Target user:** Central guild administrator
   - **Primary action:** Fix invalid category, channel type, or missing bot permissions after a failed create
   - **discord.py surface:** slash command, embed
   - **REQ trace:** REQ-UI-002, REQ-UI-003

5. Network Edit
   - **Target user:** Central guild administrator
   - **Primary action:** Update network fields (display name, feed category, output channel, concat channel)
   - **discord.py surface:** slash command, embed
   - **REQ trace:** plan.md §9.1 `/network edit`

6. Network List
   - **Target user:** Central guild administrator
   - **Primary action:** Review all configured networks with key, display name, and enabled state
   - **discord.py surface:** slash command, embed
   - **REQ trace:** REQ-UI-004

7. Network Disable
   - **Target user:** Central guild administrator
   - **Primary action:** Pause routing for a network without deleting its configuration
   - **discord.py surface:** slash command, embed
   - **REQ trace:** REQ-UI-005

8. Network Enable
   - **Target user:** Central guild administrator
   - **Primary action:** Resume routing for a previously disabled network
   - **discord.py surface:** slash command, embed
   - **REQ trace:** REQ-UI-005

9. Network Validate
   - **Target user:** Central guild administrator
   - **Primary action:** Run a consistency check on one network and review reported issues
   - **discord.py surface:** slash command, embed
   - **REQ trace:** REQ-UI-006

10. Network Delete
    - **Target user:** Central guild administrator
    - **Primary action:** Remove a network record from the database
    - **discord.py surface:** slash command, embed
    - **REQ trace:** REQ-UI-007

11. Profile Sync Success
    - **Target user:** Central guild administrator
    - **Primary action:** Parse a forum thread, sync emoji, save profile, and review warnings
    - **discord.py surface:** slash command, embed
    - **REQ trace:** REQ-UI-008, REQ-ADV-001

12. Profile Sync Error
    - **Target user:** Central guild administrator
    - **Primary action:** Recover from parse, validation, or channel-mapping failure on manual sync
    - **discord.py surface:** slash command, embed
    - **REQ trace:** REQ-UI-008, REQ-UI-022

13. Profile Sync All Summary
    - **Target user:** Central guild administrator
    - **Primary action:** Bulk sync all forum threads and review per-thread outcomes in a summary
    - **discord.py surface:** slash command, embed
    - **REQ trace:** REQ-ADV-002

14. Profile Show
    - **Target user:** Central guild administrator
    - **Primary action:** Inspect stored profile fields, emoji state, and degraded reason if any
    - **discord.py surface:** slash command, embed
    - **REQ trace:** REQ-UI-009, REQ-ADV-008

15. Profile Disable
    - **Target user:** Central guild administrator
    - **Primary action:** Stop relay eligibility for one server profile
    - **discord.py surface:** slash command, embed
    - **REQ trace:** REQ-UI-010, REQ-ADV-006

16. Profile Enable
    - **Target user:** Central guild administrator
    - **Primary action:** Re-enable relay eligibility for a disabled profile
    - **discord.py surface:** slash command, embed
    - **REQ trace:** REQ-UI-010

17. Profile Repair Emoji Success
    - **Target user:** Central guild administrator
    - **Primary action:** Recreate a missing custom emoji for a profile
    - **discord.py surface:** slash command, embed
    - **REQ trace:** REQ-ADV-007

18. Profile Repair Emoji Degraded
    - **Target user:** Central guild administrator
    - **Primary action:** Acknowledge emoji recreation failure due to guild limits and `◈` fallback
    - **discord.py surface:** slash command, embed
    - **REQ trace:** REQ-ADV-008

19. Profile Delete
    - **Target user:** Central guild administrator
    - **Primary action:** Remove a profile record while retaining the associated emoji by default
    - **discord.py surface:** slash command, embed
    - **REQ trace:** REQ-UI-011, REQ-ADV-006

## Forum profile setup

20. Forum Profile Starter Template
    - **Target user:** Participating server operator
    - **Primary action:** Configure YAML key-value body and attach a profile image on a new forum thread (reference layout; not bot-generated)
    - **discord.py surface:** forum thread reply (reference only)
    - **REQ trace:** REQ-UI-020, REQ-UI-021

21. Forum Profile Auto Sync Success
    - **Target user:** Participating server operator
    - **Primary action:** Confirm the thread was parsed, emoji synced, and profile saved after thread creation or update
    - **discord.py surface:** forum thread reply
    - **REQ trace:** REQ-UI-022, REQ-ADV-001

22. Forum Profile Auto Sync Parse Error
    - **Target user:** Participating server operator
    - **Primary action:** Fix invalid YAML, IDs, or channel mapping reported in the thread
    - **discord.py surface:** forum thread reply
    - **REQ trace:** REQ-UI-022

23. Forum Profile Emoji Degraded Notice
    - **Target user:** Participating server operator
    - **Primary action:** Understand `◈` emoji fallback and the profile `degraded_reason` after guild emoji limit failure
    - **discord.py surface:** forum thread reply
    - **REQ trace:** REQ-ADV-008

## Relay diagnostics

24. Relay Test Preview
    - **Target user:** Central guild administrator
    - **Primary action:** Simulate message transformation and send an unpublished test to the output channel (`publish=false` default)
    - **discord.py surface:** slash command, embed
    - **REQ trace:** REQ-UI-012, REQ-UI-013

25. Relay Test Published
    - **Target user:** Central guild administrator
    - **Primary action:** Send and publish a test message with `publish=true`
    - **discord.py surface:** slash command, embed
    - **REQ trace:** REQ-UI-012, REQ-UI-013

26. Relay Retry Success
    - **Target user:** Central guild administrator
    - **Primary action:** Recover a failed or incomplete relay without creating duplicate published messages
    - **discord.py surface:** slash command, embed
    - **REQ trace:** REQ-UI-014, REQ-ADV-011

27. Relay Retry Failure
    - **Target user:** Central guild administrator
    - **Primary action:** Diagnose an unrecoverable retry after send/publish reattempt
    - **discord.py surface:** slash command, embed
    - **REQ trace:** REQ-UI-014, REQ-ADV-010

28. Relay Status
    - **Target user:** Central guild administrator
    - **Primary action:** Query relay status for a specified source message
    - **discord.py surface:** slash command, embed
    - **REQ trace:** REQ-ADV-013

29. Relay Recent
    - **Target user:** Central guild administrator
    - **Primary action:** List recent relay records with status and error summary
    - **discord.py surface:** slash command, embed
    - **REQ trace:** REQ-UI-015, REQ-ADV-012

## Maintenance

30. Maintenance Validate Report
    - **Target user:** Central guild administrator
    - **Primary action:** Run a full configuration consistency check across networks and profiles
    - **discord.py surface:** slash command, embed
    - **REQ trace:** REQ-ADV-015

31. Maintenance Cleanup Emojis Summary
    - **Target user:** Central guild administrator
    - **Primary action:** Review removed vs retained emojis after administrative cleanup (unused criteria TBD)
    - **discord.py surface:** slash command, embed
    - **REQ trace:** REQ-UI-018

32. Maintenance Rebuild Cache
    - **Target user:** Central guild administrator
    - **Primary action:** Reload network and profile caches from SQLite
    - **discord.py surface:** slash command, embed
    - **REQ trace:** REQ-UI-017, REQ-ADV-014

33. Maintenance Permissions Report
    - **Target user:** Central guild administrator
    - **Primary action:** Verify bot permissions on profile forum, feed sources, concat channel, output announcement channel, and emoji management
    - **discord.py surface:** slash command, embed
    - **REQ trace:** REQ-UI-016, REQ-UI-025

## Relay log channel

34. Relay Log Relay Completed
    - **Target user:** Central guild administrator
    - **Primary action:** Confirm successful send and publish for a relay event
    - **discord.py surface:** channel message
    - **REQ trace:** REQ-UI-023, REQ-ADV-009

35. Relay Log Failed Send
    - **Target user:** Central guild administrator
    - **Primary action:** Investigate a relay that failed during send
    - **discord.py surface:** channel message
    - **REQ trace:** REQ-UI-023, REQ-ADV-010

36. Relay Log Failed Publish
    - **Target user:** Central guild administrator
    - **Primary action:** Investigate a relay that sent but failed to publish
    - **discord.py surface:** channel message
    - **REQ trace:** REQ-UI-023, REQ-ADV-010

37. Relay Log Partial Relay
    - **Target user:** Central guild administrator
    - **Primary action:** Recover or triage a multi-step relay left in partial state
    - **discord.py surface:** channel message
    - **REQ trace:** REQ-UI-023, REQ-ADV-010

38. Relay Log Profile Sync
    - **Target user:** Central guild administrator
    - **Primary action:** Audit profile sync outcome (success, warnings, or failure context)
    - **discord.py surface:** channel message
    - **REQ trace:** REQ-UI-023, REQ-UI-022

39. Relay Log Degraded Emoji
    - **Target user:** Central guild administrator
    - **Primary action:** Notice guild emoji capacity issue affecting a profile
    - **discord.py surface:** channel message
    - **REQ trace:** REQ-UI-023, REQ-ADV-008

40. Relay Log Source Message Edited
    - **Target user:** Central guild administrator
    - **Primary action:** Know a source message changed (v1 does not auto-edit downstream)
    - **discord.py surface:** channel message
    - **REQ trace:** REQ-UI-023

41. Relay Log Source Message Deleted
    - **Target user:** Central guild administrator
    - **Primary action:** Know a source message was removed (v1 does not auto-delete downstream)
    - **discord.py surface:** channel message
    - **REQ trace:** REQ-UI-023

## Error and degraded states

42. Relay Output Degraded Header
    - **Target user:** Downstream follower (passive; N/A for slash interaction)
    - **Primary action:** Read a relay announcement that uses `◈` emoji fallback in the output header
    - **discord.py surface:** channel message (output announcement)
    - **REQ trace:** REQ-ADV-008

43. Slash Command Transient Error
    - **Target user:** Central guild administrator
    - **Primary action:** Retry after rate limit or transient Discord API error
    - **discord.py surface:** slash command (ephemeral)
    - **REQ trace:** REQ-ADV-010

## Out of scope for wireframes

- Web dashboard or non-Discord admin UI
- Game UI, Foundry actor sheets, or HUD surfaces
- Downstream follower slash commands
- `/relay refresh` (post-MVP edit synchronization)
- Automatic edit/delete propagation UI for published announcements (v1 logs only)
- Concat channel audit mirror as a separate wireframe (covered under relay log admin diagnosis unless engineer requests a distinct screen)

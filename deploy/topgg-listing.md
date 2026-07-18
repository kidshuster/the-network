# top.gg listing copy — paste into your bot page

## Tags

`utility`, `moderation`, `announcements`, `community`

## Short description (≤ 250 chars)

Relay partner server announcements through a central hub. Channel Follow in, formatted embeds out — with per-server profiles, networks, and published crossposts.

## Long description

**The Network** is a central-guild relay bot for Discord announcement networks.

Partner communities use **Channel Follow** to send announcements into dedicated feed channels. The bot transforms each message into a clean embed (server icon, display name, text, and images) and **publishes** it to your network's output announcement channel for downstream followers.

### Features

- **Networks** — create relay infrastructure with `/network create`
- **Servers** — add partners with `/server create` (feed channel + profile forum thread + emoji)
- **Automatic relay** — Channel Follow webhook messages are filtered, formatted, and published
- **Embed formatting** — server profile emoji as author icon, display name as author, preserved content and images
- **Admin commands** — enable/disable networks and servers, status, list, delete with cascade cleanup

### Setup (central guild)

1. Invite the bot with Manage Channels, Manage Roles, Manage Webhooks, and Manage Expressions.
2. Run `/network create` with your output announcement channel.
3. Run `/server create` for each partner server.
4. Set up Channel Follow from each partner's announcement channel into their feed channel.

### Commands

**Network:** `create`, `delete`, `status`, `list`  
**Server:** `create`, `delete`, `enable`, `disable`, `status`, `list`

### Notes

This bot is designed for a **single central server** (hub model), not multi-tenant public use. One instance serves one relay hub.

## Prefix

`/`

## Support server

*(Add your support Discord invite URL)*

## Invite URL

```
https://discord.com/oauth2/authorize?client_id=YOUR_APPLICATION_ID&permissions=536871936&scope=bot+applications.commands
```

Replace `YOUR_APPLICATION_ID` with your bot's application ID from the [Discord Developer Portal](https://discord.com/developers/applications).

## GitHub / website

*(Add repository or docs URL if public)*

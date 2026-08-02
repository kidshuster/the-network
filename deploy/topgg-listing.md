# top.gg listing copy — paste into your bot page

## Tags

`utility`, `moderation`, `announcements`, `community`

## Short description (≤ 250 chars)

Relay partner server announcements through a central hub. Channel Follow in, formatted embeds out — with per-server profiles, networks, and published crossposts.

## Long description

**The Network** is a central-guild relay bot for Discord announcement networks.

Partner communities use **Channel Follow** to send announcements into dedicated feed channels. The bot transforms each message into a clean embed (server icon, display name, text, and images) and **publishes** it to your network's output announcement channel for downstream followers.

### Features

- **Hub layout** — `/server init` sets up Moderation + The Network categories
- **Networks** — register announcement feeds from **#commands** (Create Network button)
- **Clients** — partners join via **Join Network** in `#join-the-network`; moderators approve in `#join-requests`
- **Per-client channels** — each client gets a category with `#network-profile`, `{nkey}-publish`, and `{nkey}-subscribe`
- **Automatic relay** — Channel Follow webhook messages are filtered, formatted, and published to subscriber channels
- **Blacklist** — clients can block specific publishers on a network subscription

### Setup (central guild)

1. Invite the bot with Manage Channels, Manage Roles, Manage Webhooks, and Manage Expressions.
2. Run `/server init` to create hub categories and channels.
3. Run `/server init`, then use **Create Network** in `#commands` for each announcement network.
4. Clients use **Join Network** in `#join-the-network`; approve requests in `#join-requests`.
5. Clients subscribe to networks from buttons on their `#network-profile` channel.
6. Set up Channel Follow from each client's announcement channel into their `{nkey}-publish` channel.

### Commands

**Server:** `init`, `uninit`, `sync-join-guide`  

Network and join-request administration uses channel buttons: **Create Network** / **Delete Network** in `#commands`, **Join Network** in `#join-the-network`, and **Accept** / **Deny** in `#join-requests`.

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

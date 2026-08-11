# Widget configuration

This directory is declarative: YAML controls layout, permissions, sticky content,
changelog releases, embeds, popups, and modals. Executable loaders, recipes,
views, and APIs live under `bot/core/`.

## Layout

- `channels/layout/` — channel layout and permission profiles
- `channels/stickies/` — sticky metadata and versions
- `channels/templates/` — content installed into managed channels
- `changelog/` — release-note data
- `templates/embeds/` — interaction and command embeds
- `templates/popups/` — plain ephemeral responses
- `templates/modals/` — modal titles and fields

## Placeholders

Use `{name}` in strings. At runtime Python passes values via `render_embed("template_id", name=value)` or `render_text("popup_id", name=value)`.

Unknown `{placeholders}` are left unchanged so Discord markdown like `{server}` in prose is safe only if you avoid that exact token.

## Optional embed fields

Add `when: "{some_key}"` on a field to hide it when the substituted value is empty or zero.

## Colours

Named colours: `blurple`, `green`, `red`, `gold`, `orange`, `dark_grey`. Pass `colour=` in render context to override.

## Sticky versions

Sticky metadata and versions live in `bot/widgets/channels/stickies/stickies.yaml`.

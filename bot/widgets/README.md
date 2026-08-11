# Widgets

Recipes, views, and user-facing Discord presentation live here. Edit YAML templates to change
embeds, popups, and modal labels without touching recipes or core APIs. All failure embeds use
the single dynamic `templates/embeds/error.yaml` template.

## Layout

- `recipes/` — registered application operations
- `views/` — Discord buttons, dropdowns, and modals
- `templates/embeds/` — interaction and command embeds
- `templates/popups/` — plain ephemeral responses
- `templates/modals/` — modal titles and fields

Content installed into managed channels belongs in `bot/channels/templates/` instead.

## Placeholders

Use `{name}` in strings. At runtime Python passes values via `render_embed("template_id", name=value)` or `render_text("popup_id", name=value)`.

Unknown `{placeholders}` are left unchanged so Discord markdown like `{server}` in prose is safe only if you avoid that exact token.

## Optional embed fields

Add `when: "{some_key}"` on a field to hide it when the substituted value is empty or zero.

## Colours

Named colours: `blurple`, `green`, `red`, `gold`, `orange`, `dark_grey`. Pass `colour=` in render context to override.

## Sticky versions

Sticky metadata and versions live in `bot/channels/stickies/stickies.yaml`.

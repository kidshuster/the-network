# Presentation templates

User-facing Discord presentation lives here as YAML files. Edit these files to change embeds,
popups, and modal labels without touching recipes or core APIs. All failure embeds use the
single dynamic `embeds/error.yaml` template.

## Layout

- `embeds/` — Discord embed messages (one file per message id)
- `popups/` — Plain ephemeral text responses
- `modals/` — Modal titles and field definitions

## Placeholders

Use `{name}` in strings. At runtime Python passes values via `render_embed("template_id", name=value)` or `render_text("popup_id", name=value)`.

Unknown `{placeholders}` are left unchanged so Discord markdown like `{server}` in prose is safe only if you avoid that exact token.

## Optional embed fields

Add `when: "{some_key}"` on a field to hide it when the substituted value is empty or zero.

## Colours

Named colours: `blurple`, `green`, `red`, `gold`, `orange`, `dark_grey`. Pass `colour=` in render context to override.

## Sticky versions

Hub sticky footers use `{version}` — bump the version constant in the sticky service module when you change copy so the bot refreshes pinned messages.

# Widget Hardening Plan (post c1bdc95)

Baseline: `refactor` @ `30ffab7`. Primary tagged-template draft refactor shipped in `c1bdc95`.
Do not repeat completed migration/reorg work. Preserve app / features / core.

## 1. Disabled interactables require recipes — DONE

`build()` requires a registered recipe handler for every static and dynamic
interactable, including disabled controls. Covered by `test_widget_hardening.py`.

## 2. Strict RecipeRegistry inputs — DONE

`RecipeRegistry.run` rejects unexpected kwargs and missing required params.
No silent filtering. Covered by `test_recipe_registry.py` / `test_widget_hardening.py`.

## 3. Submitted vs persistent arguments — DONE

Submitted modal/select values stay separate from persistent `RecipeHandler`
arguments. Key collisions raise `TemplateRenderError`.

## 4. Migration through normal dispatch — DONE

Migration callback overrides removed. `ui.migrate.store|confirm|cancel` update
`RenderedView.resolutions` / `decision` through the normal recipe path.

## 5. Typed custom-ID round trips — DONE

Encode uses `!n` / `!b0`/`!b1` / `!i…` / `!s…`. Round-trips preserve types.
Malformed/oversized IDs reject. Legacy `tn:` + transitional untyped tn1 remain
in `custom_id_legacy.py`.

## 6. Reject Discord-limit violations — DONE

Drafts reject over-limit select labels/placeholders/descriptions and option
counts instead of truncating or clamping.

## 7. Mutation recipe actor authorization — DONE

UI mutation recipes authorize via `interaction_actor` / `require_manage_guild` /
`require_client_member`. Service-path network create/delete require `moderator`.

## 8. Presenter exception handling — DONE

Presenter failures propagate through `_present` / central error path.
`present.network.create` no longer emits false `Done.` on bad shapes.
Message edit cleanup catches only `discord.HTTPException`.

## 9. Legacy compatibility isolation — DONE

See `bot/app/widgets/custom_id_legacy.py` module docstring for removal condition:
delete after the next sticky rewrite cycle once no managed message still carries
`tn:` or transitional `tn1:ui.modal` / `tn1:ui.view` IDs.

## 10. Tasklist honesty — DONE

`WIDGET_TASKLIST.md` hardening section checked only where tests prove the guarantee.
Docker / GHA left unchecked until this push’s Actions run is green.

## Validation

- [x] Ruff
- [x] mypy
- [x] unit
- [x] mock smoke (`./test --dev`)
- [x] malformed-state stress
- [x] install-bundle
- [ ] Docker / GitHub Actions (after push)

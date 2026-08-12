# Widget Template Refactor Tasklist

Use this checklist with `plan.md` and `CURSOR_ARCHITECTURE_GOALS.md`. Do not perform another
top-level reorganization. Preserve the existing `app` / `features` / `core` boundaries and all
validated behavior.

## Baseline and inventory

- [x] Confirm the working branch contains commit `8003569` or its changes.
- [x] Run the current Ruff, mypy, unit, mock smoke, and malformed-state gates.
- [x] Record production Python LOC before editing.
- [x] Record LOC for `bot/app/widgets`, `bot/features/widgets`, and `bot/features/recipes`.
- [x] Inventory every view, modal, embed, popup, sticky, and channel-content template.
- [x] Inventory every interactive button, select, and modal submission.
- [x] Map every interactable to its current trigger, recipe, authorization, inputs, and presenter.
- [x] Identify static interactables whose label/style/row should return to YAML.
- [x] Identify genuinely dynamic repeated components that require slots.
- [x] Identify every special dispatcher action such as `ui.modal:*`, `ui.view:*`, or `ui.dismiss`.
- [x] Identify all legacy custom-ID formats still present on deployed persistent messages.

## Template schema

- [x] Require a unique `tag` for every static interactive component.
- [x] Keep tags local to one template.
- [x] Keep tags free of record IDs and runtime state.
- [x] Support named slots for repeated dynamic components.
- [x] Keep text, labels, descriptions, styles, emoji, rows, and ordering in YAML.
- [x] Support placeholders in every user-facing template string.
- [x] Validate button styles as literals; never silently fall back.
- [x] Reject executable/policy keys such as `require`, `inject`, `store`, `finish`, `on_success`,
  `on_error`, `field_map`, `options_from`, `foreach`, `when`, and `disabled_when`.
- [x] Reject template-level trigger, recipe, custom-ID, authorization, repository, or service data.
- [x] Validate duplicate tags and slots during template loading.
- [x] Validate Discord field, label, component, row, modal, and text limits during startup.

## Draft API

- [x] Add `ViewDraft` and `ModalDraft` types that are not Discord UI objects.
- [x] Make `templates.view(template_id, **values)` return `ViewDraft`.
- [x] Make `templates.modal(template_id, **values)` return `ModalDraft`.
- [x] Add explicit `bind(tag, recipe_handler)` to drafts.
- [x] Add `fill(slot, components)` or `add(slot, component)` for dynamic components.
- [x] Add modal `defaults(**values)`.
- [x] Add modal `on_submit(recipe_handler)`.
- [x] Add explicit `build()` as the mandatory validation boundary.
- [x] Ensure only `build()` returns `discord.ui.View` or `discord.ui.Modal`.
- [x] Optionally add context-manager syntax that calls the same `build()` logic.
- [x] If an unbuilt-draft warning is added, treat it only as diagnostics, never enforcement.

## Build validation

- [x] Reject an interactable tag without a recipe handler.
- [x] Reject a handler attached to an unknown tag.
- [x] Reject binding the same tag twice.
- [x] Reject missing slots.
- [x] Reject unknown slots.
- [x] Reject dynamic interactables without recipe handlers.
- [x] Reject handlers referencing unregistered recipes.
- [x] Reject nonprimitive persistent handler arguments.
- [x] Reject oversized or malformed custom IDs before Discord submission.
- [x] Reject unresolved placeholders instead of leaving them in output.
- [x] Reject extra renderer values when strict validation can identify them safely.
- [x] Require a modal submission recipe before building a modal.
- [x] Make build errors include template ID, tag/slot/field, and useful detail.

## Recipe attachment

- [x] Replace `ActionBinding.action` semantics with an explicitly named registered recipe handler.
- [x] Add a typed `recipe_handler(recipe_name, **primitive_arguments)` constructor.
- [x] Validate primitive argument types at handler creation.
- [x] Validate recipe existence during `build()`.
- [x] Ensure every static button and select receives a registered recipe.
- [x] Ensure every dynamic button and select receives a registered recipe.
- [x] Ensure every modal submission receives a registered recipe.
- [x] Replace `ui.modal:*` special dispatcher branches with registered open-modal recipes.
- [x] Replace `ui.view:*` special dispatcher branches with registered open-view recipes.
- [x] Register any truly generic UI operation such as `ui.dismiss` like every other recipe.
- [x] Remove alternate execution paths that bypass the recipe registry.

## Move behavior into recipes

- [x] Move hub-guild validation into feature recipes or small feature guard helpers called by them.
- [x] Move manage-guild authorization into owning recipes.
- [x] Move client-role authorization into owning recipes.
- [x] Move client, subscription, and network entity resolution into owning recipes.
- [x] Make recipes accept the interaction plus bounded primitive IDs.
- [x] Remove generic trigger payload enrichment.
- [x] Remove recipe-signature inspection and private registry access.
- [x] Remove action-to-permission and action-to-popup maps when recipe ownership replaces them.
- [x] Keep feature presenters free of repository access, authorization, mutation, and recipe calls.
- [x] Prefer structured immutable recipe results over arbitrary tuples/dictionaries.

## Renderer simplification

- [x] Keep one small public template facade.
- [x] Apply placeholder substitution to view labels, emoji, modal titles, field labels,
  descriptions, placeholders, embeds, popups, and channel messages.
- [x] Keep the renderer unaware of feature recipe modules and resources.
- [x] Keep the renderer unaware of repositories and core domain services.
- [x] Separate persistent handler arguments from submitted modal/select values.
- [x] Use one generic, versioned custom-ID codec.
- [x] Remove feature-specific custom-ID parsing from normal rendering.
- [x] Remove policy, injection, entity-resolution, success, and error branches from the renderer.
- [x] Split responsibilities only where it reduces complexity; do not distribute an interpreter
  across many small modules.

## Error handling

- [x] Keep templates free of error behavior.
- [x] Use one structured `TemplateRenderError` for loading, binding, placeholder, and build errors.
- [x] Continue routing operational failures through the centralized app error boundary.
- [x] Continue reporting operational failures to the `admin` public-updates channel.
- [x] Stop swallowing presenter exceptions.
- [x] Distinguish “no presenter registered” from “registered presenter failed.”
- [x] Never turn a presenter failure into a successful `Done.` response.
- [x] Catch only expected Discord exceptions when clearing or editing UI messages.

## Template migration

- [x] Move stable button labels, styles, emoji, and rows from Python back into YAML.
- [x] Use slots only for genuinely dynamic repeated controls.
- [x] Migrate network-profile controls.
- [x] Migrate subscription-moderation controls.
- [x] Migrate network-admin controls.
- [x] Migrate moderator-review controls.
- [x] Migrate join-network controls.
- [x] Migrate subscribe-setup controls.
- [x] Migrate blacklist select controls.
- [x] Migrate client-delete confirmation controls.
- [x] Migrate create/delete network modals.
- [x] Migrate client-profile edit modal.
- [x] Migrate join-request modal.
- [x] Migrate sticky views and persistent-view restoration.

## Persistent ID migration

- [x] Re-render all managed persistent views using the new custom-ID format.
- [x] Decide whether old IDs can be removed immediately or require one compatibility release.
- [x] If retained temporarily, isolate legacy decoding as read-only compatibility code.
- [x] Document the exact release/removal condition.
- [x] Do not retain the old renderer or policy system for legacy IDs.
- [x] Preserve the rule that client deletion is reachable only through its authorized recipe.

## Tests

- [x] Test unique interactive tags.
- [x] Test missing, duplicate, and unknown bindings.
- [x] Test missing and unknown slots.
- [x] Test unregistered recipe bindings.
- [x] Test dynamic components without handlers.
- [x] Test placeholders in all supported template string fields.
- [x] Test unresolved placeholders.
- [x] Test invalid styles and Discord limits.
- [x] Test deterministic custom-ID encoding/decoding.
- [x] Test custom-ID size and malformed payload failures.
- [x] Test modal defaults and submitted values separately from persistent arguments.
- [x] Test presenter failure propagation.
- [x] Test intentional missing-presenter fallback if the fallback remains supported.
- [x] Test every existing button, select, and modal behavior.
- [x] Test persistent-view restoration.
- [x] Test centralized error reporting to `admin`.
- [x] Test client preservation and deletion restrictions.
- [x] Add architecture tests prohibiting executable YAML and renderer business dependencies.

## LOC and cleanup requirements

- [x] Reduce `bot/app/widgets` from the `6197a6d` baseline of approximately 1,965 lines by at
  least 35%, targeting approximately 1,000 lines or fewer.
- [x] Reduce combined `app/widgets` plus `features/widgets` LOC materially, not just app LOC.
- [x] Reduce total production Python LOC relative to `8003569`.
- [x] Remove generic payload enrichment rather than moving it again.
- [x] Remove forwarding wrappers made obsolete by the draft API.
- [x] Remove unused schemas, result types, maps, imports, and compatibility helpers.
- [x] Do not count formatting compression as LOC reduction.
- [x] Produce a measured before/after LOC report from Git.

## Validation and handoff

- [x] Ruff passes.
- [x] Strict mypy passes.
- [x] All unit tests pass.
- [x] Full mock smoke passes.
- [x] Malformed-state server-init stress passes.
- [x] Persistent interaction tests pass.
- [x] Install-bundle validation passes.
- [x] Docker build passes.
- [x] GitHub Actions passes after push.
- [x] Final report lists remaining widget modules and their LOC.
- [x] Final report lists every template tag and attached recipe.
- [x] Final report lists deleted interpreter/policy/compatibility code.

## Post-c1bdc95 hardening (plan.md)

Verified by executable tests in `tests/unit/test_widget_hardening.py`,
`tests/unit/test_ui_custom_ids.py`, `tests/unit/test_recipe_registry.py`, and related handler tests:

- [x] Disabled static/dynamic interactables require registered recipe handlers.
- [x] `RecipeRegistry.run` rejects unexpected inputs (no silent filter).
- [x] Submitted modal/select keys colliding with persistent handler args are rejected.
- [x] Migration selects/buttons use registered `ui.migrate.*` recipes (no callback overrides).
- [x] Typed custom-ID round trips for `str` / `int` / `bool` / `None`.
- [x] Discord select label limit rejected at boundary (100 OK, 101 fails).
- [x] Mutation recipes require an authorized actor (missing/unauthorized covered).
- [x] Presenter failures propagate and do not send a misleading `Done.` response.
- [x] Legacy decode isolated in `bot/app/widgets/custom_id_legacy.py` with removal condition.

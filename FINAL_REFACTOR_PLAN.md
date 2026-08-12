# Final Refactor Convergence Plan

## Baseline

Implement against `refactor` at `6d66c7a` or its direct descendant.

The architecture is now accepted:

- `app` owns runtime orchestration, registration, generic widget dispatch, and error boundaries.
- `features` owns server-specific templates, recipes, presenters, and composition.
- `core` owns generalized workhorse APIs and has no feature/template knowledge.
- YAML templates create drafts; recipes bind to tagged controls; `build()` validates and creates
  Discord objects.
- All interactions execute registered recipes through the generic dispatcher.

Do not reorganize folders, replace the recipe system, introduce another interpreter, or repeat the
completed widget migration. This is the final bounded hardening and cleanup pass.

## Objective

Close the remaining correctness gaps, remove obvious residual complexity, validate the complete
system, and then stop architectural refactoring. Optimize for a smaller failure surface and clear
maintenance boundaries, not an arbitrary LOC target.

## Phase 1: Complete template schema validation

`bot/app/widgets/schema.py` remains substantially unchanged from the pre-hardening implementation.
Move configuration errors to template-load/build time rather than allowing Discord constructors or
dictionary lookups to fail later.

- Type `StaticButtonSpec.style` with the shared `ButtonStyle` literal.
- Remove the `# type: ignore` needed when passing template styles into `ButtonSpec`.
- Constrain button/select rows to Discord's supported range.
- Validate view row composition and total component capacity.
- Validate modal title length, field count, unique field IDs, text-input placeholder length,
  `max_length` range, defaults, file-upload `max_values`, labels, and descriptions.
- Validate select option values, labels, descriptions, option count, `min_values`, `max_values`, and
  their relationship to the number of options.
- Validate all substituted values after placeholder rendering, since valid YAML can become invalid
  after substitution.
- Convert Pydantic/Discord construction errors into structured `TemplateRenderError` messages that
  include template ID and tag, slot, or field.
- Reject application-owned invalid data. Do not silently truncate it.
- Remove the component-level legacy `id` to `tag` alias if no committed template uses it. Top-level
  template IDs and modal field IDs are not legacy and must remain.

Tests must cover each exact boundary and one value beyond it, invalid styles, invalid rows, duplicate
modal fields, invalid select ranges, invalid substituted values, and structured error context.

## Phase 2: Finish custom-ID hardening

The typed primitive codec is correct in principle but malformed-input handling is incomplete.

- Reject empty argument keys.
- Reject keys containing reserved delimiters.
- Reject duplicate keys while decoding instead of overwriting them.
- Enforce the Discord custom-ID length limit on decode as well as encode.
- Reject malformed type markers, malformed integers, missing recipe names, and malformed segments.
- Decide explicitly whether the corrected writer remains `tn1` or becomes `tn2`:
  - Prefer `tn2` if deployed `tn1` values include untyped data and a distinct prefix materially
    simplifies reasoning.
  - Retaining typed `tn1` is acceptable only if the decoder remains unambiguous and tests prove
    compatibility.
- Keep legacy decoding read-only and isolated in `custom_id_legacy.py`.
- Do not add new legacy mappings.
- Keep the documented removal condition: remove legacy decoding after managed persistent messages
  have been rewritten and one release records no legacy decode use.

Test exact type preservation for strings that resemble integers/booleans, all primitives, empty
strings, negative integers, duplicate keys, empty keys, reserved delimiters, malformed markers,
oversized inputs, and both supported legacy formats.

## Phase 3: Validate migration review before confirmation

The migration callback bypass is removed. Finish the flow without creating a new state framework.

- Store the set of required ambiguous resource keys on the migration `RenderedView`.
- Have `ui.migrate.store` validate that the submitted resource key is expected and the chosen ID is
  an allowed candidate for that key.
- Have `ui.migrate.confirm` refuse to close the view while required resolutions are missing.
- Return a clear ephemeral message listing unresolved resources.
- Only set a successful decision and stop the view when all required choices are valid.
- Preserve safe cancellation and timeout behavior.
- Keep `apply_manual_resolutions()` as the final defensive validation layer.

Test incomplete confirmation, invalid resource keys, invalid candidate IDs, replacement of a prior
selection, complete confirmation, cancellation, and timeout.

## Phase 4: Make truncation policy explicit

The rule should distinguish configuration from external display data:

- Application-owned templates, recipe-produced labels, and custom IDs must be validated and rejected
  when invalid.
- External Discord content displayed in a bounded field may be intentionally shortened.
- Put intentional shortening behind one clearly named helper such as `truncate_external_text()`.
- Use the helper for migration channel names and embed summaries.
- Remove scattered `[:100]`, `[:150]`, and `[:1024]` slices in widget presentation code.
- The helper must make truncation visible, preferably with an ellipsis when the limit permits.

Do not create a general formatting subsystem for this.

## Phase 5: Complete direct regression coverage

- Add a real disabled static YAML-button test. The current similarly named test exercises a dynamic
  slot component.
- Test every schema invariant added in Phase 1.
- Test custom-ID malformed inputs from Phase 2.
- Test migration confirmation behavior from Phase 3 through registered recipes.
- Retain tests for strict recipe inputs, submitted/persistent collision rejection, authorization,
  presenter error propagation, persistent restoration, and client deletion restrictions.
- Prefer behavioral tests through public draft/registry APIs. Use private helpers only when no public
  boundary can express the invariant.
- Do not duplicate large behavior suites merely to increase coverage.

## Phase 6: Focused complexity and LOC cleanup

Baseline at `6d66c7a`:

| Scope | LOC |
|---|---:|
| `bot/app/widgets` | 1,309 |
| `bot/features/widgets` | 553 |
| `bot/features/recipes` | 6,502 |
| All production Python under `bot` | 18,641 |

The hardening update improved correctness but added 235 production lines relative to `30ffab7`.
Reduce obvious residual complexity while preserving the new safeguards.

Audit and remove where proven unused:

- `ViewDraft`/`ModalDraft` `_result`, `result`, and context-manager machinery.
- Repeated limit-validation branches that a small local helper can express more clearly.
- Duplicate actor/context resolution inside the same feature domain.
- Stale imports, obsolete compatibility helpers, forwarding wrappers, and checked-off planning code
  that has no runtime purpose.
- Any alternate widget execution path bypassing the registry.

Constraints:

- Do not weaken validation to reduce LOC.
- Do not compress formatting or combine unrelated responsibilities to manufacture a lower count.
- Do not add a base-class hierarchy, policy engine, generic DI layer, or generic state machine.
- A modest LOC increase is acceptable only when required for an independently tested invariant.
- Report the final measurements honestly. Architectural convergence, not hitting a specific number,
  is the release gate.

## Phase 7: Documentation truthfulness

- Update `plan.md` and `WIDGET_TASKLIST.md` so completed claims match executable tests.
- Do not retain duplicate historical plans as active instructions. Move obsolete planning documents
  out of the implementation path or clearly mark them superseded.
- Record the active custom-ID version and legacy-removal condition.
- Record intentional truncation policy.
- Record final LOC and validation results.
- Do not mark a gate complete merely because an earlier commit passed it.

## Validation gates

Run from a clean checkout of the final commit:

1. Focused schema, drafts, custom-ID, migration, registry, authorization, and presenter tests.
2. `ruff check .`
3. `mypy bot tests/core`
4. `pytest -q tests/unit`
5. `python -m tests.core.runner recipe full --backend mock`
6. `python -m tests.core.runner recipe server-init-stress --backend mock --scenario malformed_channels`
7. Persistent-view restoration and legacy-ID tests.
8. `./bin/domain/test-install-bundle.sh`
9. `docker build --tag the-network:final-refactor .`
10. Push and confirm the GitHub Actions run for the exact final SHA.

If dependencies cannot be installed locally, do not claim local gates passed. Use the green CI run
for the exact commit and state which validation occurred only in CI.

After automated validation, run the live smoke suite on the test server. Live smoke is the release
gate for Discord behavior but should not block committing the final code if credentials are not
available to the implementing agent.

## Required final report

- Final commit SHA.
- Files changed with concise reasons.
- Each residual defect fixed and its regression test.
- Exact local validation commands and results.
- GitHub Actions URL for the final SHA.
- Before/after LOC for the four measured scopes.
- Deleted residual or compatibility code.
- Remaining legacy custom-ID compatibility and its removal trigger.
- Live-smoke status and any behavior that still requires test-server confirmation.

## Implementation status

Phases 1–7 implemented against baseline `6d66c7a`. Active codec: typed `tn1` (`!` markers).
External truncation: `bot.core.text.truncate_external_text`. Legacy decode:
`bot/app/widgets/custom_id_legacy.py` (remove after sticky rewrite + one release with no legacy hits).

## Definition of convergence

The final refactor is converged when:

- Invalid templates fail deterministically at load/build boundaries with useful context.
- Custom IDs preserve types and reject malformed or ambiguous input.
- Migration review cannot confirm incomplete or invalid resolutions.
- Truncation occurs only through an explicit external-content policy.
- Every documented widget invariant has direct regression coverage.
- No alternate interaction execution path bypasses the recipe registry.
- `app`, `features`, and `core` boundaries remain intact.
- All available automated gates pass for the exact final SHA.
- Remaining legacy compatibility has a concrete deletion trigger.
- The live smoke suite is ready for test-server execution.
- No further architectural rework is proposed. Future work becomes normal feature development,
  targeted bug fixes, or removal of expired legacy compatibility.

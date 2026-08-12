# Widget Template Refactor Tasklist

Active convergence contract: [`FINAL_REFACTOR_PLAN.md`](FINAL_REFACTOR_PLAN.md).
`plan.md` is superseded and is not an active instruction source.

Preserve the existing `app` / `features` / `core` boundaries. Architectural
convergence is complete when correctness invariants and automated gates hold —
not when historical LOC targets are met.

## Measured production LOC (from Git)

| Scope | `8003569` | `6d66c7a` | `5c49e05` | `940f5b5` |
|-------|----------:|----------:|----------:|----------:|
| `bot/app/widgets` | 1,086 | 1,309 | 1,490 | 1,632 |
| `bot/features/widgets` | 880 | 554 | 554 | 554 |
| Combined widgets | 1,966 | 1,863 | 2,044 | 2,186 |
| `bot/features/recipes` | — | 6,502 | — | 6,512 |
| All `bot/**/*.py` | 18,426 | 18,642 | 18,842 | 18,993 |

Deltas vs `8003569`: total production Python **+567** (not a reduction).
Deltas vs `6d66c7a`: total production Python **+351**.

Historical aspirational targets (≈1,000 `app/widgets`, total Python below
`8003569`, material combined-widget drop as a success gate) are **unmet /
superseded**. Validation and boundary hardening increased LOC while reducing the
failure surface. Do not weaken validation to chase old targets.

## Final convergence invariants (executable evidence)

Verified by `tests/unit/test_final_convergence.py` and retained hardening suites:

- [x] Tagged drafts: bind/fill → `build()` → Discord; recipe-only dispatch.
- [x] Disabled static/dynamic interactables require registered recipes.
- [x] Strict registry inputs; submitted/persistent key collision rejection.
- [x] Typed `tn1` custom IDs; legacy decode isolated with removal condition.
- [x] Migration review cannot confirm incomplete/invalid resolutions.
- [x] Migration review fails before open when ambiguities exceed UI capacity (4).
- [x] Resolved static+dynamic view layout validated before Discord construction.
- [x] External truncation only via `truncate_external_text()`.
- [x] Presenter failures propagate; client deletion stays recipe-gated.
- [x] Final Docker / GitHub Actions green for implementation SHA `940f5b5`
  ([run 31568965452](https://github.com/kidshuster/the-network/actions/runs/31568965452)).

## Validation gates (this pass)

- [x] Focused migration + layout tests
- [x] `ruff check .`
- [x] `mypy bot tests/core`
- [x] `pytest -q tests/unit` (595 passed)
- [x] mock full + malformed-state stress
- [x] install-bundle
- [x] persistent/legacy custom-ID + client-deletion tests
- [x] Docker / GitHub Actions for exact implementation SHA `940f5b5`
  ([run 31568965452](https://github.com/kidshuster/the-network/actions/runs/31568965452))
  (local Docker unavailable; CI Docker image build succeeded)

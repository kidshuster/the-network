# Live tests

Live tests use one Discord gateway session and two layers:

- **Probes** are directly callable Python checks registered in `probes.py`.
- **Recipes** are readable YAML sequences in `recipes/` that compose probes or
  other recipes.

List everything available:

```bash
python -m tests.live.runner list
```

Run one targeted probe (suitable for an agent diagnosing a specific failure):

```bash
python -m tests.live.runner probe hub.layout
python -m tests.live.runner probe hub.leaders_drift
```

Run a recipe:

```bash
python -m tests.live.runner recipe audit
python -m tests.live.runner recipe full
python -m tests.live.runner recipe stress
```

Run the same probes and recipes without connecting to Discord:

```bash
python -m tests.live.runner recipe full --backend mock
python -m tests.live.runner probe hub.layout --backend mock
python -m tests.live.runner recipe functional --backend mock --scenario stale_permissions
```

Mock scenarios live in `scenarios/`. They exercise recipe composition, cleanup,
protected-client invariants, expected state transitions, and common drift cases.
They do not replace live validation of Discord permission resolution, API errors,
webhooks, or rate limits. The normal `./test` gate runs the mock `full` recipe;
`./test --full` additionally runs it against Discord.

`full` is the normal smoke gate. `audit` avoids intentional permission drift.
`stress` is destructive burn-in and should use a staging guild. Recipes verify
that non-smoke clients still exist after every probe by default. Cleanup runs
from `finally` even when an earlier probe fails.

Add a probe by registering one async function in `probes.py`. Add or reorder
coverage by editing YAML; do not add another orchestration script.

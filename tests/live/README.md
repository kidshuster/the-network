# Live tests

Live tests use one Discord gateway session and three directories:

- `tests/core/` contains all Python probes, backends, guards, and runners.
- `tests/recipes/` contains YAML sequences that compose probes or recipes.
- `tests/live/` contains only shell launchers for real-server operation.

List everything available:

```bash
python -m tests.core.runner list
```

Run one targeted probe (suitable for an agent diagnosing a specific failure):

```bash
python -m tests.core.runner probe hub.layout
python -m tests.core.runner probe hub.leaders_drift
```

Run a recipe:

```bash
python -m tests.core.runner recipe audit
python -m tests.core.runner recipe full
python -m tests.core.runner recipe stress
python -m tests.core.runner recipe server-init-stress
```

Run the same probes and recipes without connecting to Discord:

```bash
python -m tests.core.runner recipe full --backend mock
python -m tests.core.runner probe hub.layout --backend mock
python -m tests.core.runner recipe functional --backend mock --scenario stale_permissions
```

Mock scenarios live in `scenarios/`. They exercise recipe composition, cleanup,
protected-client invariants, expected state transitions, and common drift cases.
They do not replace live validation of Discord permission resolution, API errors,
webhooks, or rate limits. The normal `./test` gate runs the mock `full` recipe;
`./test --full` additionally runs it against Discord.

Recipe steps may request `pause: true`. The live backend owns that behavior and
waits for `SMOKE_PHASE_DELAY_SEC` after the probe; the mock backend implements
the same interface without sleeping. Backend-specific rate-limit behavior must
not be added to the recipe runner.

The server-init launcher contains no embedded test logic; it delegates to YAML:

```bash
tests/live/smoke_server_init.sh --audit
tests/live/smoke_server_init.sh --stress
tests/live/smoke_server_init.sh --stress --mock --scenario=malformed_channels
```

`server-init-stress` first rectifies state accumulated by an always-on server,
audits the normalized layout, then exercises Leaders permission drift,
client-layout drift, channel deletion/recreation, and repeated initialization.
The `hard_blocker` scenario verifies that community resources hidden from the
bot are reported rather than silently treated as repaired.

`full` is the normal smoke gate. `audit` avoids intentional permission drift.
`stress` is destructive burn-in and should use a staging guild. Recipes verify
that non-smoke clients still exist after every probe by default. Cleanup runs
from `finally` even when an earlier probe fails.

Add a probe by registering one async function in `probes.py`. Add or reorder
coverage by editing YAML; do not add another orchestration script.

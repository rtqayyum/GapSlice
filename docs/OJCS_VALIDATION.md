# Local verification of the OJ-CS diagnostic branch

Verification began on 17 November 2026, with managed-runtime follow-up on
18 November 2026. Inherited baseline: Git commit
`e9b883da49cfbaedcfc3e284bfbd31dfdccbce77`.

## Executed locally

- 32 selected tests passed: inherited model/channel/descriptor checks plus
  new feasibility, failure propagation, resume, project-guard and runtime checks.
- All four synthetic diagnostic families completed in a real two-process local
  smoke run: four complete task records, zero failed and zero pending.
- Additional synthetic boundary checks completed for blocked/limited-bandwidth
  radio, perfectly correlated diffuse fading, 20-truck common-loss braking and
  320-tenant type-B market evaluation.
- Every new shell script and Batch passed `bash -n` individually. Python source
  passed compilation checks. Whitespace checks passed.
- The resume integration test deliberately fails a task, checks nonzero campaign
  status, executes the real radio task successfully, and verifies that a later
  invocation preserves the complete result without rerunning it.
- Guard tests use real shell processes to check acquire/release, competing
  owners, preserved unknown/changed ownership, and filesystem error reporting.
  A controlled module-load failure exercises Batch twice and verifies that the
  real failure phase is recorded and neither startup strands a guard.
- Runtime tests create/reuse a real isolated venv, preserve incompatible inputs,
  reject an external venv symlink and unverified installer, and simulate an old
  module interpreter to verify managed-runtime selection and error propagation.
- In a separate actual download check, the official pinned uv installer and
  CPython 3.13.9 were installed inside a local validation project, and a seeded
  isolated venv was created successfully. The pinned scientific requirements
  were then installed into that clean environment, all 32 selected tests passed,
  and all four smoke configurations executed successfully with two workers.
  The same 32 tests also passed under the original Conda interpreter. These
  local checks ran on macOS ARM64, not on a Linux cluster.

The complete scientific suite command used was:

```bash
python -m pytest tests/test_hpc_project_lock.py tests/test_hpc_python_runtime.py \
  tests/test_revision_feasibility.py tests/test_revision_campaign.py \
  tests/test_model_consistency.py tests/test_channel.py \
  tests/test_descriptor_tables.py -q -p no:cacheprovider
```

The local smoke command was:

```bash
python -m gapslice.revision.campaign local --preset smoke --workers 2
```

The scientific library versions matched `requirements-hpc.txt`: NumPy 2.3.5,
SciPy 1.16.3, CVXPY 1.9.2, Clarabel 0.11.1, Matplotlib 3.11.1; pytest 8.4.2.
Both local distributions used Python 3.13.9. Byte-identical regeneration of inherited PDF figures
and a full rerun of every original experiment were outside these checks.

## Not executed or established

- No Slurm job was submitted or run as part of this local verification.
- Separately supplied cluster logs showed two earlier jobs stopping at the old
  flock guard before experiments. That guard is replaced; its underlying
  cluster filesystem failure mode was not established by those logs.
- A subsequent cluster startup acquired the new guard and exposed a default
  module Python older than 3.11. The managed-runtime fallback addressed that
  prerequisite; later supplied logs confirmed Linux preparation and imports.
- Later supplied logs confirmed Linux preparation and scientific-package imports
  succeeded. A smoke job then passed 30 tests and failed two runtime fixtures
  before experiments. Those failures were reproduced locally with the managed
  interpreter: creating a copied venv through an alias broke library lookup.
  Resolving the base executable and using venv symlinks fixes the reproduced
  failures; the fixtures now verify pip as well as the Python prefix/version.
- Login-node dependency downloads and imports are confirmed by supplied logs.
  Successful scientific worker execution, peak memory and multi-node shared
  filesystem behavior on the cluster remain unverified.
- The 2,004-configuration audit and 25,308-configuration full diagnostic campaigns
  have not been run by this verification.
- All new diagnostic inputs are synthetic. There is no measured-data/testbed
  validation, new control proof, new full-maneuver guarantee, full NR compliance
  claim, formal privacy guarantee or completed revised manuscript.

The inherited stored results were left unchanged. New local runtime outputs and
logs are excluded from Git; campaign manifests and task records are generated
inside each checkout when it runs. See [the research plan](OJCS_REVISION_PLAN.md)
and [the HPC runbook](HPC_OJCS.md) for the remaining work and cluster commands.
